import requests
import json
import copy


def get_distinct_tuples():
    url = "http://alertmanager.allizom.org/data/jobtypes/"
    response = requests.get(url, headers={'accept-encoding': 'json'}, verify=True)
    data = json.loads(response.content)
    return data['jobtypes']


def is_matched(failure, removals):
    found = False
    tocheck = [str(failure[0]), str(failure[1]), str(failure[2])]
    for jobtype in removals:
        matched = 0
        if tocheck[2] == jobtype[2]:
            matched += 1
        elif jobtype[2] == '':
            matched += 1

        if tocheck[1] == jobtype[1]:
            matched += 1
        elif jobtype[1] == '':
            matched += 1

        if tocheck[0] == jobtype[0]:
            matched += 1
        elif jobtype[0] == '':
            matched += 1

        if matched == 3:
            found = True
            break

    return found


def check_removal(master, removals):
    results = {}
    for failure in master:
        results[failure] = []
        for failure_job in master[failure]:
            found = is_matched(failure_job, removals)

            # we will add the test to the resulting structure unless we find a match in the jobtype we are trying to ignore.
            if not found:
                results[failure].append(failure_job)

        if len(results[failure]) == 0:
            del results[failure]

    return results


def build_removals(active_jobs, master, target):
    ret_val = []
    master_root_cause = []
    for jobtype in active_jobs:
        remaining_failures = check_removal(master, [jobtype])
        if len(remaining_failures) >= target:
            ret_val.append(jobtype)
            master = remaining_failures
        else:
            root_cause = []
            for key in master:
                if key not in remaining_failures:
                    root_cause.append(key)
                    master_root_cause.append(key)
            print "jobtype: %s, root failure(s): %s" % (jobtype, root_cause)

    return ret_val, master_root_cause


def remove_root_cause_failures(failures, master_root_cause):
    for revision in master_root_cause:
        del failures[revision]
    return failures

def invert_index(failures, active_jobs):
    inv_map = {}

    for revision, jobtypes in failures.iteritems():
        for job in active_jobs:
            found = is_matched(job, jobtypes)
            if found:
                inv_map[str(job)] = inv_map.get(str(job), [])
                inv_map[str(job)].append(revision)

    maximum = 1
    for jobtype in sorted(inv_map):
        if len(inv_map[jobtype]) > maximum:
            maximum = len(inv_map[jobtype])
            max_job = jobtype
            revision_list = inv_map[jobtype]

    if maximum == 1:
        return failures, None

    for revision in inv_map[max_job]:
        del failures[revision]

    return failures, max_job

def failures_by_jobtype(failures, target, ignore_failure):
    total = len(failures)
    copy_failures = copy.deepcopy(failures)
    active_jobs = get_distinct_tuples()
    target = int(total* (target / 100))

    job_needed = ""
    remaining_jobs = []
    while job_needed is not None:
        copy_failures, job_needed = invert_index(copy_failures, active_jobs)
        if job_needed is not None:
            remaining_jobs.append(job_needed)

    to_remove = [x for x in active_jobs if str(x) not in remaining_jobs]

     while ignore_failure > 0:
        copy_failures = remove_root_cause_failures(copy_failures, master_root_cause)
        total = len(copy_failures)
        to_remove, master_root_cause = build_removals(active_jobs, copy_failures, total)
        ignore_failure -= 1

    total_detected = check_removal(failures, to_remove)
    return to_remove, total_detected

def weighted_by_jobtype(failures, target, ignore_failure):
    total = len(failures)
    copy_failures = copy.deepcopy(failures)
    print "working with %s failures" % total
    active_jobs = get_distinct_tuples()

    target = int(total* (target / 100))
    to_remove = []

    to_remove, master_root_cause = build_removals(active_jobs, failures, target)

    while ignore_failure > 0:
        print "\n--------------new pass----------------\n"
        copy_failures = remove_root_cause_failures(copy_failures, master_root_cause)
        total = len(copy_failures)
        to_remove, master_root_cause = build_removals(active_jobs, copy_failures, total)
        ignore_failure -= 1

    total_detected = check_removal(failures, to_remove)
    return to_remove, total_detected
