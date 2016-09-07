import os
import re
import calendar
import urlparse
from src import jobtypes
from functools import wraps
from itertools import groupby
from collections import Counter
from database.config import session
from tools.failures import SETA_WINDOW
from datetime import datetime, timedelta
from sqlalchemy import and_, func, desc, case
from database.models import Seta, Testjobs, Dailyjobs

from flask import Flask, request, json, Response, abort

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
static_path = os.path.join(os.path.dirname(SCRIPT_DIR), "static")
app = Flask(__name__, static_url_path="", static_folder=static_path)
JOBSDATA = jobtypes.Treecodes()

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

    info = '''Only slaves with more than %d jobs are displayed.''' % jobs

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


@app.route("/data/setasummary/")
@json_response
def run_seta_summary_query():
    query = session.query(Seta.date).distinct().all()
    retVal = {}
    dates = []
    for d in query:
        dates.append(d[0].strftime("%Y-%m-%d"))

    for d in dates:
        count = session.query(Seta.id).filter(Seta.date == d).count()
        retVal['%s' % d] = "%s" % int(count)

    return {'dates': retVal}


@app.route("/data/setadetails/")
@json_response
def run_seta_details_query():
    startDate, date = clean_date_params(request.args)
    active = sanitize_bool(request.args.get("active", 0))
    buildbot = sanitize_bool(request.args.get("buildbot", 0))
    branch = sanitize_string(request.args.get("branch", ''))
    taskcluster = sanitize_bool(request.args.get("taskcluster", 0))
    priority = sanitize_string(request.args.get("priority", "low"))
    jobnames = JOBSDATA.jobnames_query()
    if date == "" or date == "latest":
        today = datetime.now()
        date = today.strftime("%Y-%m-%d")
    date = "%s" % date
    query = session.query(Seta.jobtype).filter(Seta.date == date).all()
    retVal = {}
    retVal[date] = []
    jobtype = []

    # we only support fx-team and mozilla-inbound branch in seta
    if (str(branch) in ['fx-team', 'mozilla-inbound', 'autoland']) is not True \
            and str(branch) != '':
        abort(404)
    for d in query:
        parts = d[0].split("'")
        jobtype.append([parts[1], parts[3], parts[5]])

    alljobs = JOBSDATA.jobtype_query()

    # Because we store high value jobs in seta table as default,
    # so we return low value jobs(default) when the priority is 'low',
    # otherwise we return high value jobs.
    if priority == 'low':
        low_value_jobs = [low_value_job for low_value_job in alljobs if
                          low_value_job not in jobtype]
        jobtype = low_value_jobs

    if active:
        active_jobs = []
        for job in alljobs:
            found = False
            for j in jobtype:
                if j[0] == job[0] and j[1] == job[1] and j[2] == job[2]:
                    found = True
                    break
            if not found:
                active_jobs.append(job)
        jobtype = active_jobs

    if buildbot:
        active_jobs = []
        # pick up buildbot jobs from job list to faster the filter process
        buildbot_jobs = [job for job in jobnames if job['buildplatform'] == 'buildbot']
        # find out the correspond job detail information
        for job in jobtype:
            for j in buildbot_jobs:
                if j['name'] == job[2] and j['platform'] == job[0] and j['buildtype'] == job[1]:
                    active_jobs.append(j['ref_data_name'] if branch is 'mozilla-inbound'
                                       else j['ref_data_name'].replace('mozilla-inbound', branch))

        jobtype = active_jobs

    if taskcluster:
        active_jobs = []
        taskcluster_jobs = [job for job in jobnames if job['buildplatform'] == 'taskcluster']
        for job in jobtype:
            for j in taskcluster_jobs:
                if j['name'] == job[2] and j['platform'] == job[0] and j['buildtype'] == job[1]:
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
