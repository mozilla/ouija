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

import seta

def getRawData():
    conn = httplib.HTTPConnection('alertmanager.allizom.org')
    cset = "/data/seta/"
    conn.request("GET", cset)
    response = conn.getresponse()

    data = response.read()
    response.close()
    cdata = json.loads(data)
    return cdata['failures']

def communicate(failures, to_remove, total_detected, testmode, results=True):
    if results:
        platforms, buildtypes, testtypes = seta.getDistinctTuples()
        format_in_table(platforms, buildtypes, testtypes, to_remove)
        percent_detected = ((len(total_detected) / (len(failures)*1.0)) * 100)
        print "We will detect %.2f%% (%s) of the %s failures" % (percent_detected, len(total_detected), len(failures))

    if testmode:
        return

    insert_in_database(to_remove)
    now = datetime.date.today()
    addition, deletion = print_diff(str(now - datetime.timedelta(days=1)), str(now))
    total_changes = len(addition) + len(deletion)
    if total_changes == 0:
        send_email(len(failures), len(to_remove), "no changes from previous day", admin=True, results=results)
    else:
        send_email(len(failures), len(to_remove), str(total_changes)+" changes from previous day", addition, deletion, admin=True, results=results)


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

def insert_in_database(to_remove):
    now = datetime.datetime.now().strftime('%Y-%m-%d 00:00:00')
    run_query('delete from seta where date="%s"' % now)
    for tuple in to_remove:
        query = 'insert into seta (date, jobtype) values ("%s", ' % now
        query += '"%s")' % tuple
        run_query(query)

def sanity_check(failures, target):
    total = len(failures)

    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday = yesterday.strftime('%Y-%m-%d 00:00:00')
    output_list = run_query('select jobtype from seta where date="%s"' % yesterday)

    # to convert a list of strings to a list of lists
    to_remove = []
    for element in output_list:
        parts = element.split("'")
        to_remove.append([parts[1], parts[3], parts[5]])

    total_detected, total_time, saved_time = seta.check_removal(failures, to_remove)

    if percent_detected >= target:
        print "No changes found from previous day"
        return to_remove, percent_detected
    else:
        return [], total_detected

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
        failures = getRawData()
        targets = [100.0]
        for target in targets:
            if options.quick:
                to_remove, total_detected = sanity_check(failures, target)
                if len(to_remove) > 0:
                    communicate(failures, to_remove, total_detected, options.testmode, results=False)
                    continue

            # no quick option, or quick failed due to new failures detected
            to_remove, total_detected = seta.depth_first(failures, target)
            communicate(failures, to_remove, total_detected, options.testmode)

