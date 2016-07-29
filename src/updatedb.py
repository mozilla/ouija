import argparse
import MySQLdb
import datetime
import sys
import time
import logging
from threading import Thread
from Queue import Queue

import requests

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'ouija',
}

branch_paths = {
    'mozilla-central': 'mozilla-central',
    'mozilla-inbound': 'integration/mozilla-inbound',
    'b2g-inbound': 'integration/b2g-inbound',
    'fx-team': 'integration/fx-team',
    'try': 'try',
}

branches = [
    'mozilla-central',
    'mozilla-inbound',
    'b2g-inbound',
    'fx-team',
    'try'
]


class Worker(Thread):

    def __init__(self, queue, **kargs):
        Thread.__init__(self, **kargs)
        self.queue = queue
        self.daemon = True

    def run(self):
        while True:
            job_spec = self.queue.get()
            try:
                self.do_job(job_spec)
            except:
                logging.exception('Error in %s', self.name)
            finally:
                self.queue.task_done()


class Downloader(Worker):

    def __init__(self, download_queue, **kargs):
        Worker.__init__(self, download_queue, **kargs)

    def do_job(self, job_spec):
        branch, revision, date = job_spec
        logging.info("%s: %s - %s", self.name, revision, date)
        data = getCSetResults(branch, revision)
        uploadResults(data, branch, revision, date)


def getResultSetID(branch, revision):
    url = "https://treeherder.mozilla.org/api/project/%s/resultset/" \
          "?format=json&full=true&revision=%s" % (branch, revision)
    return fetch_json(url)


def getCSetResults(branch, revision):
    """
    https://tbpl.mozilla.org/php/getRevisionBuilds.php?branch=mozilla-inbound&rev=3435df09ce34.
    no caching as data will change over time.  Some results will be in asap, others will take
    up to 12 hours (usually < 4 hours)
    """
    rs_data = getResultSetID(branch, revision)
    results_set_id = rs_data['results'][0]['id']

    done = False
    offset = 0
    count = 2000
    num_results = 0
    retVal = {}
    while not done:
        url = "https://treeherder.mozilla.org/api/project/%s/jobs/" \
              "?count=%s&offset=%s&result_set_id=%s"
        data = fetch_json(url % (branch, count, offset, results_set_id))
        if len(data['results']) < 2000:
            done = True
        num_results += len(data['results'])
        offset += count

        if retVal == {}:
            retVal = data
        else:
            retVal['results'].extend(data['results'])
            retVal['meta']['count'] = num_results

    return retVal


def getPushLog(branch, startdate):
    """https://hg.mozilla.org/integration/mozilla-inbound/pushlog?startdate=2013-06-19"""
    # TODO: Replace this with fetch_json() using /jsonpushlog
    url = "https://hg.mozilla.org/%s//json-pushes?startdate=%04d-%02d-%02d&" \
          "tipsonly=1" % (branch_paths[branch], startdate.year, startdate.month,
                          startdate.day)
    response = fetch_json(url)
    pushids = response.keys()
    pushes = []
    date = None
    for pushid in pushids:
        # we should switch to 40 characters in the further
        changeset = response[pushid]['changesets'][0][0:12]
        if changeset:
            date = datetime.datetime.fromtimestamp(response[pushid]['date'])

        if changeset and date and date >= startdate:
            pushes.append([changeset, date])
            date = None
    return pushes


def clearResults(branch, startdate):

    date_xx_days_ago = datetime.date.today() - datetime.timedelta(days=180)
    delete_delta_and_old_data = 'delete from testjobs where branch="%s" and (date >= ' \
                                '"%04d-%02d-%02d %02d:%02d:%02d" or date < "%04d-%02d-%02d")' % \
                                (branch, startdate.year, startdate.month, startdate.day,
                                 startdate.hour, startdate.minute, startdate.second,
                                 date_xx_days_ago.year, date_xx_days_ago.month,
                                 date_xx_days_ago.day)

    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()
    cur.execute(delete_delta_and_old_data)
    cur.close()


def uploadResults(data, branch, revision, date):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()

    if "results" not in data:
        return

    results = data["results"]
    count = 0
    for r in results:
        _id, slave, result, duration, platform, buildtype, testtype, bugid = \
            '', '', '', '', '', '', '', ''
        _id = r["id"]

        # Skip if 'result' is unknown
        result = r["result"]
        if result == u'unknown':
            continue

        duration = '%s' % (int(r["end_timestamp"]) - int(r["start_timestamp"]))

        platform = r["platform"]
        if not platform:
            continue

        buildtype = r["platform_option"]
        build_system_type = r['build_system_type']
        # the testtype of builbot job is in 'ref_data_name'
        # like web-platform-tests-4 in "Ubuntu VM 12.04 x64 mozilla-inbound
        # but taskcluster's testtype is a part of its 'job_type_name
        if r['build_system_type'] == 'buildbot':
            testtype = r['ref_data_name'].split(' ')[-1]

        else:
            # The test name on taskcluster comes to a sort of combination
            # (e.g desktop-test-linux64/debug-jittests-3)and asan job can
            # been referenced as a opt job. we want the build type(debug or opt)
            # to separate the job_type_name, then get "jittests-3" as testtype
            # for job_type_name like desktop-test-linux64/debug-jittests-3
            separator = r['platform_option'] \
                if r['platform_option'] != 'asan' else 'opt'
            testtype = r['job_type_name'].split(
                '{buildtype}-'.format(buildtype=separator))[-1]
        if r["build_system_type"] == "taskcluster":
            # TODO: this is fragile, current platforms as of Jan 26, 2016 we see in taskcluster
            pmap = {"linux64": "Linux64",
                    "linux32": "Linux32",
                    "osx-10-7": "MacOSX64",
                    "gecko-decision": "gecko-decision",
                    "lint": "lint"}
            p = platform
            if platform in pmap:
                p = pmap[platform]
            testtype = r["job_type_name"].split(p)[-1]

        failure_classification = 0
        try:
            # http://treeherder.mozilla.org/api/failureclassification/
            failure_classification = int(r["failure_classification_id"])
        except ValueError:
            failure_classification = 0
        except TypeError:
            logging.warning("Error, failure classification id: expecting an int, "
                            "but recieved %s instead" % r["failure_classification_id"])
            failure_classification = 0

        # Get Notes: https://treeherder.mozilla.org/api/project/mozilla-inbound/note/?job_id=5083103
        if result != u'success':
            url = "https://treeherder.mozilla.org/api/project/%s/note/?job_id=%s" % (branch, _id)
            try:
                notes = fetch_json(url)
                if notes:
                    bugid = notes[-1]['note']
            except KeyError:
                pass

        # Get failure snippets: https://treeherder.mozilla.org/api/project/
        # mozilla-inbound/artifact/?job_id=11651377&name=Bug+suggestions&type=json
        failures = []
        if failure_classification == 2:
            url = "https://treeherder.mozilla.org/api/project/%s/artifact/?job_id=%s" \
                  "&name=Bug+suggestions&type=json" % (branch, _id)
            snippets = fetch_json(url)
            if snippets:
                for item in snippets[0]["blob"]:
                    if not item["search_terms"] and len(item["search_terms"]) < 1:
                        continue
                    filename = item['search_terms'][0]
                    if (filename.endswith('.js') or filename.endswith('.xul') or
                            filename.endswith('.html')):
                        dir = item['search']
                        dir = (dir.split('|')[1]).strip()
                        if dir.endswith(filename):
                            dir = dir.split(filename)[0]
                            failures.append(dir + '/' + filename)
        # https://treeherder.mozilla.org/api/project/mozilla-central/jobs/1116367/
        url = "https://treeherder.mozilla.org/api/project/%s/jobs/%s/" % (branch, _id)
        data1 = fetch_json(url)

        slave = data1['machine_name']

        # Insert into MySQL Database
        sql = """insert into testjobs (slave, result, build_system_type,
                                       duration, platform, buildtype, testtype,
                                       bugid, branch, revision, date,
                                       failure_classification, failures)
                             values ('%s', '%s', '%s', %s,
                                     '%s', '%s', '%s', '%s', '%s',
                                     '%s', '%s', %s, '%s')""" % \
              (slave, result, build_system_type,
               duration, platform, buildtype, testtype,
               bugid, branch, revision, date, failure_classification, ','.join(failures[:5]))

        try:
            cur.execute(sql)
            count += 1
        except MySQLdb.IntegrityError:
            # we already have this job
            logging.warning("sql failed to insert, we probably have this job: %s" % sql)
            pass
    cur.close()
    logging.info("uploaded %s/(%s) results for rev: %s, branch: %s, date: %s" %
                 (count, len(results), revision, branch, date))


def parseResults(args):
    download_queue = Queue()

    for i in range(args.threads):
        Downloader(download_queue, name="Downloader %s" % (i + 1)).start()

    startdate = datetime.datetime.utcnow() - datetime.timedelta(hours=args.delta)

    if args.branch == 'all':
        result_branches = branches
    else:
        result_branches = [args.branch]

    for branch in result_branches:
        clearResults(branch, startdate)

    for branch in result_branches:
        revisions = getPushLog(branch, startdate)
        for revision, date in revisions:
            download_queue.put((branch, revision, date))

    download_queue.join()
    logging.info('Downloading completed')

    # Sometimes the parent may exit and the child is not immidiately killed.
    # This may result in the error like the following -
    #
    # Exception in thread DBHandler (most likely raised during interpreter shutdown):
    # Traceback (most recent call last):
    # File "/usr/lib/python2.7/threading.py", line 810, in __bootstrap_inner
    # File "updatedb.py", line 120, in run
    # File "/usr/lib/python2.7/Queue.py", line 168, in get
    # File "/usr/lib/python2.7/threading.py", line 332, in wait
    #: 'NoneType' object is not callable
    #
    # The following line works as a fix
    # ref : http://b.imf.cc/blog/2013/06/26/python-threading-and-queue/

    time.sleep(0.1)


def fetch_json(url):
    response = requests.get(url, headers=DEFAULT_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update ouija database.')
    parser.add_argument('--branch', dest='branch', default='all',
                        help='Branch for which to retrieve results.')
    parser.add_argument('--delta', dest='delta', type=int, default=12,
                        help='Number of hours in past to use as start time.')
    parser.add_argument('--threads', dest='threads', type=int, default=1,
                        help='Number of threads to use.')
    args = parser.parse_args()
    if args.branch != 'all' and args.branch not in branches:
        print('error: unknown branch: ' + args.branch)
        sys.exit(1)
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("requests").setLevel(logging.WARNING)
    parseResults(args)
