<?php
defined('MOODLE_INTERNAL') || die();

$tasks = [
    [
        'classname' => 'plagiarism_dualtier\task\check_results',
        'blocking'  => 0,
        'minute'    => '*/5',
        'hour'      => '*',
        'day'       => '*',
        'month'     => '*',
        'dayofweek' => '*',
    ],
];
