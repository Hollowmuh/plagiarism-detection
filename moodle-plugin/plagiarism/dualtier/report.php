<?php
require_once(__DIR__ . '/../../config.php');
require_once($CFG->dirroot . '/plagiarism/dualtier/lib.php');

$id = required_param('id', PARAM_INT);       // plagiarism_dualtier_files.id
$cmid = required_param('cmid', PARAM_INT);   // Course module ID

// Security checks.
$cm = get_coursemodule_from_id('', $cmid, 0, false, MUST_EXIST);
$course = $DB->get_record('course', ['id' => $cm->course], '*', MUST_EXIST);
require_login($course, true, $cm);

$context = context_module::instance($cmid);
require_capability('plagiarism/dualtier:viewreport', $context);

// Get the record.
$record = $DB->get_record('plagiarism_dualtier_files', ['id' => $id], '*', MUST_EXIST);

// Cross-check that the record actually belongs to the module we just
// authorized against -- $id and $cmid are independent, attacker-supplied
// URL parameters. Without this, a user with viewreport in ANY module could
// view ANY other module's report (any course, any student) by pairing an
// authorized $cmid with an arbitrary $id. See
// evaluation/reports/07_full_pipeline_audit.md, finding 1.
if ((int) $record->cmid !== $cmid) {
    throw new \moodle_exception('invalidrecord', 'error', '', null,
        'Report record does not belong to the specified course module');
}

// Page setup.
$PAGE->set_url('/plagiarism/dualtier/report.php', ['id' => $id, 'cmid' => $cmid]);
$PAGE->set_context($context);
$PAGE->set_title(get_string('report_title', 'plagiarism_dualtier'));
$PAGE->set_heading(get_string('report_title', 'plagiarism_dualtier'));
$PAGE->requires->css('/plagiarism/dualtier/styles.css');

echo $OUTPUT->header();

// Summary section.
$score = round(($record->similarityscore ?? 0) * 100);
$tier = $record->tier_resolved ?? '-';
$isplagiarised = (bool) $record->is_plagiarised;
$plagiarised = $isplagiarised ? get_string('yes') : get_string('no');
$status = $record->status;

if ($score < 30) {
    $gaugecolor = 'var(--dt-green)';
} else if ($score < 70) {
    $gaugecolor = 'var(--dt-orange)';
} else {
    $gaugecolor = 'var(--dt-red)';
}

echo html_writer::start_div('dualtier-report');

// ── Hero card: score gauge + verdict pills ─────────────────────
echo html_writer::start_div('dualtier-card dualtier-hero');

echo html_writer::div(
    html_writer::span($score . '%<small>' . get_string('report_score', 'plagiarism_dualtier') . '</small>',
        'dualtier-gauge-value'),
    'dualtier-gauge',
    ['style' => "--pct: {$score}; --gauge-color: {$gaugecolor};"]
);

echo html_writer::start_div('dualtier-hero-body');
echo html_writer::tag('h3', get_string('report_title', 'plagiarism_dualtier'), ['class' => 'dualtier-hero-title']);

echo html_writer::start_div('dualtier-hero-meta');
echo html_writer::span($status, 'dualtier-pill');
if ($tier !== '-') {
    echo html_writer::span($tier, 'dualtier-pill');
}
echo html_writer::span(
    get_string('report_plagiarised', 'plagiarism_dualtier') . ': ' . $plagiarised,
    'dualtier-pill ' . ($isplagiarised ? 'dualtier-pill-verdict-yes' : 'dualtier-pill-verdict-no')
);
echo html_writer::end_div(); // hero-meta

echo html_writer::tag('p', s($record->filename ?? '-'), ['class' => 'dualtier-filename']);
echo html_writer::end_div(); // hero-body

echo html_writer::end_div(); // hero card

// Detailed results from cached report data.
if (!empty($record->reportdata)) {
    $report = json_decode($record->reportdata);

    if ($report) {
        // ── Detection breakdown: stat grid ──────────────────────
        echo html_writer::start_div('dualtier-card');
        echo html_writer::tag('p', get_string('report_scores', 'plagiarism_dualtier'), ['class' => 'dualtier-card-title']);

        echo html_writer::start_div('dualtier-stat-grid');

        $stats = [
            [get_string('report_tier1_score', 'plagiarism_dualtier'),
             $report->tier1_score !== null ? round($report->tier1_score * 100) . '%' : '-'],
            [get_string('report_tier2_score', 'plagiarism_dualtier'),
             $report->tier2_score !== null ? round($report->tier2_score * 100) . '%' : '-'],
            [get_string('report_final_score', 'plagiarism_dualtier'),
             round($report->final_score * 100) . '%'],
            [get_string('report_escalated', 'plagiarism_dualtier'),
             $report->escalated ? get_string('yes') : get_string('no')],
            [get_string('report_processing_time', 'plagiarism_dualtier'),
             ($report->processing_time_ms ?? '-') . ' ms'],
        ];
        foreach ($stats as [$label, $value]) {
            echo html_writer::start_div('dualtier-stat');
            echo html_writer::tag('p', $label, ['class' => 'dualtier-stat-label']);
            echo html_writer::tag('p', $value, ['class' => 'dualtier-stat-value']);
            echo html_writer::end_div();
        }

        echo html_writer::end_div(); // stat-grid
        echo html_writer::end_div(); // card

        // ── Matched passages ─────────────────────────────────────
        if (!empty($report->matches)) {
            echo html_writer::start_div('dualtier-card');
            echo html_writer::tag('p', get_string('report_matches', 'plagiarism_dualtier'), ['class' => 'dualtier-card-title']);

            foreach ($report->matches as $i => $match) {
                $matchnum = $i + 1;
                $matchscore = round($match->similarity_score * 100);
                $matchtype = s($match->match_type);

                echo html_writer::start_div('dualtier-match');

                echo html_writer::start_div('dualtier-match-header');
                echo html_writer::tag('h4', get_string('report_match_num', 'plagiarism_dualtier', $matchnum) . " ({$matchtype})");
                echo html_writer::span("{$matchscore}%", 'dualtier-match-score');
                echo html_writer::end_div(); // match-header

                if (!empty($match->matched_segments)) {
                    foreach ($match->matched_segments as $seg) {
                        echo html_writer::start_div('dualtier-comparison');
                        echo html_writer::start_div('dualtier-side');
                        echo html_writer::tag('strong', get_string('report_submitted', 'plagiarism_dualtier'));
                        echo html_writer::tag('p', s($seg->submitted_text ?? ''));
                        echo html_writer::end_div();

                        echo html_writer::start_div('dualtier-side');
                        echo html_writer::tag('strong', get_string('report_source', 'plagiarism_dualtier'));
                        echo html_writer::tag('p', s($seg->source_text ?? ''));
                        echo html_writer::end_div();
                        echo html_writer::end_div();
                    }
                } else {
                    // Tier 1 matches on fingerprints, which keep no text
                    // offsets, so there is no passage to show.
                    echo html_writer::tag('p', get_string(
                        $match->match_type === 'tier1' ? 'report_no_passage_tier1' : 'report_no_passage',
                        'plagiarism_dualtier'));
                }

                echo html_writer::end_div(); // match
            }

            echo html_writer::end_div(); // card
        }

        // AI-generated-content likelihood: an independent, advisory-only
        // signal, deliberately rendered in its own section rather than
        // folded into the similarity scores above. See
        // docs/2026-07-01/ai_detection_tier_1426.md for why.
        if (!empty($report->ai_detection)) {
            $ai = $report->ai_detection;
            $aiscore = round($ai->ai_score * 100);
            $verdictstr = get_string('ai_verdict_' . $ai->verdict, 'plagiarism_dualtier');

            echo html_writer::start_div('dualtier-card');
            echo html_writer::tag('p', get_string('report_ai_heading', 'plagiarism_dualtier'), ['class' => 'dualtier-card-title']);

            echo html_writer::start_div('dualtier-ai-score-row');
            echo html_writer::span("{$aiscore}%", 'dualtier-ai-score-value');
            echo html_writer::start_div();
            echo html_writer::tag('p', $verdictstr, ['class' => 'dualtier-stat-value', 'style' => 'margin:0;']);
            echo html_writer::tag('p', get_string('report_ai_model', 'plagiarism_dualtier') . ': ' . s($ai->model_name),
                ['class' => 'dualtier-stat-label', 'style' => 'margin:2px 0 0;']);
            echo html_writer::end_div();
            echo html_writer::end_div(); // ai-score-row

            echo html_writer::tag('p', get_string('report_ai_disclaimer', 'plagiarism_dualtier'),
                ['class' => 'dualtier-ai-disclaimer']);

            echo html_writer::end_div(); // card
        }
    }
}

echo html_writer::end_div(); // dualtier-report

echo $OUTPUT->footer();
