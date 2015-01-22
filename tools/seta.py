def getDistinctTuples():
    platforms = ['osx10.6', 'winxp', 'osx10.8', 'win7','linux32','linux64']
    testtypes = ['mochitest-1', 'mochitest-2', 'mochitest-3', 'mochitest-4', 'mochitest-5', 
                 'mochitest-other', 'reftest', 'xpcshell', 'crashtest', 'jsreftest', 'reftest-1', 'reftest-2',
                 'reftest-e10s', 'crashtest-e10s', 'jittest', 'marionette', 'mochitest-gl', 'cppunit', 'reftest-no-accel',
                 'web-platform-tests-1', 'web-platform-tests-2', 'web-platform-tests-3', 'web-platform-tests-4', 'web-platform-tests-reftests',
                 'mochitest-e10s-browser-chrome-1', 'mochitest-e10s-browser-chrome-2', 'mochitest-e10s-browser-chrome-3',
                 'mochitest-browser-chrome-1', 'mochitest-browser-chrome-2', 'mochitest-browser-chrome-3',
                 'mochitest-devtools-chrome-1', 'mochitest-devtools-chrome-2', 'mochitest-devtools-chrome-3', 'mochitest-devtools-chrome']
    buildtypes = ['debug', 'opt', 'asan']

    return platforms, buildtypes, testtypes

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

def build_removals(platforms, buildtypes, testtypes, master, to_remove, target):
    retVal = []
    for platform in platforms:
        for buildtype in buildtypes:
            if buildtype == 'asan' and platform != 'linux64':
                continue

            if [platform, buildtype, ''] in to_remove:
                retVal.append([platform, buildtype, ''])
                continue

            for test in testtypes:
                jobtype = [platform, buildtype, test]
                remaining_failures, total_time, saved_time = check_removal(master, [jobtype])
                if len(remaining_failures) >= target:
                    retVal.append(jobtype)
    return retVal

def compare_array(master, slave, query):
    retVal = []
    for m in master:
        found = False
        for tup in slave:
            if str(m) == str(tup):
                found = True
                break

        if not found:
            retVal.append(m)
            run_query(query % m)
    return retVal

def depth_first(failures, target):
    total = len(failures)
    print "working with %s failures" % total
    platforms, buildtypes, testtypes = getDistinctTuples()

    target = int(total* (target / 100))
    to_remove = []

    to_remove = build_removals(platforms, buildtypes, testtypes, failures, to_remove, target)
    to_remove = remove_bad_combos(failures, to_remove, target)

    total_detected, total_time, saved_time = check_removal(failures, to_remove)
    return to_remove, total_detected

