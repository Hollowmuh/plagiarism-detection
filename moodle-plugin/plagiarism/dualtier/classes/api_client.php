<?php
namespace plagiarism_dualtier;

defined('MOODLE_INTERNAL') || die();

/**
 * HTTP client for communicating with the FastAPI detection backend.
 *
 * Uses Moodle's built-in curl class for all HTTP operations.
 */
class api_client {

    /** @var string Base API URL. */
    private $baseurl;

    /** @var string Bearer token. */
    private $apikey;

    /** Connect/total timeouts (seconds). Applied to every request, not just
     *  is_healthy() -- previously only the health check set these, leaving
     *  submit_file()/get_status()/get_results() able to hang indefinitely
     *  on a slow/unresponsive backend. More consequential since
     *  poll_result.php calls get_status() every 15s and a hung call would
     *  stall that whole cron.php pass. See
     *  evaluation/reports/07_full_pipeline_audit.md, finding 4. */
    const CONNECT_TIMEOUT = 5;
    const REQUEST_TIMEOUT = 15;
    const SUBMIT_TIMEOUT = 30; // file upload is heavier than a status poll

    public function __construct() {
        global $CFG;

        // The \curl class lives in filelib.php, which isn't autoloaded and isn't
        // guaranteed to be included yet in every context this class runs in
        // (cron scheduled/ad-hoc tasks in particular).
        require_once($CFG->libdir . '/filelib.php');

        $this->baseurl = rtrim(get_config('plagiarism_dualtier', 'apiurl'), '/');
        $this->apikey = get_config('plagiarism_dualtier', 'apikey');
    }

    /**
     * Submit a file to the detection backend.
     *
     * @param string $filename Original filename.
     * @param string $filepath Path to the file on disk.
     * @param string $courseid Course ID.
     * @param string $assignmentid Assignment ID.
     * @param string $userid User ID.
     * @return object|null Response with submission_id, or null on failure.
     */
    public function submit_file(
        string $filename,
        string $filepath,
        string $courseid = '',
        string $assignmentid = '',
        string $userid = ''
    ): ?object {
        $curl = new \curl();
        $this->set_headers($curl);
        $curl->setopt([
            'CURLOPT_CONNECTTIMEOUT' => self::CONNECT_TIMEOUT,
            'CURLOPT_TIMEOUT' => self::SUBMIT_TIMEOUT,
        ]);

        $params = [
            'file' => new \CURLFile($filepath, '', $filename),
            'course_id' => $courseid,
            'assignment_id' => $assignmentid,
            'user_id' => $userid,
        ];

        $response = $curl->post($this->baseurl . '/submissions/', $params);
        $httpcode = $curl->get_info()['http_code'] ?? 0;

        if ($httpcode === 202) {
            return json_decode($response);
        }

        debugging("DualTier API submit failed (HTTP {$httpcode}): {$response}", DEBUG_DEVELOPER);
        return null;
    }

    /**
     * Submit text content (online text) to the detection backend.
     *
     * @param string $content The text content.
     * @param string $courseid Course ID.
     * @param string $assignmentid Assignment ID.
     * @param string $userid User ID.
     * @return object|null Response with submission_id, or null on failure.
     */
    public function submit_text(
        string $content,
        string $courseid = '',
        string $assignmentid = '',
        string $userid = ''
    ): ?object {
        // Write content to a temporary file and submit as .txt.
        $tmpfile = make_request_directory() . '/submission.txt';
        file_put_contents($tmpfile, $content);

        return $this->submit_file('submission.txt', $tmpfile, $courseid, $assignmentid, $userid);
    }

    /**
     * Get the status of a submission.
     *
     * @param string $submissionid The backend submission UUID.
     * @return object|null Status response or null on failure.
     */
    public function get_status(string $submissionid): ?object {
        $curl = new \curl();
        $this->set_headers($curl);
        $curl->setopt([
            'CURLOPT_CONNECTTIMEOUT' => self::CONNECT_TIMEOUT,
            'CURLOPT_TIMEOUT' => self::REQUEST_TIMEOUT,
        ]);

        $response = $curl->get($this->baseurl . '/submissions/' . $submissionid . '/status');
        $httpcode = $curl->get_info()['http_code'] ?? 0;

        if ($httpcode === 200) {
            return json_decode($response);
        }

        return null;
    }

    /**
     * Get the full detection results for a submission.
     *
     * @param string $submissionid The backend submission UUID.
     * @return object|null Results response or null on failure.
     */
    public function get_results(string $submissionid): ?object {
        $curl = new \curl();
        $this->set_headers($curl);
        $curl->setopt([
            'CURLOPT_CONNECTTIMEOUT' => self::CONNECT_TIMEOUT,
            'CURLOPT_TIMEOUT' => self::REQUEST_TIMEOUT,
        ]);

        $response = $curl->get($this->baseurl . '/submissions/' . $submissionid . '/results');
        $httpcode = $curl->get_info()['http_code'] ?? 0;

        if ($httpcode === 200) {
            return json_decode($response);
        }

        return null;
    }

    /**
     * Check if the backend API is reachable.
     *
     * @return bool
     */
    public function is_healthy(): bool {
        $curl = new \curl();
        $curl->setopt(['CURLOPT_CONNECTTIMEOUT' => 5, 'CURLOPT_TIMEOUT' => 10]);

        $response = $curl->get($this->baseurl . '/health/live');
        $httpcode = $curl->get_info()['http_code'] ?? 0;

        return $httpcode === 200;
    }

    /**
     * Set authorization headers on the curl instance.
     *
     * @param \curl $curl
     */
    private function set_headers(\curl $curl): void {
        $curl->setHeader([
            'Authorization: Bearer ' . $this->apikey,
        ]);
    }
}
