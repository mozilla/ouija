#!/usr/bin/env python

import json
import re
from datetime import datetime, timedelta
from itertools import groupby
from collections import Counter
from urlparse import urlparse, parse_qs
from wsgiref.simple_server import make_server
from wsgiref.util import request_uri

import MySQLdb


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
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return json.dumps(result or {'error': 'No data found for your request'},
                          default=serialize_to_json)
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


@json_response
def run_resultstimeseries_query(query_dict):
    platform = query_dict.get('platform', 'android4.0')
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

    bins = map(lambda x: x*60, [10, 20, 30, 40, 50])  # minutes

    data = {}
    data['total'] = len(totals)
    data['labels'] = ["< 10","10 - 20","20 - 30","30 - 40","40 - 50","> 50"]
    data['green'] = binify(bins, greens)
    data['orange'] = binify(bins, oranges)
    data['red'] = binify(bins, reds)
    data['blue'] = binify(bins, blues)
    data['totals'] = binify(bins, totals)

    return {'data': data, 'dates': get_date_range(dates)}


@json_response
def run_slaves_query(query_dict):
    start_date, end_date = clean_date_params(query_dict)

    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select slave, result, date from testjobs
                      where result in
                      ("retry", "testfailed", "success", "busted", "exception")
                      and date between "%s" and "%s"
                      order by slave;""" % (start_date, end_date))

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

    # calculate failure rate for slaves
    for slave, results in data.iteritems():
        fail_rates = calculate_fail_rate(results['success'],
                                         results['retry'],
                                         results['total'])
        data[slave]['sfr'] = fail_rates

    platforms = {}

    # group slaves by platform and calculate platform failure rate
    slaves = sorted(data.keys())
    for platform, slave_group in groupby(slaves, lambda x: x.rsplit('-', 1)[0]):
        platforms[platform] = {}
        results = {}
        slaves = list(slave_group)

        for label in ['success', 'retry', 'total']:
            r = reduce(lambda x, y: x + y,
                       [data[slave][label] for slave in slaves])
            results[label] = r

        fail_rates = calculate_fail_rate(results['success'],
                                         results['retry'],
                                         results['total'])
        platforms[platform].update(fail_rates)

    return {'slaves': data,
            'platforms': platforms,
            'dates': get_date_range(dates)}


@json_response
def run_platform_query(query_dict):
    platform = query_dict['platform']
    print('>>> platform', platform)

    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select distinct revision from testjobs
                      where platform = '%s' and branch = 'mozilla-central'
                      order by date desc limit 30;""" % platform)

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


def handler404(start_response):
    status = "404 NOT FOUND"
    response_body = "Not found"
    response_headers = [("Content-Type", "text/html"),
                        ("Content-Length", str(len(response_body)))]
    start_response(status, response_headers)
    return response_body


def application(environ, start_response):
    # get request path and request params
    request = urlparse(request_uri(environ))
    query_dict = parse_qs(request.query)

    for key, value in query_dict.items():
        if len(value) == 1:
            query_dict[key] = value[0]

    # map request handler to request path
    urlpatterns = (
        ('/data/results(/)?$', run_resultstimeseries_query),
        ('/data/slaves(/)?$', run_slaves_query),
        ('/data/platform(/)?$', run_platform_query),
        )

    # dispatch request to request handler
    for pattern, request_handler in urlpatterns:
        if re.match(pattern, request.path, re.I):
            response_body = request_handler(query_dict)
            break
    else:
        # error handling
        return handler404(start_response)

    status = "200 OK"
    response_headers = [("Content-Type", "application/json"),
                        ("Content-Length", str(len(response_body)))]
    start_response(status, response_headers)
    return response_body


if __name__ == '__main__':
    httpd = make_server("0.0.0.0", 8314, application)
    httpd.serve_forever()
