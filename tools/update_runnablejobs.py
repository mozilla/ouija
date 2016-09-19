import os
import json
import time
import datetime
import requests
import logging

from redo import retry

#TODO: reduce this if possible
from database.models import JobPriorities
from database.config import session


headers = {
    'Accept': 'application/json',
    'User-Agent': 'ouija',
}
logger = logging.getLogger(__name__)
TREEHERDER_HOST = "https://treeherder.mozilla.org/api/project/{0}/" \
                  "runnable_jobs/?decisionTaskID={1}&format=json"

def get_rootdir():

    path = os.path.expanduser('~/.mozilla/seta/')
    if not os.path.exists(path):
        os.makedirs(path)

    return path


# TODO we need add test for this function to make sure it works under any situation
def update_runnableapi():
    """Use it to update runnablejobs.json file."""
    url = "https://index.taskcluster.net/v1/task/gecko.v2.%s.latest.firefox.decision/"
    try:
        latest_task = retry(requests.get, args=(url % "mozilla-inbound", ),
                            kwargs={'headers': {'accept-encoding': 'json'},
                                    'verify': True}).json()
    except Exception as error:
        # we will end this function if got exception here
        logger.debug("the request to %s failed, due to %s" % (url, error))
        return
    task_id = latest_task['taskId']

    # The format of expires is like 2017-07-04T22:13:23.248Z and we only want 2017-07-04 part
    expires = latest_task['expires'].split('T')[0]
    time_tuple = datetime.datetime.strptime(expires, "%Y-%m-%d").timetuple()
    new_timestamp = time.mktime(time_tuple)
    path = get_rootdir() + '/runnablejobs.json'

    # we do nothing if the timestamp of runablejobs.json is equal with the latest task
    # otherwise we download and update it
    if os.path.isfile(path):
        with open(path, 'r') as data:
            # read the timesstamp of this task from json file
            oldtime = json.loads(data.read())['meta']['timetamp']
        if oldtime == new_timestamp:
            print "The runnable json file is latest already."
            return
        else:
            print "It's going to update your runnable jobs data."
            data = query_the_runnablejobs(new_timestamp, task_id)
            new_jobs = add_jobs_to_jobpriority(new_data=data,
                                               priority=1,
                                               timeout=0,
                                               set_expired=True)
            with open(path, 'w') as f:
                json.dump(data, f)
    else:
        print "It's going to help you download the runnable jobs file."
        data = query_the_runnablejobs(new_timestamp, task_id)
        if data:
            with open(path, 'w') as f:
                json.dump(data, f)
            add_jobs_to_jobpriority(new_data=data, priority=5, timeout=5400)


def query_the_runnablejobs(new_timestamp, task_id=None):
    if task_id:
        url = TREEHERDER_HOST.format('mozilla-inbound', task_id)
        try:
            data = retry(requests.get, args=(url, ), kwargs={'headers': headers}).json()
            if len(data['results']) > 0:
                data['meta'].update({'timetamp': new_timestamp})
        except:
            print "failed to get runnablejobs via %s" % url
            print "We have something wrong with the runnable api, switch to the old runnablejobs.json now"
            with open(get_rootdir() + '/runnablejobs.json', 'r') as data:
                data = json.loads(data.read())
        return data


def parse_testtype(build_system_type, refdata, platform_option, job_type_name):
    #TODO: figure out how to ignore build, lint, etc. jobs

    if build_system_type == 'buildbot':
        return refdata.split(' ')[-1]

    # taskcluster test types
    testtype = job_type_name
    testtype = testtype.split('/opt-')[-1]
    testtype = testtype.split('/debug-')[-1]

    # this is plain-reftests for android
    testtype = testtype.replace('plain-', '')

    # SETA/Ouija do not care about builds, or other jobs like lint, etc.
    testtype = testtype.replace(' Opt', 'build')
    testtype = testtype.replace(' Debug', 'build')
    testtype = testtype.replace(' Dbg', 'build')
    testtype = testtype.replace(' (opt)', 'build')
    testtype = testtype.replace(' PGO Opt', 'build')
    testtype = testtype.replace(' Valgrind Opt', 'build')
    testtype = testtype.replace(' Artifact Opt', 'build')
    testtype = testtype.replace(' (debug)', 'build')

    testtype = testtype.strip(' ')

    #TODO: these changes should have bugs on file to fix the names
    testtype = testtype.replace('browser-chrome-e10s', 'e10s-browser-chrome')
    testtype = testtype.replace('devtools-chrome-e10s', 'e10s-devtools-chrome')
    testtype = testtype.replace('[TC] Android 4.3 API15+ ', '')
    testtype = testtype.replace('jittests-', 'jittest-')

    if testtype.startswith('[funsize'):
        return None

    return testtype


def parse_platform(platform):
    if platform in ['mulet-linux64', 'b2g-device-image',
                    'osx-10-7', 'osx-10-9', 'osx-10-11', 'windows8-32',
                    'android-4-2-armv7-api15', 'android-4-4-armv7-api15',
                    'android-5-0-armv8-api15', 'android-5-1-armv7-api15',
                    'android-6-0-armv8-api15', 'taskcluster-images', 'other',
                    'Win 6.3.9600 x86_64', 'windows7-64']:
        return None
    return platform


def add_jobs_to_jobpriority(new_data=None, priority=1, timeout=0, set_expired=False):
    added_jobs = []

    if not new_data:
        return

    db_data = []
    db_data = session.query(JobPriorities.id,
                            JobPriorities.testtype,
                            JobPriorities.buildtype,
                            JobPriorities.platform,
                            JobPriorities.priority,
                            JobPriorities.timeout,
                            JobPriorities.expires).all()

    if db_data != []:
        new_jobs = [new_job for new_job in new_data['results']
                    if new_job not in db_data]
        if len(new_jobs) <= 0:
            return
    else:
        new_jobs = new_data['results']

    for job in new_jobs:
        platform = parse_platform(job['build_platform'])
        if platform == None or platform == "":
            continue

        testtype = parse_testtype(job['build_system_type'],
                                  job['ref_data_name'],
                                  job['platform_option'],
                                  job['job_type_name'])
        if testtype == None or testtype == "":
            continue

        found = False
        for row in db_data:
            if (row[1] == testtype and
                row[3] == platform and
                row[2] == job["platform_option"]):
                found = True

        # We have new jobs from runnablejobs to add to our master list
        if not found:
            _expired = None
            if set_expired:
                # set _expired = today + 14 days
                # TODO: test this, write test for it
                _expired = "%s" % (datetime.datetime.now() + datetime.timedelta(days=14))

            try:
                jobpriority = JobPriorities(str(testtype),
                                            str(job["platform_option"]),
                                            str(job["build_platform"]),
                                            priority,
                                            timeout,
                                            _expired)

                session.add(jobpriority)
                session.commit()
                added_jobs.append(job)
            except Exception as error:
                session.rollback()
                logging.warning(error)
            finally:
                session.close()

    return added_jobs


if __name__ == "__main__":
    update_runnableapi()
