import argparse
import re
import MySQLdb
import datetime
import sys
import time
import logging
from threading import Thread
from Queue import Queue

import requests

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


#
# The following platforms were not added
# We might want to add them in the future
#
'''
b2g_mozilla-central_macosx64_gecko build opt
b2g_mozilla-central_macosx64_gecko-debug build opt
b2g_macosx64 opt gaia-ui-test

linux64-br-haz_mozilla-central_dep opt

Android 4.2 x86 build
Android 4.2 x86 Emulator opt androidx86-set-4

b2g_mozilla-central_win32_gecko-debug build opt
b2g_mozilla-central_win32_gecko build opt
b2g_mozilla-central_linux32_gecko build opt
b2g_mozilla-central_linux32_gecko-debug build opt

b2g_mozilla-central_emulator-kk_periodic opt
b2g_mozilla-central_emulator-kk-debug_periodic opt
b2g_mozilla-central_emulator-kk_nonunified opt
b2g_mozilla-central_emulator-kk-debug_nonunified opt

b2g_mozilla-central_emulator-jb-debug_dep opt
b2g_mozilla-central_emulator_dep opt
b2g_mozilla-central_emulator-debug_dep opt
b2g_mozilla-central_emulator-jb_dep opt
b2g_mozilla-central_emulator_nonunified opt
b2g_mozilla-central_emulator-debug_nonunified opt
b2g_mozilla-central_emulator-jb-debug_nonunified opt
b2g_mozilla-central_emulator-jb_nonunified opt

b2g_mozilla-central_nexus-4_periodic opt
b2g_mozilla-central_nexus-4_eng_periodic opt

b2g_mozilla-central_linux64_gecko build opt
b2g_mozilla-central_linux64_gecko-debug build opt

b2g_mozilla-central_hamachi_eng_dep opt
b2g_mozilla-central_hamachi_periodic opt

b2g_mozilla-central_flame_eng_dep opt
b2g_mozilla-central_flame_periodic opt

b2g_mozilla-central_helix_periodic opt

b2g_mozilla-central_wasabi_periodic opt
'''

UPLOAD_JOB, CLEAR_JOB = 0, 1

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

class DBHandler(Worker):

    def do_job(self, job_spec):
        job_type, job_args = job_spec

        if job_type == UPLOAD_JOB:
            uploadResults(*job_args)
        elif job_type == CLEAR_JOB:
            clearResults(*job_args)
        else:
            assert False #Should not happen

class Downloader(Worker):

    def __init__(self, download_queue, db_queue, **kargs):
        Worker.__init__(self, download_queue, **kargs)
        self.db_queue = db_queue

    def do_job(self, job_spec):
        branch, revision, date = job_spec
        logging.info("%s: %s - %s", self.name, revision, date)
        data = getCSetResults(branch, revision)
        self.db_queue.put((UPLOAD_JOB, [data, branch, revision, date]))

def getCSetResults(branch, revision):
    """
      https://tbpl.mozilla.org/php/getRevisionBuilds.php?branch=mozilla-inbound&rev=3435df09ce34

      no caching as data will change over time.  Some results will be in asap, others will take
      up to 12 hours (usually < 4 hours)
    """
#    url = "https://tbpl.mozilla.org/php/getRevisionBuilds.php?branch=%s&rev=%s&showall=1" % (branch, revision)
    url = "https://treeherder.mozilla.org/api/project/%s/resultset/?format=json&full=true&revision=%s&with_jobs=true" %(branch, revision)
    response = requests.get(url, headers={'accept-encoding':'gzip'}, verify=True)
    cdata = response.json()
    return cdata

def getPushLog(branch, startdate):
    """
      https://hg.mozilla.org/integration/mozilla-inbound/pushlog?startdate=2013-06-19
    """

    url = "https://hg.mozilla.org/%s/pushlog?startdate=%04d-%02d-%02d" % (branch_paths[branch], startdate.year, startdate.month, startdate.day)
    response = requests.get(url, headers={'accept-encoding':'gzip'}, verify=True)
    data = response.content
    pushes = []
    csetid = re.compile('.*Changeset ([0-9a-f]{12}).*')
    dateid = re.compile('.*([0-9]{4}\-[0-9]{2}\-[0-9]{2})T([0-9\:]+)Z.*')
    push = None
    date = None
    for line in data.split('\n'):
        matches = csetid.match(line)
        if matches:
            push = matches.group(1)

        matches = dateid.match(line)
        if matches:
            ymd = map(int, matches.groups(2)[0].split('-'))
            hms = map(int, matches.groups(2)[1].split(':'))
            date = datetime.datetime(ymd[0], ymd[1], ymd[2], hms[0], hms[1], hms[2])

        if push and date and date >= startdate:
            pushes.append([push, date])
            push = None
            date = None
    return pushes

def clearResults(branch, startdate):

    date_xx_days_ago = datetime.date.today() - datetime.timedelta(days=180)
    delete_delta_and_old_data = 'delete from testjobs where branch="%s" and (date >= "%04d-%02d-%02d %02d:%02d:%02d" or date < "%04d-%02d-%02d")' % (branch, startdate.year, startdate.month, startdate.day, startdate.hour, startdate.minute, startdate.second, date_xx_days_ago.year, date_xx_days_ago.month, date_xx_days_ago.day)

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

    job_property_names = data["job_property_names"]
    i = lambda x: job_property_names.index(x)

    for result in data.get("results", []):
        for platform in result.get("platforms", []):
            for group in platform.get("groups", []):
                for job in group.get("jobs", []):
                    # Instantiate all values to an empty string
                    _id, log, slave, result, duration, platform, buildtype, testtype, bugid = '', '', '', '', '', '', '', '', ''
                    _id = '%s' % job[i("id")]
                    # If job already in database, skip
                    cur.execute('select revision from testjobs where id=%s' % _id)
                    if cur.fetchone():
                        continue
                    # Skip if result = unknown
                    _result = job[i("result")]
                    if _result == u'unknown':
                        continue

                    duration = '%s' % (int(job[i("end_timestamp")]) - int(job[i("start_timestamp")]))

                    platform = job[i("platform")]
                    if not platform:
                        continue

                    buildtype = job[i("platform_option")]
                   
                    testtype = job[i("ref_data_name")].split()[-1]

                    # Fetch json object from the resource_uri
                    url = "https://treeherder.mozilla.org" + job[i("resource_uri")]
                    response = requests.get(url, headers={'accept-encoding':'gzip'}, verify=True)
                    data1 = response.json()

                    for j in range(len(data1.get("artifacts", []))):
			if data1.get("artifacts", [])[j].get("name", "") == u"Structured Log":
                            url = "https://treeherder.mozilla.org" + data1.get("artifacts", [])[j].get("resource_uri", "")
                            response = requests.get(url, headers={'accept-encoding':'gzip'}, verify=True)
                            data2 = response.json()
                            
                            slave = data2.get("blob", {}).get("header",{}).get("slave","")
                            break

                    if (len(data1.get("logs"))):
                        log = data1.get("logs", [])[0].get("url", "")
                    elif (data2):
                        log = data2.get("blob", {}).get("logurl", "") 

                    regression = 0

                    # Insert into MySQL Database
                    sql = 'insert into testjobs (id, log, slave, result, duration, platform, buildtype, testtype, bugid, branch, revision, date, regression) values ('
                    sql += '%s' % _id
                    sql += ", '%s'" % log
                    sql += ", '%s'" % slave
                    sql += ", '%s'" % _result
                    sql += ', %s' % duration
                    sql += ", '%s'" % platform
                    sql += ", '%s'" % buildtype
                    sql += ", '%s'" % testtype
                    sql += ", '%s'" % bugid
                    sql += ", '%s'" % branch
                    sql += ", '%s'" % revision
                    sql += ", '%s'" % date
                    sql += ", %s" % regression
                    sql += ')'
                    cur.execute(sql)
    cur.close()
   

def parseResults(args):
    db_queue, download_queue = Queue(), Queue()

    DBHandler(db_queue, name="DBHandler").start()

    for i in range(args.threads):
        Downloader(download_queue, db_queue, name="Downloader %s" % (i+1)).start()

    startdate = datetime.datetime.utcnow() - datetime.timedelta(hours=args.delta)

    if args.branch == 'all':
        result_branches = branches
    else:
        result_branches = [args.branch]

    for branch in result_branches:
        db_queue.put((CLEAR_JOB, [branch, startdate]))

    for branch in result_branches:
        revisions = getPushLog(branch, startdate)
        for revision, date in revisions:
            download_queue.put((branch, revision, date))

    download_queue.join()
    logging.info('Downloading completed')
    db_queue.join()

    #Sometimes the parent may exit and the child is not immidiately killed.
    #This may result in the error like the following -
    #
    #Exception in thread DBHandler (most likely raised during interpreter shutdown):
    #Traceback (most recent call last):
    #File "/usr/lib/python2.7/threading.py", line 810, in __bootstrap_inner
    #File "updatedb.py", line 120, in run
    #File "/usr/lib/python2.7/Queue.py", line 168, in get
    #File "/usr/lib/python2.7/threading.py", line 332, in wait
    #: 'NoneType' object is not callable
    #
    #The following line works as a fix
    #ref : http://b.imf.cc/blog/2013/06/26/python-threading-and-queue/

    time.sleep(0.1)

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
    parseResults(args)
