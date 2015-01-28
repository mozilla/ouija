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
        active_jobs = seta.getDistinctTuples()
        format_in_table(active_jobs, to_remove)
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


def format_in_table(active_jobs, master):
    results = {}
    sum_removed = 0
    sum_remaining = 0

    tbplnames = {'mochitest-1': {'group': 'M', 'code': '1', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-2': {'group': 'M', 'code': '2', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-3': {'group': 'M', 'code': '3', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-4': {'group': 'M', 'code': '4', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-5': {'group': 'M', 'code': '5', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-other': {'group': 'M', 'code': 'Oth', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-browser-chrome-1': {'group': 'M', 'code': 'bc1', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-browser-chrome-2': {'group': 'M', 'code': 'bc2', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-browser-chrome-3': {'group': 'M', 'code': 'bc3', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-devtools-chrome-1': {'group': 'M', 'code': 'dt1', 'debug': True, 'opt': False, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-devtools-chrome-2': {'group': 'M', 'code': 'dt2', 'debug': True, 'opt': False, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-devtools-chrome-3': {'group': 'M', 'code': 'dt3', 'debug': True, 'opt': False, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-devtools-chrome': {'group': 'M', 'code': 'dt', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-gl': {'group': 'M', 'code': 'gl', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-e10s-1': {'group': 'M-e10s', 'code': '1', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'mochitest-e10s-2': {'group': 'M-e10s', 'code': '2', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'mochitest-e10s-3': {'group': 'M-e10s', 'code': '3', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'mochitest-e10s-4': {'group': 'M-e10s', 'code': '4', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'mochitest-e10s-5': {'group': 'M-e10s', 'code': '5', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'mochitest-e10s-browser-chrome-1': {'group': 'M-e10s', 'code': 'bc1', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-e10s-browser-chrome-2': {'group': 'M-e10s', 'code': 'bc2', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-e10s-browser-chrome-3': {'group': 'M-e10s', 'code': 'bc3', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'mochitest-e10s-devtools': {'group': 'M-e10s', 'code': 'dt', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'xpcshell': {'group': '', 'code': 'X', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'crashtest': {'group': 'R', 'code': 'C', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'jsreftest': {'group': 'R', 'code': 'J', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'reftest-1': {'group': 'R', 'code': 'R1', 'debug': True, 'opt': True, 'linux32': True, 'linux64': False, 'default': False},
                 'reftest-2': {'group': 'R', 'code': 'R2', 'debug': True, 'opt': True, 'linux32': True, 'linux64': False, 'default': False},
                 'reftest-e10s': {'group': 'R-e10s', 'code': 'R', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'crashtest-e10s': {'group': 'R-e10s', 'code': 'C', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'jittest': {'group': '', 'code': 'Jit', 'debug': True, 'opt': True, 'linux32': False, 'linux64': False, 'default': True},
                 'jittest-2': {'group': '', 'code': 'Jit2', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'jittest-1': {'group': '', 'code': 'Jit1', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': False},
                 'marionette': {'group': '', 'code': 'Mn', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'marionette-e10s': {'group': '', 'code': 'Mn-e10s', 'debug': False, 'opt': True, 'linux32': True, 'linux64': False, 'default': False},
                 'cppunit': {'group': '', 'code': 'Cpp', 'debug': True, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'reftest-no-accel': {'group': '', 'code': 'Cpp', 'debug': False, 'opt': True, 'linux32': True, 'linux64': False, 'default': False},
                 'web-platform-tests-1': {'group': 'W', 'code': '1', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'web-platform-tests-2': {'group': 'W', 'code': '2', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'web-platform-tests-3': {'group': 'W', 'code': '3', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'web-platform-tests-4': {'group': 'W', 'code': '4', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'web-platform-tests-reftests': {'group': 'W', 'code': 'R', 'debug': False, 'opt': True, 'linux32': True, 'linux64': True, 'default': True},
                 'reftest': {'group': 'R', 'code': 'R', 'debug': True, 'opt': True, 'linux32': False, 'linux64': True, 'default': True}}

    for jobtype in active_jobs:
        key = "%s_%s" % (jobtype[0], jobtype[1])
        if key not in results:
            results[key] = []

        for item in master:
            if item[0] == jobtype[0] and item[1] == jobtype[1]:
                results[key].append(item[2])

    keys = results.keys()
    keys.sort()
    for key in keys:
        data = results[key]
        data.sort()
        output = ""
        for platform, buildtype, test in active_jobs:
            if "%s_%s" % (platform, buildtype) != key:
                continue

            output += '\t'
            if test in data or '' in data:
                output += tbplnames[test]['code']
                sum_removed += 1
            else:
                output += "--"
                sum_remaining += 1

        print "%s%s" % (key, output)
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
    yesterday = yesterday.strftime('%Y-%m-%d')

    conn = httplib.HTTPConnection('alertmanager.allizom.org')
    cset = "/data/setadetails/?date=%s" % yesterday
    conn.request("GET", cset)
    response = conn.getresponse()

    data = response.read()
    response.close()
    cdata = json.loads(data)
    cdata = cdata['jobtypes']
    to_remove = cdata[yesterday]

    total_detected, total_time, saved_time = seta.check_removal(failures, to_remove)
    percent_detected = ((len(total_detected) / (len(failures)*1.0)) * 100)

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
    print query
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

