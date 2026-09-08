<?php
namespace plagiarism_dualtier\task;

defined('MOODLE_INTERNAL') || die();

/**
 * Scheduled task: poll the detection backend for completed results.
 *
 * Runs every 5 minutes. Checks all records with status='submitted' and
 * updates them with detection results when available.
 */
class check_results extends \core\task\scheduled_task {

    public function get_name(): string {
        return get_string('task_check_results', 'plagiarism_dualtier');
    }

    public function execute(): void {
        global $CFG, $DB;

        require_once($CFG->dirroot . '/plagiarism/dualtier/lib.php');

        if (!\plagiarism_plugin_dualtier::is_plugin_enabled()) {
            return;
        }

        // Get all pending submissions.
        $records = $DB->get_records('plagiarism_dualtier_files', ['status' => 'submitted']);

        if (empty($records)) {
            return;
        }

        mtrace('DualTier check_results: checking ' . count($records) . ' submissions');

        $client = new \plagiarism_dualtier\api_client();

        foreach ($records as $record) {
            if (empty($record->externalid)) {
                continue;
            }

            try {
                $status = $client->get_status($record->externalid);

                if (!$status) {
                    continue;
                }

                if ($status->status === 'completed') {
                    // Fetch full results.
                    $results = $client->get_results($record->externalid);

                    if ($results) {
                        $record->status = 'complete';
                        $record->similarityscore = $results->final_score;
                        $record->tier_resolved = $results->escalated ? 'tier2' : 'tier1';
                        $record->is_plagiarised = $results->is_plagiarised ? 1 : 0;
                        $record->reportdata = json_encode($results);
                        $record->timemodified = time();
                        $DB->update_record('plagiarism_dualtier_files', $record);
                        mtrace("  Record {$record->id}: complete, score={$results->final_score}");
                    }
                } else if ($status->status === 'failed') {
                    $record->status = 'error';
                    $record->errormessage = 'Detection failed on backend';
                    $record->timemodified = time();
                    $DB->update_record('plagiarism_dualtier_files', $record);
                    mtrace("  Record {$record->id}: failed");
                }
                // If still processing (pending/extracting/detecting), do nothing — check again next run.

            } catch (\Exception $e) {
                mtrace("  Record {$record->id}: error polling - " . $e->getMessage());
            }
        }
    }
}
