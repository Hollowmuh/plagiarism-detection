<?php
defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/plagiarism/lib.php');

class plagiarism_plugin_dualtier extends plagiarism_plugin {

    /**
     * Return the links (similarity badges) for a given file/content.
     *
     * Called by Moodle's gradebook and assignment grading pages.
     *
     * @param array $linkarray Contains cmid, userid, file/content, context, etc.
     * @return string HTML to display.
     */
    public function get_links($linkarray) {
        global $DB, $OUTPUT;

        $cmid = $linkarray['cmid'];
        $userid = $linkarray['userid'];

        // Check if plugin is enabled for this module.
        if (!self::is_enabled_for_module($cmid)) {
            return '';
        }

        // Moodle's own file-submission renderer (mod/assign/renderer.php's
        // assign_files()) populates 'userid' from $file->get_userid(), which
        // is NULL for files in a permanent (non-draft) file area -- this is
        // standard Moodle file-API behaviour, not specific to any one
        // submission path, so it affects every real file submission, not
        // just programmatic ones. Fall back to resolving the true owner from
        // the assignment submission record itself via the file's itemid
        // (assignsubmission_file stores files with itemid = submission id).
        if (empty($userid) && !empty($linkarray['file'])) {
            $file = $linkarray['file'];
            if ($file->get_component() === 'assignsubmission_file') {
                $userid = $DB->get_field('assign_submission', 'userid', ['id' => $file->get_itemid()]);
            }
        }

        if (empty($userid)) {
            return '';
        }

        // Find the most recent record for this user + module.
        $record = $DB->get_record_sql(
            "SELECT * FROM {plagiarism_dualtier_files}
             WHERE cmid = ? AND userid = ?
             ORDER BY timemodified DESC
             LIMIT 1",
            [$cmid, $userid]
        );

        if (!$record) {
            return '';
        }

        if ($record->status === 'pending' || $record->status === 'submitted') {
            return html_writer::tag('span',
                get_string('checking', 'plagiarism_dualtier'),
                ['class' => 'plagiarism-dualtier-badge dualtier-pending']
            );
        }

        if ($record->status === 'error') {
            return html_writer::tag('span',
                get_string('error_short', 'plagiarism_dualtier'),
                ['class' => 'plagiarism-dualtier-badge dualtier-error']
            );
        }

        if ($record->status === 'complete') {
            $score = (int) round($record->similarityscore * 100);

            if ($score < 30) {
                $class = 'dualtier-green';
            } else if ($score < 70) {
                $class = 'dualtier-orange';
            } else {
                $class = 'dualtier-red';
            }

            $tier = $record->tier_resolved ? " ({$record->tier_resolved})" : '';
            $text = "{$score}%{$tier}";

            $reporturl = new moodle_url('/plagiarism/dualtier/report.php', [
                'id' => $record->id,
                'cmid' => $cmid,
            ]);

            $html = html_writer::link($reporturl, $text, [
                'class' => 'plagiarism-dualtier-badge ' . $class,
                'title' => get_string('viewreport', 'plagiarism_dualtier'),
            ]);

            $html .= self::get_ai_badge($record, $reporturl);

            return $html;
        }

        return '';
    }

    /**
     * Render the advisory AI-authorship badge, if the cached report data
     * includes one. Deliberately a visually distinct, separate badge from
     * the similarity score above -- these are independent signals and must
     * never be shown as one combined number. See
     * docs/2026-07-01/ai_detection_tier_1426.md for why this is
     * advisory-only (false-positive/ESL-bias caveats).
     *
     * @param object $record The plagiarism_dualtier_files record (with reportdata).
     * @param moodle_url $reporturl Link target (same report page).
     * @return string HTML, or '' if no AI detection data is available yet.
     */
    private static function get_ai_badge($record, moodle_url $reporturl): string {
        if (empty($record->reportdata)) {
            return '';
        }

        $report = json_decode($record->reportdata);
        if (empty($report->ai_detection)) {
            return '';
        }

        $ai = $report->ai_detection;
        $aiscore = (int) round($ai->ai_score * 100);

        $verdictclass = [
            'likely_human' => 'dualtier-ai-human',
            'uncertain' => 'dualtier-ai-uncertain',
            'likely_ai' => 'dualtier-ai-likely',
        ][$ai->verdict] ?? 'dualtier-ai-uncertain';

        return html_writer::link($reporturl, "AI: {$aiscore}%", [
            'class' => 'plagiarism-dualtier-badge dualtier-ai-badge ' . $verdictclass,
            'title' => get_string('ai_badge_title', 'plagiarism_dualtier'),
        ]);
    }

    /**
     * Add form elements to the activity module settings form.
     *
     * @param object $mform The form object.
     * @param object $context The module context.
     * @param string $modulename The module name (e.g. 'assign').
     */
    public function get_form_elements_module($mform, $context, $modulename = '') {
        if (!self::is_plugin_enabled()) {
            return;
        }

        $cmid = optional_param('update', 0, PARAM_INT);

        $mform->addElement('header', 'plagiarism_dualtier_header',
            get_string('pluginname', 'plagiarism_dualtier'));

        $mform->addElement('advcheckbox', 'plagiarism_dualtier_enabled',
            get_string('enable_for_activity', 'plagiarism_dualtier'));
        $mform->setDefault('plagiarism_dualtier_enabled', 0);

        // Load saved value.
        if ($cmid) {
            global $DB;
            $config = $DB->get_record('plagiarism_dualtier_config', ['cmid' => $cmid]);
            if ($config) {
                $mform->setDefault('plagiarism_dualtier_enabled', $config->enabled);
            }
        }
    }

    /**
     * Save per-module form elements.
     *
     * @param object $data The submitted form data.
     */
    public function save_form_elements($data) {
        global $DB;

        if (!isset($data->coursemodule)) {
            return;
        }

        $cmid = $data->coursemodule;
        $enabled = isset($data->plagiarism_dualtier_enabled) ? (int) $data->plagiarism_dualtier_enabled : 0;

        $existing = $DB->get_record('plagiarism_dualtier_config', ['cmid' => $cmid]);

        if ($existing) {
            $existing->enabled = $enabled;
            $DB->update_record('plagiarism_dualtier_config', $existing);
        } else {
            $DB->insert_record('plagiarism_dualtier_config', (object) [
                'cmid' => $cmid,
                'enabled' => $enabled,
            ]);
        }
    }

    /**
     * Display the student disclosure notice.
     *
     * @param int $cmid The course module ID.
     * @return string HTML disclosure text.
     */
    public function print_disclosure($cmid) {
        global $OUTPUT;

        if (!self::is_enabled_for_module($cmid)) {
            return '';
        }

        return $OUTPUT->box(
            get_string('student_disclosure', 'plagiarism_dualtier'),
            'generalbox boxaligncenter plagiarism-dualtier-disclosure'
        );
    }

    /**
     * Check if the plugin is globally enabled.
     *
     * @return bool
     */
    public static function is_plugin_enabled(): bool {
        return (bool) get_config('plagiarism_dualtier', 'enabled');
    }

    /**
     * Check if the plugin is enabled for a specific course module.
     *
     * @param int $cmid Course module ID.
     * @return bool
     */
    public static function is_enabled_for_module(int $cmid): bool {
        global $DB;

        if (!self::is_plugin_enabled()) {
            return false;
        }

        $config = $DB->get_record('plagiarism_dualtier_config', ['cmid' => $cmid]);
        return $config && (bool) $config->enabled;
    }
}
