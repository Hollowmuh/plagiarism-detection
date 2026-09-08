<?php
/**
 * One-shot script: create test teacher + students + course + assignment with dualtier enabled.
 * Run inside the moodle container:
 *   php /usr/src/moodle/setup_test_data.php
 */

define('CLI_SCRIPT', true);
require(__DIR__ . '/config.php');
$CFG->debug = E_ALL;
$CFG->debugdisplay = 1;
set_debugging(DEBUG_DEVELOPER, true);
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/lib/enrollib.php');
require_once($CFG->dirroot . '/lib/modinfolib.php');
require_once($CFG->dirroot . '/mod/assign/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');

global $DB, $CFG, $USER;

// Run as admin.
$USER = get_admin();

// ─── 1. Create users ─────────────────────────────────────────────
function ensure_user($username, $firstname, $lastname, $email, $password) {
    global $DB, $CFG;
    $existing = $DB->get_record('user', ['username' => $username]);
    if ($existing) {
        echo "  user '$username' already exists (id={$existing->id})\n";
        return $existing;
    }
    $user = (object)[
        'username' => $username,
        'auth' => 'manual',
        'firstname' => $firstname,
        'lastname' => $lastname,
        'email' => $email,
        'confirmed' => 1,
        'mnethostid' => $CFG->mnet_localhost_id,
        'password' => $password,  // user_create_user will hash this
        'timecreated' => time(),
        'lang' => 'en',
    ];
    $user->id = user_create_user($user, true, false);
    echo "  created user '$username' (id={$user->id})\n";
    return $user;
}

echo "== Creating users ==\n";
$teacher = ensure_user('teacher1', 'Tina', 'Teacher', 'teacher1@example.com', 'Teacher123!');
$student1 = ensure_user('student1', 'Sam', 'Student', 'student1@example.com', 'Student123!');
$student2 = ensure_user('student2', 'Sara', 'Student', 'student2@example.com', 'Student123!');
$student3 = ensure_user('student3', 'Sid', 'Student', 'student3@example.com', 'Student123!');

// ─── 2. Create course ────────────────────────────────────────────
echo "\n== Creating course ==\n";
$course = $DB->get_record('course', ['shortname' => 'PLAG101']);
if ($course) {
    echo "  course 'PLAG101' already exists (id={$course->id})\n";
} else {
    $data = (object)[
        'fullname' => 'Plagiarism Test Course',
        'shortname' => 'PLAG101',
        'category' => 1,                  // Default Miscellaneous category
        'summary' => 'Course for testing the dualtier plagiarism plugin.',
        'summaryformat' => FORMAT_HTML,
        'format' => 'topics',
        'numsections' => 3,
        'startdate' => time(),
        'visible' => 1,
    ];
    $course = create_course($data);
    echo "  created course 'PLAG101' (id={$course->id})\n";
}

// ─── 3. Enroll users ─────────────────────────────────────────────
echo "\n== Enrolling users ==\n";
$manual = enrol_get_plugin('manual');
$enrolinstance = $DB->get_record('enrol', ['courseid' => $course->id, 'enrol' => 'manual'], '*', MUST_EXIST);

$teacherroleid = $DB->get_field('role', 'id', ['shortname' => 'editingteacher']);
$studentroleid = $DB->get_field('role', 'id', ['shortname' => 'student']);

function ensure_enrolled($manual, $enrolinstance, $user, $roleid, $label) {
    global $DB;
    $context = \context_course::instance($enrolinstance->courseid);
    if (is_enrolled($context, $user)) {
        echo "  $label '{$user->username}' already enrolled\n";
        return;
    }
    $manual->enrol_user($enrolinstance, $user->id, $roleid);
    echo "  enrolled $label '{$user->username}' (role=$roleid)\n";
}

ensure_enrolled($manual, $enrolinstance, $teacher,  $teacherroleid, 'teacher');
ensure_enrolled($manual, $enrolinstance, $student1, $studentroleid, 'student');
ensure_enrolled($manual, $enrolinstance, $student2, $studentroleid, 'student');
ensure_enrolled($manual, $enrolinstance, $student3, $studentroleid, 'student');

// ─── 4. Create assignment activity with dualtier enabled ─────────
echo "\n== Creating assignment ==\n";

$existing_cm = $DB->get_record_sql(
    "SELECT cm.* FROM {course_modules} cm
     JOIN {modules} m ON m.id = cm.module
     JOIN {assign} a ON a.id = cm.instance
     WHERE cm.course = ? AND m.name = 'assign' AND a.name = ?",
    [$course->id, 'Test Plagiarism Assignment']
);

if ($existing_cm) {
    echo "  assignment 'Test Plagiarism Assignment' already exists (cmid={$existing_cm->id})\n";
    $cmid = $existing_cm->id;
} else {
    $moduleid = $DB->get_field('modules', 'id', ['name' => 'assign'], MUST_EXIST);
    $moduleinfo = (object)[
        'modulename' => 'assign',
        'module' => $moduleid,
        'course' => $course->id,
        'section' => 1,
        'name' => 'Test Plagiarism Assignment',
        'intro' => '<p>Submit a .txt file. The dualtier plagiarism plugin will analyze it.</p>',
        'introformat' => FORMAT_HTML,
        'visible' => 1,
        'visibleoncoursepage' => 1,
        // Plagiarism plugin enable flag (lib.php save_form_elements reads this).
        'plagiarism_dualtier_enabled' => 1,
        // Assignment submission options:
        'submissiondrafts' => 0,
        'requiresubmissionstatement' => 0,
        'sendnotifications' => 0,
        'sendlatenotifications' => 0,
        'duedate' => 0,
        'allowsubmissionsfromdate' => 0,
        'grade' => 100,
        'cutoffdate' => 0,
        'gradingduedate' => 0,
        'teamsubmission' => 0,
        'requireallteammemberssubmit' => 0,
        'teamsubmissiongroupingid' => 0,
        'blindmarking' => 0,
        'attemptreopenmethod' => 'none',
        'maxattempts' => -1,
        'markingworkflow' => 0,
        'markingallocation' => 0,
        // Submission plugin: file uploads
        'assignsubmission_file_enabled' => 1,
        'assignsubmission_file_maxfiles' => 1,
        'assignsubmission_file_maxsizebytes' => 10485760,    // 10 MB
        'assignsubmission_file_filetypes' => '.txt,.pdf,.docx',
        // Submission plugin: online text
        'assignsubmission_onlinetext_enabled' => 0,
        'assignsubmission_onlinetext_wordlimit' => 0,
        'assignsubmission_onlinetext_wordlimit_enabled' => 0,
        // Submission plugin: comments
        'assignsubmission_comments_enabled' => 0,
        // Feedback plugins (required by add_moduleinfo)
        'assignfeedback_comments_enabled' => 1,
        'assignfeedback_file_enabled' => 0,
        'assignfeedback_offline_enabled' => 0,
        'assignfeedback_comments_commentinline' => 0,
    ];

    $courseobj = $DB->get_record('course', ['id' => $course->id], '*', MUST_EXIST);
    $moduleinfo = add_moduleinfo($moduleinfo, $courseobj);
    $cmid = $moduleinfo->coursemodule;
    echo "  created assignment 'Test Plagiarism Assignment' (cmid={$cmid}, assignid={$moduleinfo->instance})\n";

    // Verify dualtier config row was inserted by lib.php save_form_elements.
    $plagconfig = $DB->get_record('plagiarism_dualtier_config', ['cmid' => $cmid]);
    if (!$plagconfig) {
        // save_form_elements wasn't called via this path — insert directly.
        $DB->insert_record('plagiarism_dualtier_config', (object)[
            'cmid' => $cmid,
            'enabled' => 1,
        ]);
        echo "  manually enabled dualtier on cmid={$cmid}\n";
    } else {
        echo "  dualtier already enabled on cmid={$cmid}\n";
    }
}

echo "\n== Summary ==\n";
echo "  Course URL:     {$CFG->wwwroot}/course/view.php?id={$course->id}\n";
echo "  Assignment URL: {$CFG->wwwroot}/mod/assign/view.php?id={$cmid}\n";
echo "  Teacher:        teacher1 / Teacher123!\n";
echo "  Student 1:      student1 / Student123!\n";
echo "  Student 2:      student2 / Student123!\n";
echo "  Student 3:      student3 / Student123!\n";
echo "  Admin:          admin / Admin123! (per docker-compose env)\n";
echo "\nDone.\n";
