<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {

    $settings = new admin_settingpage('plagiarism_dualtier',
        get_string('pluginname', 'plagiarism_dualtier'));

    // Global enable/disable.
    $settings->add(new admin_setting_configcheckbox(
        'plagiarism_dualtier/enabled',
        get_string('setting_enabled', 'plagiarism_dualtier'),
        get_string('setting_enabled_desc', 'plagiarism_dualtier'),
        0
    ));

    // API URL.
    $settings->add(new admin_setting_configtext(
        'plagiarism_dualtier/apiurl',
        get_string('setting_apiurl', 'plagiarism_dualtier'),
        get_string('setting_apiurl_desc', 'plagiarism_dualtier'),
        'http://localhost:8000/api/v1',
        PARAM_URL
    ));

    // API key.
    $settings->add(new admin_setting_configpasswordunmask(
        'plagiarism_dualtier/apikey',
        get_string('setting_apikey', 'plagiarism_dualtier'),
        get_string('setting_apikey_desc', 'plagiarism_dualtier'),
        ''
    ));

    // Similarity threshold (percentage to flag).
    $settings->add(new admin_setting_configtext(
        'plagiarism_dualtier/threshold',
        get_string('setting_threshold', 'plagiarism_dualtier'),
        get_string('setting_threshold_desc', 'plagiarism_dualtier'),
        '25',
        PARAM_INT
    ));

    // Tau low.
    $settings->add(new admin_setting_configtext(
        'plagiarism_dualtier/tau_low',
        get_string('setting_tau_low', 'plagiarism_dualtier'),
        get_string('setting_tau_low_desc', 'plagiarism_dualtier'),
        '0.25',
        PARAM_FLOAT
    ));

    // Tau high.
    $settings->add(new admin_setting_configtext(
        'plagiarism_dualtier/tau_high',
        get_string('setting_tau_high', 'plagiarism_dualtier'),
        get_string('setting_tau_high_desc', 'plagiarism_dualtier'),
        '0.75',
        PARAM_FLOAT
    ));

    // Cross-submission checking.
    $settings->add(new admin_setting_configcheckbox(
        'plagiarism_dualtier/crosscheck',
        get_string('setting_crosscheck', 'plagiarism_dualtier'),
        get_string('setting_crosscheck_desc', 'plagiarism_dualtier'),
        1
    ));

    $ADMIN->add('plagiarism', $settings);
}
