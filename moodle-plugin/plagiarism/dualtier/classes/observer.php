<?php
namespace plagiarism_dualtier;

defined('MOODLE_INTERNAL') || die();

/**
 * Event observer for assignment submissions.
 *
 * Listens for file and online text uploads, creates a tracking record,
 * and queues an ad-hoc task to submit to the detection backend.
 */
class observer {

    /**
     * Handle an assessable_uploaded event (file or online text).
     *
     * @param \core\event\base $event
     */
    public static function file_uploaded(\core\event\base $event): void {
        global $CFG, $DB;

        require_once($CFG->dirroot . '/plagiarism/dualtier/lib.php');

        $cmid = $event->contextinstanceid;

        // Check if the plugin is enabled for this module.
        if (!\plagiarism_plugin_dualtier::is_enabled_for_module($cmid)) {
            return;
        }

        $eventdata = $event->get_data();
        $userid = $eventdata['userid'];
        $courseid = $eventdata['courseid'] ?? '';

        // Get assignment ID from the course module.
        $cm = get_coursemodule_from_id('', $cmid);
        $assignmentid = $cm ? (string) $cm->instance : '';

        // Handle file submissions.
        if (!empty($eventdata['other']['pathnamehashes'])) {
            $fs = get_file_storage();
            foreach ($eventdata['other']['pathnamehashes'] as $hash) {
                $file = $fs->get_file_by_hash($hash);
                if (!$file || $file->is_directory()) {
                    continue;
                }

                self::queue_submission(
                    $cmid,
                    $userid,
                    $file->get_contenthash(),
                    $file->get_filename(),
                    $courseid,
                    $assignmentid,
                    $file
                );
            }
        }

        // Handle online text submissions.
        if (!empty($eventdata['other']['content'])) {
            $content = $eventdata['other']['content'];
            // Strip HTML tags for plain text submission.
            $plaintext = html_to_text($content, 0, false);
            $identifier = hash('sha256', $plaintext);

            self::queue_submission(
                $cmid,
                $userid,
                $identifier,
                'onlinetext.txt',
                $courseid,
                $assignmentid,
                null,
                $plaintext
            );
        }
    }

    /**
     * Create a tracking record and queue the ad-hoc submission task.
     *
     * @param int $cmid Course module ID.
     * @param int $userid User ID.
     * @param string $identifier Content hash for dedup.
     * @param string $filename Original filename.
     * @param string $courseid Course ID.
     * @param string $assignmentid Assignment ID.
     * @param \stored_file|null $file Moodle stored file (for file submissions).
     * @param string|null $content Plain text content (for online text submissions).
     */
    private static function queue_submission(
        int $cmid,
        int $userid,
        string $identifier,
        string $filename,
        string $courseid,
        string $assignmentid,
        ?\stored_file $file = null,
        ?string $content = null
    ): void {
        global $DB;

        // Dedup: Moodle is known to sometimes fire assessable_uploaded more
        // than once for a single logical submission action. Without this
        // check, each firing created an independent tracking record and an
        // independent backend submission for identical content -- wasted
        // Tier 2 cost, redundant index entries, and (via get_links()
        // picking the most-recently-modified record) a risk of the
        // displayed badge flipping between near-duplicate results. See
        // evaluation/reports/07_full_pipeline_audit.md, finding 3.
        $existing = $DB->get_record('plagiarism_dualtier_files', [
            'cmid' => $cmid,
            'userid' => $userid,
            'identifier' => $identifier,
        ]);
        if ($existing && $existing->status !== 'error') {
            return;
        }

        $now = time();

        // Create tracking record.
        $record = new \stdClass();
        $record->cmid = $cmid;
        $record->userid = $userid;
        $record->identifier = $identifier;
        $record->filename = $filename;
        $record->status = 'pending';
        $record->timecreated = $now;
        $record->timemodified = $now;
        $record->id = $DB->insert_record('plagiarism_dualtier_files', $record);

        // Build task custom data.
        $taskdata = new \stdClass();
        $taskdata->recordid = $record->id;
        $taskdata->courseid = $courseid;
        $taskdata->assignmentid = $assignmentid;

        if ($file) {
            // Store the file's identifier, not a copied path: ad-hoc tasks run in a
            // later, separate request (via cron), and make_request_directory() paths
            // are deleted at the end of the request that created them.
            $taskdata->pathnamehash = $file->get_pathnamehash();
        } else if ($content) {
            $taskdata->content = $content;
        }

        // Queue the ad-hoc task.
        $task = new \plagiarism_dualtier\task\submit_file();
        $task->set_custom_data($taskdata);
        $task->set_userid($userid);
        \core\task\manager::queue_adhoc_task($task);
    }
}
