import requests
import json
import copy

def getDistinctTuples():
    url = "http://alertmanager.allizom.org/data/jobtypes/"
    response = requests.get(url, headers={'accept-encoding':'json'}, verify=True)
    data = json.loads(response.content)
    return data['jobtypes']


def is_matched(f, removals):
    found = False
    tocheck = [str(f[0]), str(f[1]), str(f[2])]
    for jobtype in removals:
        matched = 0
        if tocheck[2] == jobtype[2]:
            matched +=1
        elif jobtype[2] == '':
            matched +=1

        if tocheck[1] == jobtype[1]:
            matched +=1
        elif jobtype[1] == '':
            matched +=1

        if tocheck[0] == jobtype[0]:
            matched +=1
        elif jobtype[0] == '':
            matched +=1

        if matched == 3:
            found = True
            break

    return found

def check_removal(master, removals):
    results = {}
    total_time = 0.0
    saved_time = 0.0
    for failure in master:
        results[failure] = []
        for f in master[failure]:
            total_time += f[3]
            found = is_matched(f, removals)

            # we will add the test to the resulting structure unless we find a match in the jobtype we are trying to ignore.
            if found:
                saved_time += f[3]
            else:
                results[failure].append(f)

        if len(results[failure]) == 0:
            del results[failure]

    return results, total_time, saved_time


def build_removals(active_jobs, master, to_remove, target):
    retVal = []
    master_root_cause = []
    for jobtype in active_jobs:
        remaining_failures, total_time, saved_time = check_removal(master, [jobtype])
        if len(remaining_failures) >= target:
            retVal.append(jobtype)
            master = remaining_failures
        else:
            root_cause = []
            for key in master:
                if key not in remaining_failures:
                    root_cause.append(key)
                    master_root_cause.append(key)
            print "jobtype: %s, root failure(s): %s" % (jobtype, root_cause)

    return retVal, remaining_failures, master_root_cause

def remove_root_cause_failures(failures, master_root_cause):
    for revision in master_root_cause:
        del failures[revision]
    return failures

def depth_first(failures, target, ignore_failure):
    total = len(failures)
    copy_failures = copy.deepcopy(failures)
    print "working with %s failures" % total
    active_jobs = getDistinctTuples()

    target = int(total* (target / 100))
    to_remove = []

    to_remove, remaining_failures, master_root_cause = build_removals(active_jobs, failures, to_remove, target)

    while ignore_failure > 0:
        print "\n--------------new pass----------------\n"
        copy_failures = remove_root_cause_failures(copy_failures, master_root_cause)
        total = len(copy_failures)
        to_remove, remaining_failures, master_root_cause = build_removals(active_jobs, copy_failures, [], total)
        ignore_failure -= 1

    total_detected, total_time, saved_time = check_removal(failures, to_remove)
    return to_remove, total_detected

