import requests
import json
import copy
import logging
import os

LOG = logging.getLogger(__name__)
BIT_MASK_8BIT = 255
BUILDTYPE_BYTE_SHIFT = 8
TESTTYPE_BYTE_SHIFT = 16
# globals used for maps_to_indexes - this stores a unique value for every
# possible job as an array, then we use the array index and map to a bit
# field.  See map_to_indexes for more details.
PLATFORMS = []
BUILDTYPES = []
TESTTYPES = []


def map_to_text(bitmaskData):
    """
       bitmaskData is a 32 bit integer, ex:
       bitmaskData = 197121
       testtype = 3
       buildtype = 2
       platform = 1
    """
    return [PLATFORMS[bitmaskData & BIT_MASK_8BIT],
            BUILDTYPES[(bitmaskData >> BUILDTYPE_BYTE_SHIFT) & BIT_MASK_8BIT],
            TESTTYPES[(bitmaskData >> TESTTYPE_BYTE_SHIFT)]]


def map_to_indexes(data):
    global PLATFORMS
    global BUILDTYPES
    global TESTTYPES

    indexed_data = []
    # ideally we can just use the index of this data, but we need to map to failures as well
    for item in data:
        if item[0] not in PLATFORMS:
            PLATFORMS.append(item[0])
        if item[1] not in BUILDTYPES:
            BUILDTYPES.append(item[1])
        if item[2] not in TESTTYPES:
            TESTTYPES.append(item[2])

        # platforms < 256 - 8 bit mask
        # buildtypes < 256 - 8 bit mask
        # testtypes > 256 - 16 bit mask
        # fit in a 32 bit int field- packed as platform|buildtype|testtype
        value = TESTTYPES.index(item[2]) << TESTTYPE_BYTE_SHIFT
        value += BUILDTYPES.index(item[1]) << BUILDTYPE_BYTE_SHIFT
        value += PLATFORMS.index(item[0])
        indexed_data.append(value)
    return indexed_data


def get_distinct_tuples():
    url = "http://seta-dev.herokuapp.com/data/jobtypes/"
    response = requests.get(url, headers={'accept-encoding': 'json'}, verify=True)
    data = json.loads(response.content)
    return map_to_indexes(data['jobtypes'])


def check_removal(master, removals):
    results = {}
    for failure in master:
        results[failure] = []
        for failure_job in master[failure]:
            # we will add the test to the resulting structure unless we find a match
            # in the jobtype we are trying to ignore.
            if failure_job not in removals:
                results[failure].append(failure_job)

        if len(results[failure]) == 0:
            del results[failure]

    return results


def build_removals(active_jobs, master, target):
    """
    active_jobs - all possible desktop & android jobs on Treeherder (no PGO)
    master - list of all failures
    target - number of failures we want to process

    Return list of jobs to remove and list of revisions that are regressed
    """
    low_value_jobs = []
    master_root_cause = []
    for jobtype in active_jobs:
        # Determine if removing an active job will reduce the number of failures we will catch
        # or stay the same
        remaining_failures = check_removal(master, [jobtype])

        if len(remaining_failures) >= target:
            low_value_jobs.append(jobtype)
            master = remaining_failures
        else:
            root_cause = []
            for revision in master:
                if revision not in remaining_failures:
                    root_cause.append(revision)
                    master_root_cause.append(revision)
            LOG.info("jobtype: %s is the root failure(s) of %s" %
                     (map_to_text(jobtype), root_cause))

    return low_value_jobs, master_root_cause


def remove_root_cause_failures(failures, master_root_cause):
    for revision in master_root_cause:
        del failures[revision]
    return failures


def invert_index(failures, active_jobs):
    inv_map = {}

    for revision, jobtypes in failures.iteritems():
        for job in active_jobs:
            if job in jobtypes:
                inv_map[job] = inv_map.get(job, [])
                inv_map[job].append(revision)

    maximum = 1
    for jobtype in sorted(inv_map):
        if len(inv_map[jobtype]) > maximum:
            maximum = len(inv_map[jobtype])
            max_job = jobtype

    if maximum == 1:
        return failures, None

    for revision in inv_map[max_job]:
        del failures[revision]

    return failures, max_job


def failures_by_jobtype(failures, target, ignore_failure):
    total = len(failures)
    copy_failures = copy.deepcopy(failures)
    active_jobs = get_distinct_tuples()
    target = int(total * (target / 100))
    master_root_cause = []

    job_needed = ""
    remaining_jobs = []
    while job_needed is not None:
        copy_failures, job_needed = invert_index(copy_failures, active_jobs)
        if job_needed is not None:
            remaining_jobs.append(job_needed)

    low_value_jobs = [x for x in active_jobs if str(x) not in remaining_jobs]

    while ignore_failure > 0:
        copy_failures = remove_root_cause_failures(copy_failures, master_root_cause)
        total = len(copy_failures)
        low_value_jobs, master_root_cause = build_removals(active_jobs, copy_failures, total)
        ignore_failure -= 1
    # only return high value job we want
    for low_value_job in low_value_jobs:
        try:
            active_jobs.remove(low_value_job)
        except ValueError:
            LOG.info("%s is missing from the job list" % low_value_job)
    total_detected = check_removal(failures, low_value_jobs)
    high_value_jobs = active_jobs
    return high_value_jobs, total_detected


def weighted_by_jobtype(failures, target, ignore_failure, offline):
    """
    failures - jobs that have been starred for fixing a commit or associated to a bug
    target - precentage of failures to analyze
    ignore_failure - which failures to ignore
    """
    total = len(failures)
    indexed_failures = {}
    for failure in failures:
        indexed_failures[failure] = map_to_indexes(failures[failure])

    copy_failures = copy.deepcopy(indexed_failures)
    LOG.info("working with %s failures" % total)
    # Fetch the jobtypes' endpoint
    # List of jobs (platform, platform_opt, testtype)
    # It reads the runnable API, it calculates the testtype for each build system type
    # It also skips PGO jobs
    # XXX: We could query the job priorities table and skip the PGO jobs here
    if offline:
        tuples = 'tuples.json'
        if offline and os.path.exists(tuples):
            with open(tuples, 'r') as f:
                data = json.load(f)
                map_to_indexes(data['jobtypes'])
        else:
            active_jobs = get_distinct_tuples()
    else:
        active_jobs = get_distinct_tuples()

    target = int(total * (target / 100))
    low_value_jobs, master_root_cause = build_removals(active_jobs, indexed_failures, target)

    while ignore_failure > 0:
        LOG.info("\n--------------new pass----------------\n")
        copy_failures = remove_root_cause_failures(copy_failures, master_root_cause)
        total = len(copy_failures)
        low_value_jobs, master_root_cause = build_removals(active_jobs, copy_failures, total)
        ignore_failure -= 1

    # only return high value job we want
    for low_value_job in low_value_jobs:
        try:
            active_jobs.remove(low_value_job)
        except ValueError:
            LOG.info("%s is missing from the job list" % low_value_job)

    total_detected = check_removal(indexed_failures, low_value_jobs)

    high_value_jobs = []
    for value in active_jobs:
        high_value_jobs.append(map_to_text(value))

    return high_value_jobs, total_detected
