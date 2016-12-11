import os
import re
import calendar
import urlparse
import logging
from src import jobtypes
from functools import wraps
from itertools import groupby
from collections import Counter
from database.config import session, engine
from tools.failures import SETA_WINDOW
from datetime import datetime, timedelta
from flask_cors import CORS
from sqlalchemy import and_, func, desc, case, update
from database.models import (Testjobs, Dailyjobs,
                             TaskRequests, JobPriorities)

from flask import Flask, request, json, Response, abort

LOG = logging.getLogger(__name__)
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
static_path = os.path.join(os.path.dirname(SCRIPT_DIR), "static")
app = Flask(__name__, static_url_path="", static_folder=static_path)
CORS(app)
JOBSDATA = jobtypes.Treecodes()
RESET_DELTA = 5400
# These are necesary setup for postgresql on heroku
PORT = int(os.environ.get("PORT", 8157))
urlparse.uses_netloc.append("postgres")

try:
    DBURL = urlparse.urlparse(os.environ["DATABASE_URL"])
except:
    # use mysql
    pass


class CSetSummary(object):
    def __init__(self, cset_id):
        self.cset_id = cset_id
        self.green = Counter()
        self.orange = Counter()
        self.red = Counter()
        self.blue = Counter()


def serialize_to_json(object):
    """Serialize class objects to json"""
    try:
        return object.__dict__
    except AttributeError:
        raise TypeError(repr(object) + 'is not JSON serializable')


def json_response(func):
    """Decorator: Serialize response to json"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = json.dumps(func(*args, **kwargs) or {"error": "No data found for your request"},
                            default=serialize_to_json)
        headers = [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(result)))
        ]
        return Response(result, status=200, headers=headers)

    return wrapper


def sanitize_string(input):
    m = re.search('[a-zA-Z0-9\-\_\.]+', input)
    if m:
        return input
    else:
        return ''


def sanitize_bool(input):
    if int(input) == 0 or int(input) == 1:
        return int(input)
    else:
        return 0


def get_date_range(dates):
    if dates:
        return {'startDate': min(dates).strftime('%Y-%m-%d %H:%M'),
                'endDate': max(dates).strftime('%Y-%m-%d %H:%M')}


def clean_date_params(query_dict, delta=7):
    """Parse request date params"""
    now = datetime.now()

    # get dates params
    start_date_param = query_dict.get('startDate') or \
        query_dict.get('startdate') or \
        query_dict.get('date')
    end_date_param = query_dict.get('endDate') or \
        query_dict.get('enddate') or \
        query_dict.get('date')

    # parse dates
    end_date = (parse_date(end_date_param) or now)
    start_date = parse_date(start_date_param) or end_date - timedelta(days=delta)

    # validate dates
    if start_date > now or start_date.date() > end_date.date():
        start_date = now - timedelta(days=7)
        end_date = now + timedelta(days=1)

    return start_date.date(), end_date.date()


def parse_date(date_):
    if date_ is None:
        return

    masks = ['%Y-%m-%d',
             '%Y-%m-%dT%H:%M',
             '%Y-%m-%d %H:%M']

    for mask in masks:
        try:
            return datetime.strptime(date_, mask)
        except ValueError:
            pass


def calculate_fail_rate(passes, retries, totals):
    # skip calculation for slaves and platform with no failures
    if passes == totals:
        results = [0, 0]

    else:
        results = []
        denominators = [totals - retries, totals]
        for denominator in denominators:
            try:
                result = 100 - (passes * 100) / float(denominator)
            except ZeroDivisionError:
                result = 0
            results.append(round(result, 2))

    return dict(zip(['failRate', 'failRateWithRetries'], results))


def binify(bins, data):
    result = []
    for i, bin in enumerate(bins):
        if i > 0:
            result.append(len(filter(lambda x: x >= bins[i - 1] and x < bin, data)))
        else:
            result.append(len(filter(lambda x: x < bin, data)))

    result.append(len(filter(lambda x: x >= bins[-1], data)))

    return result


@app.route("/data/results/flot/day/")
@json_response
def run_results_day_flot_query():
    """
    This function returns the total failures/total jobs data per day for all platforms.
    It is sending the data in the format required by flot.Flot is a jQuery package used
    for 'attractive' plotting
    """
    start_date, end_date = clean_date_params(request.args)

    platforms = ['android4.0',
                 'android2.3',
                 'linux32',
                 'winxp',
                 'win7',
                 'win8',
                 'osx10.6',
                 'osx10.7',
                 'osx10.8']

    data_platforms = {}
    for platform in platforms:
        query_results = session.query(Testjobs.date.label('day'),
                                      func.count(Testjobs.result == 'testfailed'
                                                 ).label("failures"),
                                      func.count(Testjobs).label('totals')).filter(
            and_(Testjobs.platform == platform,
                 Testjobs.date >= start_date, Testjobs.date <= end_date)).group_by('day').all()

        dates = []
        data = {}
        data['failures'] = []
        data['totals'] = []

        for day, fail, total in query_results:
            dates.append(day)
            timestamp = calendar.timegm(day.timetuple()) * 1000
            data['failures'].append((timestamp, int(fail)))
            data['totals'].append((timestamp, int(total)))

        data_platforms[platform] = {'data': data, 'dates': get_date_range(dates)}

    session.close()
    return data_platforms


@app.route("/data/slaves/")
@json_response
def run_slaves_query():
    start_date, end_date = clean_date_params(request.args)

    days_to_show = (end_date - start_date).days
    if days_to_show <= 8:
        jobs = 5
    else:
        jobs = int(round(days_to_show * 0.4))

    info = 'Only slaves with more than %d jobs are displayed.' % jobs

    query_results = session.query(Testjobs.slave, Testjobs.result, Testjobs.date).filter(
        and_(Testjobs.result.in_(["retry", "testfailed", "success", "busted", "exception"]),
             Testjobs.date.between(start_date, end_date))).all().order_by(Testjobs.date)
    session.close()

    if not query_results:
        return

    data = {}
    labels = 'fail retry infra success total'.split()
    summary = {result: 0 for result in labels}
    summary['jobs_since_last_success'] = 0
    dates = []

    for name, result, date in query_results:
        data.setdefault(name, summary.copy())
        data[name]['jobs_since_last_success'] += 1
        if result == 'testfailed':
            data[name]['fail'] += 1
        elif result == 'retry':
            data[name]['retry'] += 1
        elif result == 'success':
            data[name]['success'] += 1
            data[name]['jobs_since_last_success'] = 0
        elif result == 'busted' or result == 'exception':
            data[name]['infra'] += 1
        data[name]['total'] += 1
        dates.append(date)

    # filter slaves
    slave_list = [slave for slave in data if data[slave]['total'] > jobs]

    # calculate failure rate only for slaves that we're going to display
    for slave in slave_list:
        results = data[slave]
        fail_rates = calculate_fail_rate(results['success'],
                                         results['retry'],
                                         results['total'])
        data[slave]['sfr'] = fail_rates

    platforms = {}

    # group slaves by platform and calculate platform failure rate
    slaves = sorted(data.keys())
    for platform, slave_group in groupby(slaves, lambda x: x.rsplit('-', 1)[0]):
        slaves = list(slave_group)

        # don't calculate failure rate for platform we're not going to show
        if not any(slave in slaves for slave in slave_list):
            continue

        platforms[platform] = {}
        results = {}

        for label in ['success', 'retry', 'total']:
            r = reduce(lambda x, y: x + y,
                       [data[slave][label] for slave in slaves])
            results[label] = r

        fail_rates = calculate_fail_rate(results['success'],
                                         results['retry'],
                                         results['total'])
        platforms[platform].update(fail_rates)

    # remove data that we don't need
    for slave in data.keys():
        if slave not in slave_list:
            del data[slave]

    return {'slaves': data,
            'platforms': platforms,
            'dates': get_date_range(dates),
            'disclaimer': info}


@app.route("/data/platform/")
@json_response
def run_platform_query():
    platform = sanitize_string(request.args.get("platform"))
    build_system_type = sanitize_string(request.args.get("build_system_type"))
    start_date, end_date = clean_date_params(request.args)

    log_message = 'platform: %s startDate: %s endDate: %s' % (platform,
                                                              start_date.strftime('%Y-%m-%d'),
                                                              end_date.strftime('%Y-%m-%d'))
    app.logger.debug(log_message)

    csets = session.query(Testjobs.revision).distinct().\
        filter(and_(Testjobs.platform == platform,
                    Testjobs.branch == 'mozilla-central',
                    Testjobs.date.between(start_date, end_date),
                    Testjobs.build_system_type == build_system_type)).order_by(desc(Testjobs.date))

    cset_summaries = []
    test_summaries = {}
    dates = []

    labels = 'green orange blue red'.split()
    summary = {result: 0 for result in labels}

    for cset in csets:
        cset_id = cset[0]
        cset_summary = CSetSummary(cset_id)

        test_results = session.query(Testjobs.result, Testjobs.testtype, Testjobs.date).\
            filter(and_(Testjobs.platform == platform,
                        Testjobs.buildtype == 'opt',
                        Testjobs.revision == cset_id,
                        Testjobs.build_system_type == build_system_type)).all().order_by(
            Testjobs.testtype)

        for res, testtype, date in test_results:
            test_summary = test_summaries.setdefault(testtype, summary.copy())

            if res == 'success':
                cset_summary.green[testtype] += 1
                test_summary['green'] += 1
            elif res == 'testfailed':
                cset_summary.orange[testtype] += 1
                test_summary['orange'] += 1
            elif res == 'retry':
                cset_summary.blue[testtype] += 1
                test_summary['blue'] += 1
            elif res == 'exception' or res == 'busted':
                cset_summary.red[testtype] += 1
                test_summary['red'] += 1
            elif res == 'usercancel':
                app.logger.debug('usercancel')
            else:
                app.logger.debug('UNRECOGNIZED RESULT: %s' % res)
            dates.append(date)

        cset_summaries.append(cset_summary)

    # sort tests alphabetically and append total & percentage to end of the list
    test_types = sorted(test_summaries.keys())
    test_types += ['total', 'percentage']

    # calculate total stats and percentage
    total = Counter()
    percentage = {}

    for test in test_summaries:
        total.update(test_summaries[test])
    test_count = sum(total.values())

    for key in total:
        percentage[key] = round((100.0 * total[key] / test_count), 2)

    fail_rates = calculate_fail_rate(passes=total['green'],
                                     retries=total['blue'],
                                     totals=test_count)

    test_summaries['total'] = total
    test_summaries['percentage'] = percentage
    session.close()
    return {'testTypes': test_types,
            'byRevision': cset_summaries,
            'byTest': test_summaries,
            'failRates': fail_rates,
            'dates': get_date_range(dates)}


@app.route("/data/jobtypes/")
@json_response
def run_jobtypes_query():
    return {'jobtypes': JOBSDATA.jobtype_query()}


@app.route("/data/seta/")
@json_response
def run_seta_query():
    start_date, end_date = clean_date_params(request.args, delta=SETA_WINDOW)

    # we would like to enlarge the datetime range to make sure the latest failures been get.
    start_date = start_date - timedelta(days=1)
    end_date = end_date + timedelta(days=1)
    data = session.query(Testjobs.bugid, Testjobs.platform, Testjobs.buildtype, Testjobs.testtype,
                         Testjobs.duration).filter(and_(Testjobs.failure_classification == 2,
                                                        Testjobs.date >= start_date,
                                                        Testjobs.date <= end_date)).all()
    failures = {}
    for d in data:
        failures.setdefault(d[0], []).append(d[1:])

    return {'failures': failures}


@app.route("/data/setadetails/")
@json_response
def run_seta_details_query():
    buildbot = sanitize_bool(request.args.get("buildbot", 0))
    branch = sanitize_string(request.args.get("branch", 'mozilla-inbound'))
    taskcluster = sanitize_bool(request.args.get("taskcluster", 0))
    priority = int(sanitize_string(request.args.get("priority", '5')))
    jobnames = JOBSDATA.jobnames_query()
    date = str(datetime.now().date())
    retVal = {}
    retVal[date] = []
    jobtype = []

    # we only support fx-team, autoland, and mozilla-inbound branch in seta
    if (str(branch) in ['fx-team', 'mozilla-inbound', 'autoland']) is not True \
            and str(branch) != '':
        abort(404)

    # For the case of TaskCluster request, we don't care which priority the user request.
    # We return jobs depend on the strategy that we return high value jobs as default and
    # return all jobs for every 5 push or 90 minutes for that branch.
    if request.headers.get('User-Agent', '') == 'TaskCluster':
        # we make taskcluster to 1 if it's a request from taskcluster, it's more reasonable and
        # can simplify the request url.
        taskcluster = 1

        # we will return all jobs for every 90 minutes, so the return_all_jobs flag will been
        # set to true if the time limit been reached.
        return_all_jobs = False

        # We should return full job list as a fallback, if it's a request from
        # taskcluster and without head_rev or pushlog_id in there
        try:
            branch_info = session.query(TaskRequests.counter,
                                        TaskRequests.datetime,
                                        TaskRequests.reset_delta).filter(
                TaskRequests.branch == branch).all()
        except:
            branch_info = []
        time_of_now = datetime.now()

        # If we got nothing related with that branch, we should create it.
        if len(branch_info) == 0:
            # time_of_lastreset is not a good name anyway :(
            # And we treat all branches' reset_delta is 90 seconds, we should find a
            # better delta for them in the further.
            branch_data = TaskRequests(str(branch), 1, time_of_now, RESET_DELTA)
            try:
                session.add(branch_data)
                session.commit()
            except Exception as error:
                LOG.debug(error)
                session.rollback()

            finally:
                session.close()
            counter = 1
            time_string = time_of_now
            reset_delta = RESET_DELTA

        # We should update it if that branch had already been stored.
        else:
            counter, time_string, reset_delta = branch_info[0]
            counter += 1
            conn = engine.connect()
            statement = update(TaskRequests).where(
                TaskRequests.branch == branch).values(
                counter=counter)
            conn.execute(statement)

        delta = (time_of_now - time_string).total_seconds()

        # we should update the time recorder if the elapse time had
        # reach the time limit of that branch.
        if delta >= reset_delta:
            conn = engine.connect()
            statement = update(TaskRequests).where(
                TaskRequests.branch == branch).values(
                datetime=time_of_now)
            conn.execute(statement)

            # we need to set the return_all_jobs flag to true.
            return_all_jobs = True

        # we query all jobs rather than jobs filter by the requested priority in here,
        # Because we need to set the job returning strategy depend on different job priority.
        query = session.query(JobPriorities.platform,
                              JobPriorities.buildtype,
                              JobPriorities.testtype,
                              JobPriorities.priority,
                              JobPriorities.timeout
                              ).all()

        for d in query:
            # we only return that job if it hasn't reach the timeout limit. And the
            # timeout is zero means this job need always running.
            if delta < d[4] or d[4] == 0:
                # Due to the priority of all high value jobs is 1, and we
                # need to return all jobs for every 5 pushes(for now).
                if counter % d[3] != 0:
                    jobtype.append([d[0], d[1], d[2]])

            # we need to return all jobs for every 90 minutes, so all jobs will been returned
            # if the delta is larger than 5400
            elif return_all_jobs:
                jobtype.append([d[0], d[1], d[2]])

    # We don't care about the timeout variable of job if it's not a taskcluster request.
    else:
        query = session.query(JobPriorities.platform,
                              JobPriorities.buildtype,
                              JobPriorities.testtype,
                              JobPriorities.priority,
                              ).all()

        # priority = 0; run all the jobs
        if priority != 1 and priority != 5:
            priority = 0

        # Because we store high value jobs in seta table as default,
        # so we return low value jobs, means no failure related with this job as default
        if priority == 0:
            jobtype = JOBSDATA.jobtype_query()  # All jobs regardless of priority
        # priority =5 run all low value jobs
        else:
            joblist = [job for job in query if job[3] == priority]
            for j in joblist:
                jobtype.append([j[0], j[1], j[2]])

        # TODO: filter out based on buildsystem from database, either 'buildbot' or '*'
        if buildbot:
            active_jobs = []
            # pick up buildbot jobs from job list to faster the filter process
            buildbot_jobs = [job for job in jobnames if job['buildplatform'] == 'buildbot']
            # find out the correspond job detail information
            for job in jobtype:
                for j in buildbot_jobs:
                    if j['name'] == job[2] and j['platform'] == job[0] and j['buildtype'] == job[1]:
                        active_jobs.append(j['ref_data_name'] if branch is 'mozilla-inbound'
                                           else j['ref_data_name'].replace(
                                               'mozilla-inbound', branch))

            jobtype = active_jobs

    # TODO: filter out based on buildsystem from database, either 'taskcluster' or '*'
    if taskcluster:
        active_jobs = []
        taskcluster_jobs = [job for job in jobnames if job['buildplatform'] == 'taskcluster']
        for job in jobtype:
            # we need to retranslate the jobtype back to the proper data form after all.
            job[2] = job[2].replace('e10s-browser-chrome', 'browser-chrome-e10s')
            job[2] = job[2].replace('e10s-devtools-chrome', 'devtools-chrome-e10s')
            job[2] = job[2].replace('gl-', 'webgl-')

            for j in taskcluster_jobs:
                if job[2] in j['name'] and j['platform'] == job[0] and j['buildtype'] == job[1]:
                    active_jobs.append(j['ref_data_name'])
        jobtype = active_jobs

    retVal[date] = jobtype
    return {"jobtypes": retVal}


@app.route("/data/jobnames/")
@json_response
def run_jobnames_query():
    # inbound is a safe default
    json_jobnames = {'results': JOBSDATA.jobnames_query()}

    return json_jobnames


@app.route("/data/dailyjobs/")
@json_response
def run_dailyjob_query():
    start_date, end_date = clean_date_params(request.args)
    start_date = start_date - timedelta(days=1)
    end_date = end_date + timedelta(days=1)
    data = session.query(Dailyjobs.date, Dailyjobs.platform, Dailyjobs.branch, Dailyjobs.numjobs,
                         Dailyjobs.sumduration).\
        filter(Dailyjobs.date.between(start_date, end_date)).order_by(case([
            (Dailyjobs.platform == 'linux', 1),
            (Dailyjobs.platform == 'osx', 2),
            (Dailyjobs.platform == 'win', 3),
            (Dailyjobs.platform == 'android', 4)], else_='5')).all()

    output = {}
    for rows in data:
        date = str(rows[0])
        platform = rows[1]
        branch = rows[2]
        numpushes = int(rows[3])
        numjobs = int(rows[4])
        sumduration = int(rows[5])

        if date not in output:
            output[date] = {'mozilla-inbound': [], 'fx-team': [], 'try': [], 'autoland': []}
        if 'mozilla-inbound' in branch:
            output[date]['mozilla-inbound'].append([platform, numpushes, numjobs, sumduration])
        elif 'fx-team' in branch:
            output[date]['fx-team'].append([platform, numpushes, numjobs, sumduration])
        elif 'try' in branch:
            output[date]['try'].append([platform, numpushes, numjobs, sumduration])
        elif 'autoland' in branch:
            output[date]['autoland'].append([platform, numpushes, numjobs, sumduration])
    return {'dailyjobs': output}


@app.errorhandler(404)
@json_response
def handler404(error):
    return {"status": 404, "msg": str(error)}


@app.route("/")
def root_directory():
    return template("index.html")


@app.route("/<string:filename>")
def template(filename):
    filename = os.path.join(static_path, filename)
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            response_body = f.read()
        return response_body
    abort(404)


def update_preseed():
    """
    We sync preseed.json to jobpririties in server on startup, since that is
    the only time we expect preseed.json to change.
    """

    # get preseed data first
    preseed_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'src', 'preseed.json')
    preseed = []
    with open(preseed_path, 'r') as fHandle:
        preseed = json.load(fHandle)

    # Preseed data will have fields: buildtype,testtype,platform,priority,timeout,expires
    # The expires field defaults to 2 weeks on a new job in the database
    # Expires field has a date "YYYY-MM-DD", but can have "*" to indicate never
    # Typical priority will be 1, but if we want to force coalescing we can do that
    # One hack is that if we have a * in a buildtype,testtype,platform field, then
    # we assume it is for all flavors of the * field: i.e. linux64,pgo,* - all tests
    # assumption - preseed fields are sanitized already - move parse_testtype to utils.py ?

    for job in preseed:
        data = session.query(JobPriorities.id,
                             JobPriorities.testtype,
                             JobPriorities.buildtype,
                             JobPriorities.platform,
                             JobPriorities.priority,
                             JobPriorities.timeout,
                             JobPriorities.expires,
                             JobPriorities.buildsystem)
        if job['testtype'] != '*':
            data = data.filter(getattr(JobPriorities, 'testtype') == job['testtype'])

        if job['buildtype'] != '*':
            data = data.filter(getattr(JobPriorities, 'buildtype') == job['buildtype'])

        if job['platform'] != '*':
            data = data.filter(getattr(JobPriorities, 'platform') == job['platform'])

        data = data.all()

        _buildsystem = job["build_system_type"]

        # TODO: edge case: we add future jobs with a wildcard, when jobs show up
        #       remove the wildcard, apply priority/timeout/expires to new jobs
        # Deal with the case where we have a new entry in preseed
        if len(data) == 0:
            _expires = job['expires']
            if _expires == '*':
                _expires = str(datetime.now().date() + timedelta(days=365))

            LOG.info("adding a new unknown job to the database: %s" % job)
            newjob = JobPriorities(job['testtype'],
                                   job['buildtype'],
                                   job['platform'],
                                   job['priority'],
                                   job['timeout'],
                                   _expires,
                                   _buildsystem)
            session.add(newjob)
            session.commit()
            session.close()
            continue

        # We can have wildcards, so loop on all returned values in data
        for d in data:
            changed = False
            LOG.info("updating existing job %s/%s/%s" % (d[1], d[2], d[3]))
            _expires = job['expires']
            _priority = job['priority']
            _timeout = job['timeout']

            # we have a taskcluster job in the db, and new job in preseed
            if d[7] != _buildsystem:
                _buildsystem = "*"
                changed = True

            # When we have a defined date to expire a job, parse and use it
            if _expires == '*':
                _expires = str(datetime.now().date() + timedelta(days=365))

            try:
                dv = datetime.strptime(_expires, "%Y-%M-%d").date()
            except ValueError:
                continue

            # When we have expired, use existing priority/timeout, reset expires
            if dv <= datetime.now().date():
                LOG.info("  --  past the expiration date- reset!")
                _expires = ''
                _priority = d[4]
                _timeout = d[5]
                changed = True

            if changed:
                # TODO: do we need to try/except/finally with commit/rollback statements
                conn = engine.connect()
                statement = update(JobPriorities).where(
                    JobPriorities.id == d[0]).values(
                    priority=_priority,
                    timeout=_timeout,
                    expires=_expires,
                    buildsystem=_buildsystem)
                conn.execute(statement)


if __name__ == "__main__":
    update_preseed()
    app.run(host="0.0.0.0", port=PORT, debug=True)
