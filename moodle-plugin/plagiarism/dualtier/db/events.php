<?php
defined('MOODLE_INTERNAL') || die();

$observers = [
    [
        'eventname' => '\assignsubmission_file\event\assessable_uploaded',
        'callback'  => 'plagiarism_dualtier\observer::file_uploaded',
    ],
    [
        'eventname' => '\assignsubmission_onlinetext\event\assessable_uploaded',
        'callback'  => 'plagiarism_dualtier\observer::file_uploaded',
    ],
];
