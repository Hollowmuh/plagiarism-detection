<?php
defined('MOODLE_INTERNAL') || die();

// General.
$string['pluginname'] = 'Dual-Tier Plagiarism Detection';
$string['pluginname_short'] = 'DualTier';

// Settings.
$string['setting_enabled'] = 'Enable plagiarism detection';
$string['setting_enabled_desc'] = 'Enable the dual-tier plagiarism detection system globally.';
$string['setting_apiurl'] = 'Detection API URL';
$string['setting_apiurl_desc'] = 'Base URL of the FastAPI detection backend (e.g. http://api:8000/api/v1).';
$string['setting_apikey'] = 'API key';
$string['setting_apikey_desc'] = 'Bearer token for authenticating with the detection backend.';
$string['setting_threshold'] = 'Flag threshold (%)';
$string['setting_threshold_desc'] = 'Similarity percentage above which a submission is flagged for review.';
$string['setting_tau_low'] = 'Tau low';
$string['setting_tau_low_desc'] = 'Tier 1 lower threshold. Scores below this are classified as original.';
$string['setting_tau_high'] = 'Tau high';
$string['setting_tau_high_desc'] = 'Tier 1 upper threshold. Scores above this are classified as plagiarised.';
$string['setting_crosscheck'] = 'Cross-submission checking';
$string['setting_crosscheck_desc'] = 'Compare submissions against other students in the same assignment.';

// Activity form.
$string['enable_for_activity'] = 'Enable plagiarism detection for this activity';

// Status badges.
$string['checking'] = 'Checking...';
$string['error_short'] = 'Error';
$string['viewreport'] = 'View similarity report';
$string['ai_badge_title'] = 'Advisory AI-authorship likelihood - view report for details';

// Student disclosure.
$string['student_disclosure'] = 'Your submission will be checked for originality using the Dual-Tier plagiarism detection system. Submitted files are analysed and compared against other submissions.';

// Tasks.
$string['task_submit_file'] = 'Submit file for plagiarism detection';
$string['task_check_results'] = 'Check plagiarism detection results';
$string['task_poll_result'] = 'Poll plagiarism detection result (fast ad-hoc)';

// Report page.
$string['report_title'] = 'Similarity Report';
$string['report_summary'] = 'Summary';
$string['report_scores'] = 'Detection Scores';
$string['report_matches'] = 'Matched Passages';
$string['report_status'] = 'Status';
$string['report_score'] = 'Similarity Score';
$string['report_tier'] = 'Tier Resolved';
$string['report_plagiarised'] = 'Flagged as Plagiarism';
$string['report_file'] = 'File';
$string['report_tier1_score'] = 'Tier 1 Score (Lexical)';
$string['report_tier2_score'] = 'Tier 2 Score (Semantic)';
$string['report_final_score'] = 'Final Score';
$string['report_escalated'] = 'Escalated to Tier 2';
$string['report_processing_time'] = 'Processing Time';
$string['report_match_num'] = 'Match {$a}';
$string['report_submitted'] = 'Submitted text';
$string['report_source'] = 'Source text';
$string['report_ai_heading'] = 'AI-Generated Content Likelihood (Advisory)';
$string['report_ai_score'] = 'AI-Authorship Likelihood';
$string['report_ai_verdict'] = 'Verdict';
$string['report_ai_model'] = 'Detector Model';
$string['report_ai_disclaimer'] = 'This score is an advisory signal only, not a determination of academic misconduct. AI-text detectors -- including this one -- are known to produce false positives, particularly for non-native English writers. Use this as a prompt for a conversation with the student, not as standalone evidence.';
$string['ai_verdict_likely_human'] = 'Likely human-written';
$string['ai_verdict_uncertain'] = 'Uncertain';
$string['ai_verdict_likely_ai'] = 'Possible AI involvement';

// Capabilities.
$string['dualtier:viewreport'] = 'View plagiarism similarity reports';
$string['dualtier:enable'] = 'Enable/disable plagiarism detection for activities';

// Privacy.
$string['privacy:metadata:table'] = 'Records of files submitted for plagiarism checking.';
$string['privacy:metadata:cmid'] = 'The course module ID where the submission was made.';
$string['privacy:metadata:userid'] = 'The ID of the user who submitted the file.';
$string['privacy:metadata:identifier'] = 'A hash of the file content.';
$string['privacy:metadata:filename'] = 'The name of the submitted file.';
$string['privacy:metadata:similarityscore'] = 'The similarity score returned by the detection system.';
$string['privacy:metadata:status'] = 'The processing status of the submission.';
$string['privacy:metadata:filecontent'] = 'The file content is sent to the detection backend for analysis.';
$string['privacy:metadata:backend'] = 'File content is transmitted to the plagiarism detection backend for processing.';
