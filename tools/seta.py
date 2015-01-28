import httplib
import json

def getDistinctTuples():
    conn = httplib.HTTPConnection('alertmanager.allizom.org')
    cset = "/data/jobtypes/"
    conn.request("GET", cset)
    response = conn.getresponse()

    data = response.read()
    response.close()
    cdata = json.loads(data)
    return cdata['jobtypes']

def is_matched(f, removals):
    found = False
    for jobtype in removals:
        matched = 0
        if f[2] == jobtype[2]:
            matched +=1
        elif jobtype[2] == '':
            matched +=1

        if f[1] == jobtype[1]:
            matched +=1
        elif jobtype[1] == '':
            matched +=1

        if f[0] == jobtype[0]:
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

def remove_bad_combos(master, scenarios, target):
    retVal = []
    temp = []
    for item in scenarios:
        temp.append(item)
        if len(check_removal(master, temp)[0]) >= target:
            retVal.append(item)
        else:
            temp.remove(item)

    return retVal

def build_removals(active_jobs, master, to_remove, target):
    retVal = []
    for jobtype in active_jobs:
        remaining_failures, total_time, saved_time = check_removal(master, [jobtype])
        if len(remaining_failures) >= target:
            retVal.append(jobtype)

    return retVal

def depth_first(failures, target):
    total = len(failures)
    print "working with %s failures" % total
    active_jobs = getDistinctTuples()

    target = int(total* (target / 100))
    to_remove = []

    to_remove = build_removals(active_jobs, failures, to_remove, target)
    to_remove = remove_bad_combos(failures, to_remove, target)

    total_detected, total_time, saved_time = check_removal(failures, to_remove)
    return to_remove, total_detected

