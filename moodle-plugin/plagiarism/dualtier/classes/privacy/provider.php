<?php
namespace plagiarism_dualtier\privacy;

defined('MOODLE_INTERNAL') || die();

use core_privacy\local\metadata\collection;
use core_privacy\local\request\contextlist;
use core_privacy\local\request\approved_contextlist;
use core_privacy\local\request\userlist;
use core_privacy\local\request\approved_userlist;
use core_privacy\local\request\writer;

/**
 * GDPR privacy provider for plagiarism_dualtier.
 */
class provider implements
    \core_privacy\local\metadata\provider,
    \core_privacy\local\request\plugin\provider,
    \core_privacy\local\request\core_userlist_provider {

    /**
     * Describe the data stored by this plugin.
     */
    public static function get_metadata(collection $collection): collection {
        $collection->add_database_table('plagiarism_dualtier_files', [
            'cmid' => 'privacy:metadata:cmid',
            'userid' => 'privacy:metadata:userid',
            'identifier' => 'privacy:metadata:identifier',
            'filename' => 'privacy:metadata:filename',
            'similarityscore' => 'privacy:metadata:similarityscore',
            'status' => 'privacy:metadata:status',
        ], 'privacy:metadata:table');

        $collection->add_external_location_link('plagiarism_dualtier_backend', [
            'file_content' => 'privacy:metadata:filecontent',
            'userid' => 'privacy:metadata:userid',
        ], 'privacy:metadata:backend');

        return $collection;
    }

    /**
     * Get the list of contexts that contain user data.
     */
    public static function get_contexts_for_userid(int $userid): contextlist {
        $contextlist = new contextlist();

        $sql = "SELECT ctx.id
                  FROM {plagiarism_dualtier_files} f
                  JOIN {course_modules} cm ON cm.id = f.cmid
                  JOIN {context} ctx ON ctx.instanceid = cm.id AND ctx.contextlevel = :contextlevel
                 WHERE f.userid = :userid";

        $contextlist->add_from_sql($sql, [
            'contextlevel' => CONTEXT_MODULE,
            'userid' => $userid,
        ]);

        return $contextlist;
    }

    /**
     * Get the list of users within a context.
     */
    public static function get_users_in_context(userlist $userlist): void {
        $context = $userlist->get_context();

        if ($context->contextlevel != CONTEXT_MODULE) {
            return;
        }

        $sql = "SELECT f.userid
                  FROM {plagiarism_dualtier_files} f
                 WHERE f.cmid = :cmid";

        $userlist->add_from_sql('userid', $sql, ['cmid' => $context->instanceid]);
    }

    /**
     * Export user data for the given contexts.
     */
    public static function export_user_data(approved_contextlist $contextlist): void {
        global $DB;

        $userid = $contextlist->get_user()->id;

        foreach ($contextlist->get_contexts() as $context) {
            if ($context->contextlevel != CONTEXT_MODULE) {
                continue;
            }

            $records = $DB->get_records('plagiarism_dualtier_files', [
                'cmid' => $context->instanceid,
                'userid' => $userid,
            ]);

            foreach ($records as $record) {
                $data = (object) [
                    'filename' => $record->filename,
                    'status' => $record->status,
                    'similarityscore' => $record->similarityscore,
                    'tier_resolved' => $record->tier_resolved,
                    'is_plagiarised' => $record->is_plagiarised,
                    'timecreated' => transform::datetime($record->timecreated),
                ];

                writer::with_context($context)->export_data(
                    [get_string('pluginname', 'plagiarism_dualtier')],
                    $data
                );
            }
        }
    }

    /**
     * Delete all user data in a context.
     */
    public static function delete_data_for_all_users_in_context(\context $context): void {
        global $DB;

        if ($context->contextlevel != CONTEXT_MODULE) {
            return;
        }

        $DB->delete_records('plagiarism_dualtier_files', ['cmid' => $context->instanceid]);
    }

    /**
     * Delete user data for approved contexts.
     */
    public static function delete_data_for_user(approved_contextlist $contextlist): void {
        global $DB;

        $userid = $contextlist->get_user()->id;

        foreach ($contextlist->get_contexts() as $context) {
            if ($context->contextlevel != CONTEXT_MODULE) {
                continue;
            }

            $DB->delete_records('plagiarism_dualtier_files', [
                'cmid' => $context->instanceid,
                'userid' => $userid,
            ]);
        }
    }

    /**
     * Delete user data for approved users in a context.
     */
    public static function delete_data_for_users(approved_userlist $userlist): void {
        global $DB;

        $context = $userlist->get_context();
        if ($context->contextlevel != CONTEXT_MODULE) {
            return;
        }

        [$insql, $params] = $DB->get_in_or_equal($userlist->get_userids(), SQL_PARAMS_NAMED);
        $params['cmid'] = $context->instanceid;

        $DB->delete_records_select('plagiarism_dualtier_files',
            "cmid = :cmid AND userid {$insql}", $params);
    }
}
