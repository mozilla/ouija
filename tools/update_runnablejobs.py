import copy
import datetime
import json
import logging
import os
import time

import requests
from redo import retry
from sqlalchemy import update

from database.models import JobPriorities
from database.config import session, engine

HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'ouija',
}
LOG = logging.getLogger(__name__)
TREEHERDER_HOST = 'https://treeherder.mozilla.org'
RUNNABLE_API = TREEHERDER_HOST + '/api/project/{0}/runnable_jobs/?decision_task_id={1}&format=json'


def _unique_key(job):
    """Return a key to query our uniqueness mapping system.

    This makes sure that we use a consistent key between our code and selecting jobs from the
    table.

    See row[1:4] usage in the code which selects the 2nd to 4th columns from jobpriority table.
    """
    return (job['testtype'], job['platform_option'], job['platform'])


def get_rootdir():
    path = os.path.expanduser('~/.mozilla/seta/')
    if not os.path.exists(path):
        os.makedirs(path)

    return path


def get_runnable_jobs_path():
    return os.path.join(get_rootdir(), 'runnable_jobs.json')


def sanitized_data(runnable_jobs_data):
    """We receive data from runnable jobs api and return the sanitized data that meets our needs.

    This is a loop to remove duplicates (including buildsystem -> * transformations if needed)
    By doing this, it allows us to have a single database query

    It returns sanitized_list which will contain a subset which excludes:
    * jobs that don't specify the build_platform
    * jobs that don't specify the testtype
    * if the job appears again, we replace build_system_type with '*'
    """
    map = {}
    sanitized_list = []
    if not runnable_jobs_data:
        return sanitized_list

    for job in runnable_jobs_data['results']:
        # XXX: Once this code moves to TH, the database models will have foreign keys
        #      to other tables. Specifically platform/build_platform and platform_option
        if not valid_platform(job['build_platform']):
            continue

        testtype = parse_testtype(
            build_system_type=job['build_system_type'],
            job_type_name=job['job_type_name'],
            platform_option=job['platform_option'],
            refdata=job['ref_data_name'])

        if not testtype:
            continue

        # NOTE: This is *all* the data we need from the runnable API
        new_job = {
            'platform': job['build_platform'],  # e.g. windows8-64
            'testtype': testtype,  # e.g. web-platform-tests-1
            'platform_option': job['platform_option'],  # e.g. {opt,debug}
            'build_system_type': job['build_system_type']  # e.g. {buildbot,taskcluster,*}
        }
        key = _unique_key(new_job)

        # Let's build a map of all the jobs and if duplicated change the build_system_type to *
        if key not in map:
            map[key] = job['build_system_type']
            sanitized_list.append(new_job)

        elif job['build_system_type'] != map[key]:
            previous_job = copy.deepcopy(new_job)
            previous_job['build_system_type'] = map[key]
            previous_index = sanitized_list.index(previous_job)
            # This will make so we *replace* the previous build system type with '*'
            # This also guarantees that we don't have duplicates
            sanitized_list[previous_index]['build_system_type'] = '*'

    return sanitized_list


def query_sanitized_data(repo_name='mozilla-inbound'):
    """Return sanitized jobs data based on runnable api. None if failed to obtain or no new data.

     We need to find the latest gecko decision task ID (by querying the index [1][2])
     in order to know which task ID to pass to the runnable api [3][4].

     It stores the minimal sanitized data from runnable apis under ~/.mozilla/seta/<task_id>.json

     [1] https://index.taskcluster.net/v1/task/gecko.v2.%s.latest.firefox.decision/
     [2] Index's data structure:
      {
        "namespace": "gecko.v2.mozilla-inbound.latest.firefox.decision",
        "taskId": "Dh9ZvFk5QCSprJ877cgUmw",
        "rank": 0,
        "data": {},
        "expires": "2017-10-06T18:30:18.428Z"
      }
     [3] https://treeherder.mozilla.org/api/project/mozilla-inbound/runnable_jobs/?decision_task_id=Pp7ZxoH0SKyU6wnhX_Fp0g&format=json  # flake8: noqa
     [4] NOTE: I Skip some data that is not relevant to failures.py
     {
      meta: {
        count: 2317,
        offset: 0,
        repository: mozilla-inbound,
      },
      results: [
        {
          build_platform: windows8-64,
          build_system_type: buildbot,
          job_type_name: W3C Web Platform Tests,
          platform_option: debug,
          ref_data_name: Windows 8 64-bit mozilla-inbound debug test web-platform-tests-1,
        },
        {
            "build_platform": "linux64",
            "build_system_type": "taskcluster",
            "job_type_name": "desktop-test-linux64/opt-reftest-8",
            "platform": "linux64",
            "platform_option": "opt",
            "ref_data_name": "desktop-test-linux64/opt-reftest-8",
        },
    """
    url = "https://index.taskcluster.net/v1/task/gecko.v2.%s.latest.firefox.decision/"
    try:
        latest_task = retry(
            requests.get,
            args=(url % repo_name, ),
            kwargs={'headers': {'accept-encoding': 'json'}, 'verify': True}
        ).json()
        task_id = latest_task['taskId']
    except Exception as error:
        # we will end this function if got exception here
        LOG.exception("The request for %s failed due to %s" % (url, error))
        return None

    path = os.path.join(get_rootdir(), '%s.json' % task_id)

    # we do nothing if the timestamp of runablejobs.json is equal with the latest task
    # otherwise we download and update it
    if os.path.isfile(path):
        LOG.info("We have already processed the data from this task (%s)." % task_id)
        return None
    else:
        LOG.info("We're going to fetch new runnable jobs data.")
        # We never store the output of runnable api but the minimal data we need
        data = sanitized_data(query_the_runnablejobs(repo_name=repo_name, task_id=task_id))

        if data:
            # Store the sanitized data to disk for inspection
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True)

        return data


# TODO we need add test for this function to make sure it works under any situation
def update_job_priority_table():
    """Use it to update the job priority table with data from the runnable api."""
    # XXX: We are assuming that the jobs accross 'mozilla-inbound', 'autoland' and 'fx-team' are equivalent
    #      This could cause issues in the future
    data = query_sanitized_data(repo_name='mozilla-inbound')

    if data:
        _update_job_priority_table(data)
    else:
        LOG.warning('We received an empty data set')
        return


def query_the_runnablejobs(task_id, repo_name='mozilla-inbound'):
    url = RUNNABLE_API.format(repo_name, task_id)
    try:
        data = retry(requests.get, args=(url, ), kwargs={'headers': HEADERS}).json()
        if data:
            # A lot of code components still rely on the file being on disk
            with open(get_runnable_jobs_path(), 'w') as f:
                json.dump(data, f, indent=2, sort_keys=True)

        return data
    except:
        LOG.warning("We failed to get runnablejobs via %s" % url)
        return None


def parse_testtype(build_system_type, job_type_name, platform_option, refdata):
    # TODO: figure out how to ignore build, lint, etc. jobs

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

    # TODO: these changes should have bugs on file to fix the names
    testtype = testtype.replace('browser-chrome-e10s', 'e10s-browser-chrome')
    testtype = testtype.replace('devtools-chrome-e10s', 'e10s-devtools-chrome')
    testtype = testtype.replace('[TC] Android 4.3 API15+ ', '')
    testtype = testtype.replace('jittests-', 'jittest-')

    # TODO: fix this in updatedb.py
    testtype = testtype.replace('webgl-', 'gl-')

    if testtype.startswith('[funsize'):
        return None

    return testtype


def valid_platform(platform):
    # TODO: this is very hardcoded and prone to fall out of date
    # We only care about scheduled from in-tree tests (neither autophone nor other systems)
    # We only care about tests and not builds.
    return platform not in [
        'mulet-linux64', 'b2g-device-image', 'osx-10-7', 'osx-10-9', 'osx-10-11',
        'windows8-32', 'android-4-2-armv7-api15', 'android-4-4-armv7-api15',
        'android-5-0-armv8-api15', 'android-5-1-armv7-api15', 'android-6-0-armv8-api15',
        'taskcluster-images', 'other', 'Win 6.3.9600 x86_64', 'windows7-64'
    ]


def _update_job_priority_table(data):
    """Add new jobs to the priority table and update the build system if required."""
    LOG.info('Fetch all rows from the job priority table.')
    # Get all rows of job priorities
    db_data = session.query(JobPriorities.id,
                            JobPriorities.testtype,
                            JobPriorities.buildtype,
                            JobPriorities.platform,
                            JobPriorities.priority,
                            JobPriorities.timeout,
                            JobPriorities.expires,
                            JobPriorities.buildsystem).all()

    # TODO: write test for this
    # When the table is empty it means that we're starting the system for the first time
    # and we're going to use different default values
    map = {}
    if not len(db_data) == 0:
        priority = 1
        timeout = 0
        # Using %Y-%m-%d fixes this issue:
        # Warning: Incorrect date value: '2016-10-28 17:36:58.153265' for column 'expires' at row 1
        expiration_date = (datetime.datetime.now() + datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        # Creating this data structure which will reduce how many times we iterate through the DB rows
        for row in db_data:
            key = tuple(row[1:4])
            # This is guaranteed by a unique composite index for these 3 fields in models.py
            assert key not in map,\
                '"{}" should be a unique row and that is unexpected.'.format(key)
            # (testtype, buildtype, platform)
            map[key] = {'pk': row[0], 'build_system_type': row[7]}
    else:
        priority = 5
        timeout = 5400
        expiration_date = None

    total_jobs = len(data)
    new_jobs = 0
    failed_changes = 0
    updated_jobs = 0
    # Loop through sanitized jobs, add new jobs and update the build system if needed
    for job in data:
        _buildsystem = job["build_system_type"]
        key = _unique_key(job)
        if key in map:
            # We already know about this job, we might need to update the build system
            row_build_system_type = map[key]['build_system_type']

            if row_build_system_type == '*' or _buildsystem == '*':
                # We don't need to update anything
                pass
            else:
                # We're seeing the job again but for another build system (e.g. buildbot vs
                # taskcluster). We need to change it to '*'
                if row_build_system_type != _buildsystem:
                    _buildsystem = "*"
                    # Update table with new buildsystem
                    try:
                        conn = engine.connect()
                        statement = update(JobPriorities).where(
                            JobPriorities.id == map[key]['pk_key']).values(buildsystem=_buildsystem)
                    except Exception as e:
                        LOG.info("exception updating jobPriorities: " + e)
                        LOG.info("key = %s, buildsystem = %s" % (key, _buildsystem))
                    conn.execute(statement)
                    LOG.info('Updated {}/{} from {} to {}'.format(
                        job['testtype'], job['platform_option'],
                        job['build_system_type'], _buildsystem
                    ))
                    updated_jobs += 1

        else:
            # We have a new job from runnablejobs to add to our master list
            try:
                jobpriority = JobPriorities(
                    str(job["testtype"]),
                    str(job["platform_option"]),
                    str(job["platform"]),
                    priority,
                    timeout,
                    expiration_date,
                    _buildsystem
                )
                session.add(jobpriority)
                session.commit()
                LOG.info('New job was found ({},{},{},{})'.format(
                    job['testtype'], job['platform_option'], job['platform'], _buildsystem,))
                new_jobs += 1
            except Exception as error:
                session.rollback()
                LOG.warning(error)
                failed_changes += 1
            finally:
                session.close()

    LOG.info('We have {} new jobs and {} updated jobs out of {} total jobs processed.'.format(
        new_jobs, updated_jobs, total_jobs
    ))

    if failed_changes != 0:
        LOG.error('We have failed {} changes out of {} total jobs processed.'.format(
            failed_changes, total_jobs
        ))


if __name__ == "__main__":
    update_job_priority_table()
