<?php
namespace plagiarism_dualtier\task;

defined('MOODLE_INTERNAL') || die();

/**
 * Ad-hoc task: poll the detection backend for ONE submission's result,
 * re-queueing itself with a short delay until the result is ready.
 *
 * Queued by submit_file.php immediately after a successful submission,
 * instead of relying solely on check_results.php's 5-minute scheduled
 * task. Moodle's scheduled-task cron fields (minute/hour/day/month/
 * dayofweek) have no seconds field and a hard 1-minute granularity floor
 * -- even running admin/cli/cron.php more often than once a minute can't
 * make a *scheduled* task fire faster than that, because Moodle computes
 * its next-run-time at minute resolution regardless of how often cron.php
 * itself is invoked. Ad-hoc tasks have no such floor: they run as soon as
 * cron.php next picks them up and they're due, so this is what actually
 * delivers sub-minute latency (combined with running cron.php every ~15s
 * -- see the VM crontab). check_results.php remains as a slower-but-
 * persistent fallback in case this chain is ever dropped (e.g. the worker
 * crashes mid-chain).
 */
class poll_result extends \core\task\adhoc_task {

    /** Re-queue interval between poll attempts, in seconds. */
    const POLL_INTERVAL = 15;

    /** Give up re-queueing after this many attempts (~10 minutes at 15s
     *  intervals) and leave the record for check_results.php's fallback
     *  poll instead of retrying forever. */
    const MAX_ATTEMPTS = 40;

    public function get_name(): string {
        return get_string('task_poll_result', 'plagiarism_dualtier');
    }

    public function execute(): void {
        global $DB;

        $data = $this->get_custom_data();

        if (empty($data->recordid)) {
            mtrace('DualTier poll_result: missing recordid');
            return;
        }

        $record = $DB->get_record('plagiarism_dualtier_files', ['id' => $data->recordid]);
        if (!$record || empty($record->externalid)) {
            return;
        }

        // Another poll attempt (or the scheduled-task fallback) may have
        // already resolved this record since this task was queued.
        if ($record->status !== 'submitted') {
            return;
        }

        $client = new \plagiarism_dualtier\api_client();
        $status = null;

        try {
            $status = $client->get_status($record->externalid);
        } catch (\Exception $e) {
            mtrace("DualTier poll_result: error polling record {$record->id} - " . $e->getMessage());
        }

        if ($status && $status->status === 'completed') {
            $results = $client->get_results($record->externalid);
            if ($results) {
                $record->status = 'complete';
                $record->similarityscore = $results->final_score;
                $record->tier_resolved = $results->escalated ? 'tier2' : 'tier1';
                $record->is_plagiarised = $results->is_plagiarised ? 1 : 0;
                $record->reportdata = json_encode($results);
                $record->timemodified = time();
                $DB->update_record('plagiarism_dualtier_files', $record);
                mtrace("DualTier poll_result: record {$record->id} complete, score={$results->final_score}");
            }
            return;
        }

        if ($status && $status->status === 'failed') {
            $record->status = 'error';
            $record->errormessage = 'Detection failed on backend';
            $record->timemodified = time();
            $DB->update_record('plagiarism_dualtier_files', $record);
            mtrace("DualTier poll_result: record {$record->id} failed");
            return;
        }

        // Still processing (or a transient poll error) -- re-queue for
        // another attempt shortly.
        $attempt = ($data->attempt ?? 0) + 1;
        if ($attempt >= self::MAX_ATTEMPTS) {
            mtrace("DualTier poll_result: giving up on record {$record->id} after {$attempt} attempts; leaving to check_results fallback");
            return;
        }

        $next = new self();
        $next->set_custom_data((object) [
            'recordid' => $data->recordid,
            'attempt' => $attempt,
        ]);
        $next->set_next_run_time(time() + self::POLL_INTERVAL);
        \core\task\manager::queue_adhoc_task($next);
    }
}
