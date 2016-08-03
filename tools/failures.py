import json
import os
import requests
import datetime
import MySQLdb
from argparse import ArgumentParser
from emails import send_email
from redo import retry
from update_runnablejobs import update_runnableapi

import seta

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
# ROOT_DIR = os.getcwd()
ROOT_DIR = '/home/ubuntu/ouija/data'
SETA_WINDOW = 90
TREEHERDER_HOST = "https://treeherder.mozilla.org/api/project/{0}/" \
                  "runnable_jobs/?decisionTaskID={1}&format=json"
headers = {
    'Accept': 'application/json',
    'User-Agent': 'ouija',
}


def get_raw_data(start_date, end_date):
    if not end_date:
        end_date = datetime.datetime.now()

    if not start_date:
        start_date = end_date - datetime.timedelta(days=SETA_WINDOW)

    url = "http://alertmanager.allizom.org/data/seta/?startDate=%s&endDate=%s" % \
          (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

    response = retry(requests.get, args=(url, ),
                     kwargs={'headers': headers, 'verify': True})
    data = json.loads(response.content)
    return data['failures']


def communicate(failures, to_insert, total_detected, testmode, date):

    active_jobs = seta.get_distinct_tuples()
    format_in_table(active_jobs, to_insert)  # we may need to fix this later
    percent_detected = ((len(total_detected) / (len(failures) * 1.0)) * 100)
    print "We will detect %.2f%% (%s) of the %s failures" % \
          (percent_detected, len(total_detected), len(failures))

    if testmode:
        return
    prepare_the_database()
    insert_in_database(to_insert, date)

    if date is None:
        date = datetime.date.today()
    change = print_diff("%s" % (date - datetime.timedelta(days=1)).strftime('%Y-%m-%d'), '%s' %
                        date.strftime('%Y-%m-%d'))
    try:
        total_changes = len(change)
    except TypeError:
        total_changes = 0

    if total_changes == 0:
        send_email(len(failures), len(to_insert), date, "no changes from previous day",
                   admin=True, results=False)
    else:
        send_email(len(failures), len(to_insert), date, str(total_changes) +
                   " changes from previous day", change, admin=True, results=True)


def format_in_table(active_jobs, master):
    results = {}
    sum_removed = 0
    sum_remaining = 0

    data = retry(requests.get, args=('http://alertmanager.allizom.org/data/jobnames/', ),
                 kwargs={'headers': headers,
                         'verify': True}).json()
    running_jobs = data['results']

    for jobtype in active_jobs:
        key = "%s_%s" % (jobtype[0], jobtype[1])
        if key not in results:
            results[key] = []

        for item in master:
            if item[0] == jobtype[0] and item[1] == jobtype[1]:
                if item[2] not in results[key]:
                    results[key].append(item[2])

    keys = results.keys()
    keys.sort()
    missing_jobs = []
    for key in keys:
        data = results[key]
        data.sort()
        output = ""
        for platform, buildtype, test in active_jobs:
            if "%s_%s" % (platform, buildtype) != key:
                continue

            output += '\t'
            if test in data or '' in data:
                found = False
                for job in running_jobs:
                    if job['name'] == test:
                        output += job['job_type_symbol']
                        found = True
                        break

                if not found:
                    output += '**'
                    missing_jobs.append(test)

                sum_removed += 1
            else:
                output += "--"
                sum_remaining += 1

        print "%s%s" % (key, output)

    if missing_jobs:
        print "** new jobs which need a code: %s" % ','.join(missing_jobs)

    print "Total removed %s" % (sum_removed)
    print "Total remaining %s" % (sum_remaining)
    print "Total jobs %s" % (sum_removed + sum_remaining)


def insert_in_database(to_insert, date=None):
    if not date:
        date = datetime.datetime.now().strftime('%Y-%m-%d')
    else:
        date = date.strftime('%Y-%m-%d')

    run_query('delete from seta where date="%s"' % date)
    for jobtype in to_insert:
        query = 'insert into seta (date, jobtype) values ("%s", ' % date
        query += '"%s")' % jobtype
        run_query(query)


def prepare_the_database():
    # wipe up the job data older than 90 days
    date = (datetime.datetime.now() - datetime.timedelta(days=SETA_WINDOW)).strftime('%Y-%m-%d')
    run_query("delete from seta where date<='%s'" % date)


def run_query(query):
    database = MySQLdb.connect(host="localhost",
                               user="root",
                               passwd="root",
                               db="ouija")

    cur = database.cursor()
    cur.execute(query)

    results = []
    # each row is in ('val',) format, we want 'val'
    for rows in cur.fetchall():
        results.append(rows[0])

    cur.close()
    return results


def check_data(query_date):
    ret_val = []
    data = run_query('select jobtype from seta where date="%s"' % query_date)
    if not data:
        print "The database does not have data for the given %s date." % query_date
        for date in range(-3, 4):
            current_date = query_date + datetime.timedelta(date)
            jobtype = run_query('select jobtype from seta where date="%s"' % current_date)
            if jobtype:
                print "The data is available for date=%s" % current_date
        return ret_val

    for job in data:
        parts = job.split("'")
        ret_val.append("%s" % [str(parts[1]), str(parts[3]), str(parts[5])])

    return ret_val


def print_diff(start_date, end_date):
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    start_tuple = check_data(start_date)
    end_tuple = check_data(end_date)

    start_tuple.sort()
    end_tuple.sort()

    if start_tuple is None or end_tuple is None:
        print "NO DATA: %s, %s" % (start_date, end_date)
        return []
    else:
        deletion = list(set(start_tuple) - set(end_tuple))
        deletion.sort()
        if not deletion:
            deletion = ''
        print "%s: These jobs have changed from the previous day: %s" % \
              (end_date.strftime("%Y-%m-%d"), deletion)
        return deletion


def parse_args(argv=None):
    parser = ArgumentParser()
    parser.add_argument("-s", "--start_date",
                        metavar="YYYY-MM-DD",
                        dest="start_date",
                        help="starting date for comparison."
                        )

    parser.add_argument("-e", "--end_date",
                        metavar="YYYY-MM-DD",
                        dest="end_date",
                        help="ending date for comparison."
                        )

    parser.add_argument("--testmode",
                        action="store_true",
                        dest="testmode",
                        help="This mode is for testing without interaction with \
                              database and emails."
                        )

    parser.add_argument("--diff",
                        action="store_true",
                        dest="diff",
                        help="This mode is for printing a diff between two dates. \
                              requires --start_date and --end_date."
                        )

    parser.add_argument("--ignore-failure",
                        type=int,
                        dest="ignore_failure",
                        help="With this option one can ignore root causes of revisions. \
                              Specify the number of *extra* passes to be done."
                        )

    parser.add_argument("--method",
                        metavar="[failures|weighted]",
                        dest="method",
                        default="weighted",
                        help="This is for deciding the algorithm to run. \
                              Two algorithms to run currently: [failures|weighted]."
                        )

    options = parser.parse_args(argv)
    return options


def analyze_failures(start_date, end_date, testmode, ignore_failure, method):
    failures = get_raw_data(start_date, end_date)
    print "date: %s, failures: %s" % (end_date, len(failures))
    target = 100  # 100% detection

    if method == "failures":
        to_insert, total_detected = seta.failures_by_jobtype(failures, target, ignore_failure)
    else:
        to_insert, total_detected = seta.weighted_by_jobtype(failures, target, ignore_failure)

    preseed_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'src', 'preseed.json')
    preseed = []
    with open(preseed_path, 'r') as fHandle:
        preseed = json.load(fHandle)

    for job in preseed:
        # TODO: if expired, ignore
        jobspec = [job['platform'], job['buildtype'], job['name']]
        if jobspec in to_insert and job['action'] == 'coalesce':
            to_insert.remove(jobspec)
        elif jobspec not in to_insert and job['action'] == 'run':
            to_insert.append(jobspec)

    communicate(failures, to_insert, total_detected, testmode, end_date)


if __name__ == "__main__":
    options = parse_args()
    update_runnableapi()
    if options.diff:
        if options.start_date and options.end_date:
            print_diff(options.start_date, options.end_date)
        else:
            print "when using --diff please provide a --start_date and an --end_date"
    else:
        if options.end_date:
            end_date = datetime.datetime.strptime(options.end_date, "%Y-%m-%d")
        else:
            end_date = datetime.datetime.now()

        if options.start_date:
            start_date = datetime.datetime.strptime(options.start_date, "%Y-%m-%d")
        else:
            start_date = end_date - datetime.timedelta(days=SETA_WINDOW)

        analyze_failures(start_date, end_date, options.testmode, options.ignore_failure,
                         options.method)
