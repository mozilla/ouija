import json
import logging
import os
import requests
import datetime
from argparse import ArgumentParser
from emails import send_email
from redo import retry
from database.models import JobPriorities
from database.config import session, engine
from update_runnablejobs import update_job_priority_table, get_rootdir
from sqlalchemy import update, and_

import seta

# Let's get the root logger - this guarantees seeing all messages from other modules
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                  datefmt='%I:%M:%S'))
LOG.addHandler(ch)
# Silence requests as it is too noisy
logging.getLogger("requests").setLevel(logging.WARNING)

ROOT_DIR = get_rootdir()
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
# Number of days to go back and gather failures
SETA_WINDOW = 90
HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'ouija',
}
HOST = "http://seta-dev.herokuapp.com/"


def get_raw_data(start_date, end_date):
    if not end_date:
        end_date = datetime.datetime.now()

    if not start_date:
        start_date = end_date - datetime.timedelta(days=SETA_WINDOW)

    url = HOST + "data/seta/?startDate=%s&endDate=%s" % \
                 (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    try:
        response = retry(requests.get, args=(url, ),
                         kwargs={'headers': HEADERS, 'verify': True})
        data = json.loads(response.content)
    except Exception as error:
        # we will return an empty 'failures' list if got exception here
        LOG.debug("the request to %s failed, due to %s" % (url, error))
        data = {'failures': []}
    return data['failures']


def communicate(failures, to_insert, total_detected, testmode, date):

    active_jobs = seta.get_distinct_tuples()
    percent_detected = ((len(total_detected) / (len(failures) * 1.0)) * 100)
    LOG.info("We will detect %.2f%% (%s) of the %s failures" %
             (percent_detected, len(total_detected), len(failures)))

    if testmode:
        return

    priority = 1
    timeout = 0
    reset_preseed()
    updated_jobs = update_jobpriorities(to_insert, priority, timeout)
    LOG.info("updated %s (%s) jobs" % (len(updated_jobs), len(to_insert)))

    if date is None:
        date = datetime.date.today()

    try:
        total_changes = len(updated_jobs)
    except TypeError:
        total_changes = 0

# TODO: we need to setup username/password to work in Heroku, probably via env variables
#    if total_changes == 0:
#        send_email(len(failures), len(to_insert), date, "no changes from previous day",
#                   admin=True, results=False)
#    else:
#        send_email(len(failures), len(to_insert), date, str(total_changes) +
#                   " changes from previous day", updated_jobs, admin=True, results=True)


def reset_preseed():
    data = session.query(JobPriorities.expires, JobPriorities.id)\
                  .filter(JobPriorities.expires != None).all()

    now = datetime.datetime.now()
    for item in data:
        try:
            dv = datetime.datetime.strptime(item[0], "%Y-%M-%d")
        except ValueError:
            # TODO: consider updating column to have expires=None?
            continue
        except TypeError:
            dv = datetime.datetime.combine(item[0].today(), datetime.datetime.min.time())

        # reset expire field if date is today or in the past
        if dv.date() <= now.date():
            conn = engine.connect()
            statement = update(JobPriorities)\
                .where(JobPriorities.id == item[1])\
                .values(expires=None)
            conn.execute(statement)


def update_jobpriorities(to_insert, _priority, _timeout):
    # to_insert is currently high priority, pri=1 jobs, all else are pri=5 jobs

    changed_jobs = []
    for item in to_insert:
        # NOTE: we ignore JobPriorities with expires as they take precendence
        data = session.query(JobPriorities.id, JobPriorities.priority)\
                      .filter(and_(JobPriorities.testtype == item[2],
                                   JobPriorities.buildtype == item[1],
                                   JobPriorities.platform == item[0],
                                   JobPriorities.expires == None)).all()
        if len(data) != 1:
            # TODO: if 0 items, do we add the job?  if >1 do we alert and cleanup?
            continue

        if data[0][1] != _priority:
            changed_jobs.append(item)

            conn = engine.connect()
            statement = update(JobPriorities)\
                .where(and_(JobPriorities.testtype == item[2],
                            JobPriorities.buildtype == item[1],
                            JobPriorities.platform == item[0]))\
                .values(priority=_priority, timeout=_timeout)
            conn.execute(statement)

    return changed_jobs


def parse_args(argv=None):
    parser = ArgumentParser()
    parser.add_argument("-s", "--start-date",
                        metavar="YYYY-MM-DD",
                        dest="start_date",
                        help="starting date for comparison."
                        )

    parser.add_argument("-e", "--end-date",
                        metavar="YYYY-MM-DD",
                        dest="end_date",
                        help="ending date for comparison."
                        )

    parser.add_argument("--do-not-analyze",
                        action="store_true",
                        dest="do_not_analyze",
                        help="This option skips analysis of failures."
                        )

    parser.add_argument("--testmode",
                        action="store_true",
                        dest="testmode",
                        help="This mode is for testing without interaction with \
                              database and emails."
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
    LOG.info("date: %s, failures: %s" % (end_date, len(failures)))
    target = 100  # 100% detection

    to_insert, total_detected = seta.weighted_by_jobtype(failures, target, ignore_failure)
    communicate(failures, to_insert, total_detected, testmode, end_date)


if __name__ == "__main__":
    options = parse_args()
    update_job_priority_table()

    if options.end_date:
        end_date = datetime.datetime.strptime(options.end_date, "%Y-%m-%d")
    else:
        end_date = datetime.datetime.now()

    if options.start_date:
        start_date = datetime.datetime.strptime(options.start_date, "%Y-%m-%d")
    else:
        start_date = end_date - datetime.timedelta(days=SETA_WINDOW)

    if not options.do_not_analyze:
        analyze_failures(start_date, end_date, options.testmode, options.ignore_failure,
                         options.method)
