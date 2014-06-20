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


def clean_date_params(query_dict):
    """Parse request date params"""
    now = datetime.now()

    # get dates params
    start_date_param = query_dict.get('startDate')
    end_date_param = query_dict.get('endDate')

    # parse dates
    end_date = (parse_date(end_date_param) or now) + timedelta(days=1)
    start_date = parse_date(start_date_param) or end_date - timedelta(days=8)

    # validate dates
    if start_date > now or start_date.date() >= end_date.date():
        start_date = now - timedelta(days=7)
        end_date = now + timedelta(days=1)

    return start_date, end_date


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


@app.route("/data/results/")
@json_response
def run_resultstimeseries_query():
    platform = request.args.get("platform", "android4.0")
    print('>>>> platform: ', platform)

    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select result, duration, date from testjobs
                      where platform="%s" order by duration;""" % platform)

    query_results = cursor.fetchall()

    greens = []
    oranges = []
    reds = []
    blues = []
    totals = []

    dates = []

    for result, duration, date in query_results:
        if result == 'success':
            greens.append(int(duration))
        elif result == 'testfailed':
            oranges.append(int(duration))
        elif result == 'retry':
            blues.append(int(duration))
        elif result == 'exception' or result == 'busted':
            reds.append(int(duration))
        totals.append(int(duration))
        dates.append(date)

    cursor.close()
    db.close()

    bins = map(lambda x: x * 60, [10, 20, 30, 40, 50])  # minutes

    data = {}
    data['total'] = len(totals)
    data['labels'] = ["< 10", "10 - 20", "20 - 30", "30 - 40", "40 - 50", "> 50"]
    data['green'] = binify(bins, greens)
    data['orange'] = binify(bins, oranges)
    data['red'] = binify(bins, reds)
    data['blue'] = binify(bins, blues)
    data['totals'] = binify(bins, totals)

    return {'data': data, 'dates': get_date_range(dates)}


@app.route("/data/results/flot/day/")
@json_response
def run_results_day_flot_query():
    """ This function returns the total failures/total jobs data per day for all platforms. It is sending the data in the format required by flot.Flot is a jQuery package used for 'attractive' plotting """

    start_date, end_date = clean_date_params(request.args)

    platforms = ['android4.0', 'android2.2', 'linux32', 'winxp', 'win7', 'win8', 'osx10.6', 'osx10.7', 'osx10.8']
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
                      order by slave;""".format(start_date, end_date))

    query_results = cursor.fetchall()
    cursor.close()
    db.close()

    if not query_results:
        return

    data = {}
    labels = 'fail retry infra success total'.split()
    summary = {result: 0 for result in labels}

    dates = []

    for name, result, date in query_results:
        data.setdefault(name, summary.copy())
        if result == 'testfailed':
            data[name]['fail'] += 1
        elif result == 'retry':
            data[name]['retry'] += 1
        elif result == 'success':
            data[name]['success'] += 1
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

    print('>>> platform', platform, "startDate:", start_date, "endDate:", end_date)

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
                print('>>>> usercancel')
            else:
                print('>>>> UNRECOGNIZED RESULT: ', result)
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


if __name__ == "__main__": app.run(host="0.0.0.0", port=8314, debug=True)
