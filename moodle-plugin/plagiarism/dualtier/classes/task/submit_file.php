<?php
namespace plagiarism_dualtier\task;

defined('MOODLE_INTERNAL') || die();

/**
 * Ad-hoc task: submit a file to the detection backend.
 *
 * Queued by the event observer when a student submits an assignment.
 */
class submit_file extends \core\task\adhoc_task {

    public function get_name(): string {
        return get_string('task_submit_file', 'plagiarism_dualtier');
    }

    public function execute(): void {
        global $DB;

        $data = $this->get_custom_data();

        if (empty($data->recordid)) {
            mtrace('DualTier submit_file: missing recordid');
            return;
        }

        $record = $DB->get_record('plagiarism_dualtier_files', ['id' => $data->recordid]);
        if (!$record) {
            mtrace("DualTier submit_file: record {$data->recordid} not found");
            return;
        }

        $client = new \plagiarism_dualtier\api_client();

        $result = null;

        if (!empty($data->pathnamehash)) {
            // File submission: re-fetch the stored file now, since the ad-hoc task
            // runs in a later, separate request than the one that queued it.
            $fs = get_file_storage();
            $file = $fs->get_file_by_hash($data->pathnamehash);

            if (!$file || $file->is_directory()) {
                $record->status = 'error';
                $record->errormessage = 'Stored file no longer available';
                $record->timemodified = time();
                $DB->update_record('plagiarism_dualtier_files', $record);
                mtrace("DualTier: file missing for record {$record->id}");
                return;
            }

            $tmpdir = make_request_directory();
            $tmppath = $tmpdir . '/' . $file->get_filename();
            $file->copy_content_to($tmppath);

            $result = $client->submit_file(
                $record->filename ?? 'document',
                $tmppath,
                (string) ($data->courseid ?? ''),
                (string) ($data->assignmentid ?? ''),
                (string) $record->userid
            );
        } else if (!empty($data->content)) {
            // Online text submission.
            $result = $client->submit_text(
                $data->content,
                (string) ($data->courseid ?? ''),
                (string) ($data->assignmentid ?? ''),
                (string) $record->userid
            );
        }

        if ($result && !empty($result->submission_id)) {
            $record->externalid = $result->submission_id;
            $record->status = 'submitted';
            $record->timemodified = time();
            $DB->update_record('plagiarism_dualtier_files', $record);
            mtrace("DualTier: submitted record {$record->id} -> external {$result->submission_id}");

            // Start fast ad-hoc polling instead of waiting for
            // check_results.php's 5-minute scheduled task -- see
            // poll_result.php for why ad-hoc (not scheduled) is required
            // to get sub-minute latency.
            $poll = new poll_result();
            $poll->set_custom_data((object) ['recordid' => $record->id, 'attempt' => 0]);
            $poll->set_next_run_time(time() + 3); // give the backend a moment to start processing
            \core\task\manager::queue_adhoc_task($poll);
        } else {
            $record->status = 'error';
            $record->errormessage = 'Failed to submit to detection backend';
            $record->timemodified = time();
            $DB->update_record('plagiarism_dualtier_files', $record);
            mtrace("DualTier: failed to submit record {$record->id}");
        }
    }
}
