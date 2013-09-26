#!/usr/bin/env python

import json
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


class TestSummary(object):
    def __init__(self):
        self.green = 0
        self.orange = 0
        self.red = 0
        self.blue = 0


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


def get_date_range(dates):
    start_date = min(dates)
    end_date = max(dates)

    return {'startDate': start_date.strftime('%Y-%m-%d %H:%M'),
            'endDate': end_date.strftime('%Y-%m-%d %H:%M')}

def binify(bins, data):

    result = []
    for i, bin in enumerate(bins):
        if i > 0:
            result.append(len(filter(lambda x: x >= bins[i - 1] and x < bin, data))) 
        else:
            result.append(len(filter(lambda x: x < bin, data)))

    result.append(len(filter(lambda x: x >= bins[-1], data)))

    return result


def run_resultstimeseries_query(query_dict):
    platform = query_dict.get('platform', 'android4.0')
    print('>>>> platform: ', platform)

    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select result, duration, date from testjobs
                      where platform="%s" order by duration;""" % platform)

    greens = []
    oranges = []
    reds = []
    blues = []
    totals = []

    dates = []

    for result, duration, date in cursor.fetchall():
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

    return json.dumps([data, get_date_range(dates)])


def run_slaves_query(query_dict):
    db = create_db_connnection()
    cursor = db.cursor()
    cursor.execute("""select slave, result, date from testjobs
                      where result in ("retry", "testfailed", "success")
                      order by slave;""")

    data = {}
    keys = 'retry fail success total'
    summary = {result: 0 for result in keys.split()}

    dates = []

    for name, result, date in cursor.fetchall():
        data.setdefault(name, summary.copy())
        if result == 'testfailed':
            data[name]['fail'] += 1
        elif result == 'retry':
            data[name]['retry'] += 1
        else:
            data[name]['success'] += 1
        data[name]['total'] += 1
        dates.append(date)

    cursor.close()
    db.close()

    return json.dumps([data, get_date_range(dates)])


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

    for cset in csets:
        cset_id = cset[0]

        cursor.execute("""select result,testtype, date from testjobs
                          where platform='%s' and buildtype='opt' and revision='%s'
                          order by testtype""" % (platform, cset_id))

        test_results = cursor.fetchall()

        cset_summary = CSetSummary(cset_id)

        for res, testtype, date in test_results:

            test_summary = test_summaries.setdefault(testtype, TestSummary())

            if res == 'success':
                cset_summary.green[testtype] += 1
                test_summary.green += 1
            elif res == 'testfailed':
                cset_summary.orange[testtype] += 1
                test_summary.orange += 1
            elif res == 'retry':
                cset_summary.blue[testtype] += 1
                test_summary.blue += 1
            elif res == 'exception' or res == 'busted':
                cset_summary.red[testtype] += 1
                test_summary.red += 1
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
        values = test_summaries[test].__dict__
        total.update(values)

    test_count = sum(total.values())

    for key in total:
        percentage[key] = round((100.0 * total[key] / test_count), 2)

    fail_rate = 100.0 - (100.0 * total['green']) / test_count
    fail_rate_exclude_retries = 100.0 - (100.0 * total['green']) / (test_count - total['blue'])

    test_summaries['total'] = total
    test_summaries['percentage'] = percentage

    result = {'testTypes': test_types,
              'byRevision': cset_summaries,
              'byTest': test_summaries,
              'failureRate': round(fail_rate, 2),
              'failureRateNoRetries': round(fail_rate_exclude_retries, 2),
              'dates': get_date_range(dates)}

    return json.dumps(result, default=serialize_to_json)


def application(environ, start_response):

    request = urlparse(request_uri(environ))
    query_dict = parse_qs(request.query)

    for key, value in query_dict.items():
        if len(value) == 1:
            query_dict[key] = value[0]

    if request.path == '/data/results':
        request_handler = run_resultstimeseries_query

    elif request.path == '/data/slaves':
        request_handler = run_slaves_query

    elif request.path == '/data/platform':
        request_handler = run_platform_query

    response_body = request_handler(query_dict)
    status = "200 OK"
    response_headers = [("Content-Type", "application/json"),
                        ("Content-Length", str(len(response_body)))]
    start_response(status, response_headers)
    return response_body


if __name__ == '__main__':
    httpd = make_server("0.0.0.0", 8314, application)
    httpd.serve_forever()
