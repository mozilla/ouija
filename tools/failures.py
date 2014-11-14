import json
import re
import copy
import httplib
import datetime

def removeType(master, targetlist):
    """
        Given a master dictionary of:
           key: failure id (unique bugid comment representing revision)
           value: array of instance tuples that meet this requirement

        iterate through each key and remove matching targetlist items 
    """
    if targetlist == []:
        return master

    removed = {}
    for row in master:
        if targetlist[0] in master[row]:
            if row not in removed:
                removed[row] = []
            removed[row].append(targetlist[0])


    for row in removed:
        for item in removed[row]:
            master[row].remove(item)
        if len(master[row]) == 0:
            del master[row]

    return master, removed

def addType(master, toAdd):
    for row in toAdd:
        if row not in master:
            master[row] = []

        master[row].extend(toAdd[row])

    return master

def bruteForcePercentage(total, scenarios, master, results, levels):
    """
        This is one level deep for brute force calculations.

        We take an array of scenarios (in tuple format), and for each one
        we test a removal of this specific scenario and record the scenario
        in a dictionary of results with this format:
           Key: percent match (i.e 99)
           Value: list of tuple sets which can be removed and allow us to gain [Key] coverage
    """
    for scenario in scenarios:
        temp, removed = removeType(master, scenario)

        p = int((float(len(temp)) / total) * 100)
        if p not in results:
            results[p] = []
        results[p].append(levels + scenario)
        master = addType(master, removed)
    return results
    

def removeBadScenarios(results, threshold):
    """
        Given a threshold, remove anything from a results dictionary
        that is below the threshold.  Results dictionary format is:
            Key: percent match (i.e 99)
            Value: list of tuple sets which can be removed and allow us to gain [Key] coverage

        This is used as an optimization, so we focus on important scenarios

        Return value is a Results dictionary
    """
    retVal = {}
    for percent in results:
        if percent >= threshold:
            retVal[percent] = results[percent]

    return retVal

def buildScenarios(results):
    """
        Given a Results dictionary, build a list of all unique scenarios
        in a list format
    """
    retVal = []
    for row in results:
        for item in results[row]:
            if item not in retVal:
                retVal.append(item)
    return retVal

def sortList(input):
    """
        Given a list of 3 part tuples, sort them and remove duplicates.

        TODO: this is the ugliest code, there must be a better way to do this.
        TODO: this is hardcoded for a 3 part tuple
    """
    retVal = []
    for item in input:
       if isinstance(item[0], list):
           sorted = sortList(item)
           if not sorted in retVal:
               retVal.append(sorted)
       else:
           count = 0
           if item in retVal:
               continue
           for iter in retVal:
               if item[0] < iter[0]:
                   retVal.insert(count, item)
                   break
               elif (item[0] == iter[0]) and \
                    (item[1] < iter[1]):
                   retVal.insert(count, item)
                   break
               elif (item[0] == iter[0]) and \
                    (item[1] == iter[1]) and \
                    (item[2] < iter[2]):
                   retVal.insert(count, item)
                   break
               elif (item[0] == iter[0]) and \
                    (item[1] == iter[1]) and \
                    (item[2] == iter[2]):
                   break
               count += 1
           if count >= len(retVal):
               retVal.append(item)

    return retVal

def mergeResults(original, new):
    """
        Given two Results Dictionaries, merge together to a unified dict.

        TODO: there has to be a built in function for this.
        TODO: do we have duplicates here?
    """
    if new == {}:
        retVal = {}
    else:
        retVal = copy.deepcopy(new)

    for item in original:
        if item in retVal:
            for tuple in original[item]:
                if tuple not in retVal[item]:
                    retVal[item].append(tuple)
        else:
            retVal[item] = original[item]

    return retVal

def getRawData(jobtype):
    """
        This pulls a query from the database and builds up our data dict
        in this format:
           Key: unique bugid (revision of bad change)
           Value: tuple (platform, buildtype, testtype) that is related to key

        We build this up for all platforms that we care about.

        Inputs:
            jobtype: key for the regression column in the db: -2, -1, 1

    """
    platforms, buildtypes, testtypes = getDistinctTuples(jobtype)

    # TODO: these dates are hardcoded to 60 days
    old = datetime.date.today() - datetime.timedelta(days=60)
    now = datetime.datetime.today()
    startDate = '%s-%02d-%02d' % (old.year, old.month, old.day)
    endDate = '%s-%02d-%02d' % (now.year, now.month, now.day)

    conn = httplib.HTTPConnection('alertmanager.allizom.org')
    cset = "/data/seta/?jobtype=%s&startDate=%s&endDate=%s" % (jobtype, startDate, endDate)
    p = '&platform='.join(platforms)
    b = '&build='.join(buildtypes)
    t = '&test='.join(testtypes)
    if p:
        cset += "&platform=" + p
    if b:
        cset += "&build=" + b
    if t:
        cset += "&test=" + t

    print cset
    conn.request("GET", cset)
    response = conn.getresponse()

    data = response.read()
    response.close()
    cdata = json.loads(data)

    print json.dumps(cdata)
    return cdata['failures']


def getDistinctTuples(jobtype):
#    platforms = ['linux32','linux64','winxp','win7','osx10.6']
    platforms = ['linux32','linux64']
    testtypes = ['mochitest-1', 'mochitest-2', 'mochitest-3', 'mochitest-4', 'mochitest-5']
    testtypes = ['mochitest-1']
    buildtypes = ['opt', 'debug']

    return platforms, buildtypes, testtypes
    
def buildMasterScenarioList(jobtype):
    retVal = []
    platforms, buildtypes, testtypes = getDistinctTuples(jobtype)

    for p in platforms:
        for b in buildtypes:
            for t in testtypes:
                retVal.append([[p, b, t]])

    return retVal

def findPercentage(jobtype):
    failures = getRawData(jobtype)
    total = len(failures)
    print "working with %s failures" % total

    scenarios = buildMasterScenarioList(jobtype)

    depth_level = 2
    depth = 0
    results = {}
    filtered_scenarios = [[]]
    while depth < depth_level:
        depth += 1
        tempResults = {}
        l2scenarios = copy.deepcopy(scenarios)
        count = 0
        for scenario in filtered_scenarios:
            count += 1
            temp = copy.deepcopy(failures)
            if scenario == []:
                filtered_scenarios = copy.deepcopy(scenarios)
                l2scenarios = copy.deepcopy(scenarios)

            add_to_scenario = []
            for i in scenario:
                temp, removed = removeType(temp, [i])
                if [i] in l2scenarios:
                    l2scenarios.remove([i])
                    add_to_scenario.append([i])

            tempResults = bruteForcePercentage(total, l2scenarios, temp, tempResults, scenario)

            l2scenarios.extend(add_to_scenario)

        tempResults = removeBadScenarios(tempResults, 99)
        filtered_scenarios = buildScenarios(tempResults)
        results = tempResults
        print "finished round %s with %s(%s) scenarios, %s" % (depth, len(l2scenarios), len(scenarios), len(filtered_scenarios))
        

    print "\n\nsummary of choices:"
    for index in sorted(results.iterkeys()):
        l = sortList(results[index])
        print "%s%% detection, %s choices- removing any of these configs:" % (index, len(l))
        for i in l:
            print "  * %s" % i

if __name__ == "__main__":
    jobtype = 1 # code for build job type
    findPercentage(jobtype)

