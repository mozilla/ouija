import json
import re
import copy
import httplib
import datetime
import os
import MySQLdb
import sys
from argparse import ArgumentParser
from emails import send_email

def getRawData(jobtype):
    conn = httplib.HTTPConnection('alertmanager.allizom.org')
    cset = "/data/seta/"
    conn.request("GET", cset)
    response = conn.getresponse()

    data = response.read()
    response.close()
    cdata = json.loads(data)
    return cdata['failures']

def getDistinctTuples(jobtype):
    platforms = ['osx10.6', 'winxp', 'osx10.8', 'win7','linux32','linux64']
    testtypes = ['mochitest-1', 'mochitest-2', 'mochitest-3', 'mochitest-4', 'mochitest-5', 
                 'mochitest-other', 'reftest', 'xpcshell', 'crashtest', 'jsreftest', 'reftest-ipc', 'crashtest-ipc',
                 'mochitest-browser-chrome-1', 'mochitest-browser-chrome-2', 'mochitest-browser-chrome-3',
                 'mochitest-devtools-chrome-1', 'mochitest-devtools-chrome-2', 'mochitest-devtools-chrome-3', 'mochitest-devtools-chrome']
    buildtypes = ['debug', 'opt']

    return platforms, buildtypes, testtypes

def is_matched(f, removals):
    found = False
    for tuple in removals:
        matched = 0
        if f[2] == tuple[2]:
            matched +=1
        elif tuple[2] == '':
            matched +=1

        if f[1] == tuple[1]:
            matched +=1
        elif tuple[1] == '':
            matched +=1

        if f[0] == tuple[0]:
            matched +=1
        elif tuple[0] == '':
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

            # we will add the test to the resulting structure unless we find a match in the tuple we are trying to ignore.
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


def format_in_table(platforms, buildtypes, testtypes, master):
    results = {}
    sum_removed = 0
    sum_remaining = 0

    for platform in platforms:
        for buildtype in buildtypes:
            key = "%s_%s" % (platform, buildtype)
            if key not in results:
                results[key] = []

            for item in master:
                if item[0] == platform and item[1] == buildtype:
                    results[key].append(item[2])

    tbplnames = {'mochitest-1': 'm1',
                 'mochitest-2': 'm2',
                 'mochitest-3': 'm3',
                 'mochitest-4': 'm4',
                 'mochitest-5': 'm5',
                 'mochitest-other': 'mOth',
                 'xpcshell': 'X',
                 'crashtest': 'C',
                 'jsreftest': 'J',
                 'mochitest-browser-chrome-1': 'bc1',
                 'mochitest-browser-chrome-2': 'bc2',
                 'mochitest-browser-chrome-3': 'bc3',
                 'mochitest-devtools-chrome-1': 'dt1',
                 'mochitest-devtools-chrome-2': 'dt2',
                 'mochitest-devtools-chrome-3': 'dt3',
                 'mochitest-devtools-chrome': 'dt',
                 'reftest-ipc': 'Ripc',
                 'crashtest-ipc': 'Cipc',
                 'reftest': 'R'}

    keys = results.keys()
    keys.sort()
    for key in keys:
        data = results[key]
        data.sort()
        output = ""
        for test in testtypes:
            output += '\t'
            if test in data or '' in data:
                output += tbplnames[test]
                sum_removed += 1
            else:
                output += "--"
                sum_remaining += 1

        modifier = ""
        if len(data) == len(testtypes):
            modifier = "*"

        print "%s%s%s" % (key, modifier, output)
    print "Total removed %s" % (sum_removed)
    print "Total remaining %s" % (sum_remaining)
    print "Total jobs %s" % (sum_removed + sum_remaining)

def build_removals(platforms, buildtypes, testtypes, master, to_remove, target):
    retVal = []
    for platform in platforms:
        for buildtype in buildtypes:
            if [platform, buildtype, ''] in to_remove:
                retVal.append([platform, buildtype, ''])
                continue

            for test in testtypes:
                tuple = [platform, buildtype, test]
                remaining_failures, total_time, saved_time = check_removal(master, [tuple])
                if len(remaining_failures) >= target:
                    retVal.append(tuple)
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

def depth_first(jobtype, target, options):
    failures = getRawData(jobtype)
    total = len(failures)
    print "working with %s failures" % total
    platforms, buildtypes, testtypes = getDistinctTuples(jobtype)

    target = int(total* (target / 100))
    to_remove = []

    # check large vectors first - entire platform/buildtypes
    to_remove = build_removals(platforms, buildtypes, [''], failures, to_remove, target)
    to_remove = remove_bad_combos(failures, to_remove, target)

    # now do the remaining details
    to_remove = build_removals(platforms, buildtypes, testtypes, failures, to_remove, target)
    to_remove = remove_bad_combos(failures, to_remove, target)

    total_detected, total_time, saved_time = check_removal(failures, to_remove)
    percent_detected = ((len(total_detected) / (total*1.0)) * 100)

    format_in_table(platforms, buildtypes, testtypes, to_remove)
    print "We will detect %.2f%% (%s) of the %s failures" % (percent_detected, len(total_detected), total)

    if options.testmode:
        return

    insert_in_database(to_remove)
    now = datetime.date.today()
    addition, deletion = print_diff(str(now - datetime.timedelta(days=1)), str(now))
    total_changes = len(addition) + len(deletion)
    if total_changes == 0:
        send_email(len(failures), len(to_remove), "no changes from previous day", admin=True, results=True)
    else:
        send_email(len(failures), len(to_remove), str(total_changes)+" changes from previous day", addition, deletion, admin=True, results=True)

def insert_in_database(to_remove):
    now = datetime.datetime.now().strftime('%Y-%m-%d 00:00:00')
    run_query('delete from seta where date="%s"' % now)
    for tuple in to_remove:
        query = 'insert into seta (date, jobtype) values ("%s", ' % now
        query += '"%s")' % tuple
        run_query(query)

def sanity_check(jobtype, target, options):
    failures = getRawData(jobtype)
    total = len(failures)

    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday = yesterday.strftime('%Y-%m-%d 00:00:00')
    output_list = run_query('select jobtype from seta where date="%s"' % yesterday)

    # to convert a list of strings to a list of lists
    to_remove = []
    for element in output_list:
        parts = element.split("'")
        to_remove.append([parts[1], parts[3], parts[5]])

    total_detected, total_time, saved_time = check_removal(failures, to_remove)
    percent_detected = ((len(total_detected) / (total*1.0)) * 100)

    if percent_detected >= target:
        print "No changes found from previous day"
        if options.testmode:
            return
        insert_in_database(to_remove)
        send_email(len(failures), len(to_remove), "no changes from previous day", admin=True)
        return 0
    else:
        return -1

def run_query(query):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()
    cur.execute(query)

    results = []
    # each row is in ('val',) format, we want 'val'
    for rows in cur.fetchall():
        results.append(rows[0])

    cur.close()
    return results

def check_data(query_date):
    data = run_query('select jobtype from seta where date="%s"' % query_date)
    if not data:
        print "The database does not have data for the given %s date." % query_date
        for date in range(-3, 4):
            current_date = query_date + datetime.timedelta(date)
            tuple = run_query('select jobtype from seta where date="%s"' % current_date)
            if tuple:
                print "The data is available for date=%s" % current_date
        return None
    return data

def print_diff(start_date, end_date):
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    start_tuple = check_data(start_date)
    end_tuple = check_data(end_date)

    if start_tuple is None or end_tuple is None:
        return
    else:
        print "The tuples present on %s and not present on %s: " % (end_date, start_date)
        addition = list(set(end_tuple) - set(start_tuple))
        if len(addition) > 20:
            print "Warning: Too many differences detected, most likely there is data missing or incorrect"
        else:
            print addition

        print "The tuples not present on %s and present on %s: " % (end_date, start_date)
        deletion = list(set(start_tuple) - set(end_tuple))
        if len(deletion) > 20:
            print "Warning: Too many differences detected, most likely there is data missing or incorrect"
        else:
            print deletion

        return (addition, deletion)

def parse_args(argv=None):
    parser = ArgumentParser()
    parser.add_argument("-s", "--startdate",
                        metavar="YYYY-MM-DD",
                        dest="start_date",
                        help="starting date for comparison."
                        )

    parser.add_argument("-e", "--enddate",
                        metavar="YYYY-MM-DD",
                        dest="end_date",
                        help="ending date for comparison."
                        )

    parser.add_argument("--quick",
                        action="store_true",
                        dest="quick",
                        help="quick sanity check to compare previous day entries \
                              and see if still valid."
                        )

    parser.add_argument("--testmode",
                        action="store_true",
                        dest="testmode",
                        help="This mode is for testing without interaction with \
                              database and emails."
                        )

    options = parser.parse_args(argv)
    return options

if __name__ == "__main__":
    options = parse_args()
    if options.start_date and options.end_date:
        print_diff(options.start_date, options.end_date)
    else:
        jobtype = 1 # code for test job type
        targets = [100.0]
        for target in targets:
            if options.quick:
                result = sanity_check(jobtype, target, options)
                if result == 0:
                    continue
            depth_first(jobtype, target, options)

