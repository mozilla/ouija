#!/usr/bin/env python

import os
import calendar
from datetime import datetime, timedelta
from itertools import groupby
from collections import Counter
from functools import wraps

import MySQLdb
from flask import Flask, request, json, Response, abort

static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
app = Flask(__name__, static_url_path="", static_folder=static_path)

class CSetSummary(object):
    def __init__(self, cset_id):
        self.cset_id = cset_id
        self.green = Counter()
        self.orange = Counter()
        self.red = Counter()
        self.blue = Counter()


def create_db_connnection():
    return MySQLdb.connect(host="localhost",
                           user="root",
                           passwd="root",
                           db="ouija")


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


def get_date_range(dates):
    if dates:
        return {'startDate': min(dates).strftime('%Y-%m-%d %H:%M'),
                'endDate': max(dates).strftime('%Y-%m-%d %H:%M')}


def clean_date_params(query_dict, delta=7):
    """Parse request date params"""
    now = datetime.now()

    # get dates params
    start_date_param = query_dict.get('startDate') or query_dict.get('startdate')
    end_date_param = query_dict.get('endDate') or query_dict.get('enddate')

    # parse dates
    end_date = (parse_date(end_date_param) or now)
    start_date = parse_date(start_date_param) or end_date - timedelta(days=delta)

    # validate dates
    if start_date > now or start_date.date() >= end_date.date():
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
    """ This function returns the total failures/total jobs data per day for all platforms. It is sending the data in the format required by flot.Flot is a jQuery package used for 'attractive' plotting """

    start_date, end_date = clean_date_params(request.args)

    platforms = ['android4.0', 'android2.3', 'linux32', 'winxp', 'win7', 'win8', 'osx10.6', 'osx10.7', 'osx10.8']
    db = create_db_connnection()

    data_platforms = {}
    for platform in platforms:
        cursor = db.cursor()
        cursor.execute("""select DATE(date) as day,sum(result="%s") as failures,count(*) as totals from testjobs
                          where platform="%s" and date >= "%s" and date <= "%s" group by day""" % ('testfailed', platform, start_date, end_date))

        query_results = cursor.fetchall()

        dates = []
        data = {}
        data['failures'] = []
        data['totals'] = []

        for day, fail, total in query_results:
            dates.append(day)
            timestamp = calendar.timegm(day.timetuple()) * 1000
            data['failures'].append((timestamp, int(fail)))
            data['totals'].append((timestamp, int(total)))

        cursor.close()

        data_platforms[platform] = {'data': data, 'dates': get_date_range(dates)}

    db.close()
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

    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select slave, result, date from testjobs
                      where result in
                      ("retry", "testfailed", "success", "busted", "exception")
                      and date between "{0}" and "{1}"
                      order by date;""".format(start_date, end_date))

    query_results = cursor.fetchall()
    cursor.close()
    db.close()

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
    platform = request.args.get("platform")
    start_date, end_date = clean_date_params(request.args)

    log_message = 'platform: %s startDate: %s endDate: %s' % (platform,
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d'))
    app.logger.debug(log_message)

    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select distinct revision from testjobs
                      where platform = '%s'
                      and branch = 'mozilla-central'
                      and date between '%s' and '%s'
                      order by date desc;""" % (platform, start_date, end_date))

    csets = cursor.fetchall()

    cset_summaries = []
    test_summaries = {}
    dates = []

    labels = 'green orange blue red'.split()
    summary = {result: 0 for result in labels}

    for cset in csets:
        cset_id = cset[0]
        cset_summary = CSetSummary(cset_id)

        cursor.execute("""select result, testtype, date from testjobs
                          where platform='%s' and buildtype='opt' and revision='%s'
                          order by testtype""" % (platform, cset_id))

        test_results = cursor.fetchall()

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
                app.logger.debug('UNRECOGNIZED RESULT: %s' % result)
            dates.append(date)

        cset_summaries.append(cset_summary)

    cursor.close()
    db.close()

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

    return {'testTypes': test_types,
            'byRevision': cset_summaries,
            'byTest': test_summaries,
            'failRates': fail_rates,
            'dates': get_date_range(dates)}


def jobtype_query():
    db = create_db_connnection()
    cursor = db.cursor()
    query = "select platform, buildtype, testtype from uniquejobs"
    cursor.execute(query)
    jobtypes = []
    for d in cursor.fetchall():
        jobtypes.append([d[0], d[1], d[2]])

    return jobtypes

@app.route("/data/jobtypes/")
@json_response
def run_jobtypes_query():
    return {'jobtypes': jobtype_query()}


@app.route("/data/create_jobtypes/")
@json_response
def run_create_jobtypes_query():
    # skipping b2g*, android*, mulet*, osx-10-10
    platforms = ['osx-10-6', 'osx-10-8', 'windowsxp', 'windows7-32', 'linux32', 'linux64', 'windows8-64']

    # skipping pgo - We run this infrequent enough that we should have all pgo results tested
    buildtypes = ['debug', 'asan', 'opt']

    now = datetime.now()
    twoweeks = now - timedelta(days=14)
    twoweeks = twoweeks.strftime('%Y-%m-%d')

    jobtypes = []
    db = create_db_connnection()
    for platform in platforms:
        for buildtype in buildtypes:
            # ignore *build* types
            query = """select distinct testtype from testjobs where date>'%s' and platform='%s'
                       and buildtype='%s' and testtype not like '%%build%%'
                       and testtype not like '%%_dep'""" % (twoweeks, platform, buildtype)
            cursor = db.cursor()
            cursor.execute(query)
            types = []
            for testtype in cursor.fetchall():
                testtype = testtype[0]
                # ignore talos, builds, jetpack
                if testtype in ['svgr', 'svgr-e10s', 'svgr-snow', 'svgr-snow-e10s',
                                'other', 'other-e10s', 'other-snow', 'other-snow-e10s', 
                                'chromez', 'chromez-e10s', 'chromez-snow', 'chromez-snow-e10s',
                                'tp5o', 'tp5o-e10s', 'dromaeojs', 'dromaeojs-e10s',
                                'g1', 'g1-e10s', 'g1-snow', 'g1-snow-e10s', 
                                'other_nol64', 'other_nol64-e10s', 'other_l64', 'other_l64-e10s',
                                'xperf', 'xperf-e10s', 'dep', 'nightly', 'jetpack',
                                'non-unified', 'valgrind']:
                    continue

                if testtype:
                    types.append(testtype)

            types.sort()
            for testtype in types:
                jobtypes.append([platform, buildtype, testtype])

    cursor.execute("delete from uniquejobs");
    for j in jobtypes:
        query = "insert into uniquejobs (platform, buildtype, testtype) values ('%s', '%s', '%s')" % (j[0], j[1], j[2])
        cursor.execute(query)

    return {'status': 'ok'}


@app.route("/data/seta/")
@json_response
def run_seta_query():
    start_date, end_date = clean_date_params(request.args, delta=180)

    db = create_db_connnection()
    cursor = db.cursor()
    query = "select bugid, platform, buildtype, testtype, duration from testjobs where failure_classification=2 and date>='%s' and date<='%s'" % (start_date, end_date)
    cursor.execute(query)
    failures = {}
    for d in cursor.fetchall():
        failures.setdefault(d[0], []).append(d[1:])

    return {'failures': failures}


@app.route("/data/setasummary/")
@json_response
def run_seta_summary_query():
    db = create_db_connnection()
    cursor = db.cursor()
    query = "select distinct date from seta"
    cursor.execute(query)
    retVal = {}
    dates = []
    for d in cursor.fetchall():
        dates.append(d[0])

    for d in dates:
        query = "select count(id) from seta where date='%s'" % d
        cursor.execute(query)
        results = cursor.fetchall()
        retVal['%s' % d] = "%s" % results[0]

    return {'dates': retVal}


@app.route("/data/setadetails/")
@json_response
def run_seta_details_query():
    date = request.args.get("date")
    active = request.args.get("active", 0)
    buildbot = request.args.get("buildbot", 0)
    branch = request.args.get("branch", '')

    db = create_db_connnection()
    cursor = db.cursor()
    query = "select jobtype from seta where date='%s 00:00:00'" % date
    cursor.execute(query)
    retVal = {}
    retVal[date] = []
    jobtype = []
    for d in cursor.fetchall():
        parts = d[0].split("'")
        jobtype.append([parts[1], parts[3], parts[5]])

    if active:
        alljobs = jobtype_query()
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
        for job in jobtype:
            active_jobs.append(buildbot_name(job[0], job[1], job[2], branch))
        jobtype = active_jobs

    retVal[date] = jobtype
    return {'jobtypes': retVal}


def buildbot_name(platform, buildtype, jobname, branch):
    platform_map = {}
    platform_map['osx-10-8'] = "Rev5 MacOSx Mountain Lion 10.8"
    platform_map['osx-10-6'] = "Rev4 MacOSX Snow Leopard 10.6"
    platform_map['linux32'] = "Ubuntu VM 12.04"
    platform_map['linux64'] = "Ubuntu VM 12.04 x64"
    platform_map['linux64asan'] = "Ubuntu ASAN VM 12.04 x64"
    platform_map['windowsxp'] = "Windows XP 32-bit"
    platform_map['windows7-32'] = "Windows 7 32-bit"
    platform_map['windows8-64'] = "Windows 8 64-bit"

    buildtype_map = {}
    buildtype_map["opt"] = "opt"
    buildtype_map["debug"] = "debug"
    buildtype_map["asan"] = "opt"

    if buildtype == 'asan':
        platform = 'linux64asan'

    if not branch:
        branch = "%s"

    # TODO: do we need to do a jobname conversion?  I don't see a need yet
    return "%s %s %s test %s" % (platform_map[platform], branch, buildtype_map[buildtype], jobname)

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
    app.run(host="0.0.0.0", port=8157, debug=False)
