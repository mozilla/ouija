import datetime
import json
import logging
import os
from argparse import ArgumentParser
import cProfile

import requests
from redo import retry
from sqlalchemy import update, and_

from database.models import JobPriorities
from database.config import session, engine
from update_runnablejobs import update_job_priority_table, get_rootdir
from seta import weighted_by_jobtype


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
    """Reach the data/seta endpoint for all failures that have been marked as "fixed by commit"

    The endpoint returns a dictionary with a key per revision or bug ID (the bug ID is used for
    intermittent failures and the revision is used for real failures). The failures for *real
    failures* will contain all jobs that have been starred as "fixed by commit".

    Notice that the raw data does not tell you on which repository a root failure was fixed.

    For instance, in the raw data you might see a reference to 9fa614d8310d which is a back out and
    it is reference by 12 starred jobs:
        https://treeherder.mozilla.org/#/jobs?repo=autoland&filter-searchStr=android%20debug%20cpp&tochange=9fa614d8310db9aabe85cc3c3cff6281fe1edb0c
    The raw data will show those 12 jobs.

    We return the obtained data or an empty structure if we failed to fetch it.

    [1]
    {
      "failures": {
        "44d29bac3654": [
          ["android-4-0-armv7-api15", "opt", "android-lint", 2804 ],
          ["android-4-0-armv7-api15", "opt", "android-api-15-gradle-dependencies", 2801],
    """
    if not end_date:
        end_date = datetime.datetime.now()

    if not start_date:
        start_date = end_date - datetime.timedelta(days=SETA_WINDOW)

    url = HOST + "data/seta/?startDate=%s&endDate=%s" % \
                 (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    LOG.info('Grabbing information from {}'.format(url))
    try:
        response = retry(requests.get, args=(url, ),
                         kwargs={'headers': HEADERS, 'verify': True})
        data = json.loads(response.content)
    except Exception as error:
        # we will return an empty 'failures' list if got exception here
        LOG.warning("The request for %s failed due to %s" % (url, error))
        LOG.warning("We will work with an empty list of failures")
        data = {'failures': []}

    return data['failures']


def clear_expiration_field_for_expired_jobs():
    data = session.query(JobPriorities.expires, JobPriorities.id).filter(
        JobPriorities.expires != None).all()  # flake8: noqa

    now = datetime.datetime.now()
    for item in data:
        try:
            expiration_date = datetime.datetime.strptime(item[0], "%Y-%M-%d")
        except ValueError:
            # TODO: consider updating column to have expires=None?
            LOG.warning('Failed to downcast to datetime for ({},{})'.format(item[1], item[0]))
            continue
        except TypeError:
            expiration_date = datetime.datetime.combine(
                item[0].today(),
                datetime.datetime.min.time()
            )

        # reset expiration field if the date is today or in the past
        if expiration_date.date() <= now.date():
            conn = engine.connect()
            statement = update(JobPriorities)\
                .where(JobPriorities.id == item[1])\
                .values(expires=None)
            conn.execute(statement)


def increase_jobs_priority(high_value_jobs, priority=1, timeout=0):
    """For every high value job try to see if we need to update increase its priority

    Currently, high value jobs have a priority of 1 and a timeout of 0.

    Return how many jobs had their priority increased
    """
    changed_jobs = []
    for item in high_value_jobs:
        # NOTE: we ignore JobPriorities with expires as they take precendence
        data = session.query(JobPriorities.id, JobPriorities.priority)\
                      .filter(and_(JobPriorities.testtype == item[2],
                                   JobPriorities.buildtype == item[1],
                                   JobPriorities.platform == item[0],
                                   JobPriorities.expires == None)).all()  # flake8: noqa
        if len(data) != 1:
            # TODO: if 0 items, do we add the job?  if >1 do we alert and cleanup?
            continue

        if data[0][1] != priority:
            changed_jobs.append(item)

            conn = engine.connect()
            statement = update(JobPriorities)\
                .where(and_(JobPriorities.testtype == item[2],
                            JobPriorities.buildtype == item[1],
                            JobPriorities.platform == item[0]))\
                .values(priority=priority, timeout=timeout)
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

    parser.add_argument("--dry-run",
                        action="store_true",
                        dest="dry_run",
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


def analyze_failures(start_date, end_date, dry_run, ignore_failure, method):
    failures = get_raw_data(start_date, end_date)
    LOG.info("date: %s, failures: %s" % (end_date, len(failures)))
    target = 100  # 100% detection

    high_value_jobs, total_detected = weighted_by_jobtype(failures, target, ignore_failure)

    percent_detected = ((len(total_detected) / (len(failures) * 1.0)) * 100)
    LOG.info("We will detect %.2f%% (%s) of the %s failures" %
             (percent_detected, len(total_detected), len(failures)))

    if not dry_run:
        clear_expiration_field_for_expired_jobs()
        updated_jobs = increase_jobs_priority(high_value_jobs)
        LOG.info("updated %s (%s) jobs" % (len(updated_jobs), len(high_value_jobs)))


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
        cProfile.run('analyze_failures(start_date, end_date, options.dry_run, options.ignore_failure, options.method)')
