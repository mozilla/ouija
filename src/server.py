#!/usr/bin/env python

import json
import MySQLdb
from collections import Counter
from urlparse import urlparse, parse_qs
from wsgiref.simple_server import make_server


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


def serialize_to_json(object):
    """Serialize class objects to json"""
    try:
        return object.__dict__
    except AttributeError:
        raise TypeError(repr(object) + 'is not JSON serializable')


def binify(bins, data):

    result = []
    for i, bin in enumerate(bins):
        if i > 0:
            result.append(len(filter(lambda x: x >= bins[i - 1] and x < bin, data))) 
        else:
            result.append(len(filter(lambda x: x < bin, data)))

    result.append(len(filter(lambda x: x >= bins[-1], data)))

    return result


def run_resultstimeseries_query(platform):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cursor = db.cursor()

    cursor.execute("""select result, duration from testjobs
                      where platform="%s" order by duration;""" % platform)

    results = cursor.fetchall()

    greens = []
    oranges = []
    reds = []
    blues = []
    totals = []

    for result in results:
        res = result[0]
        if res == 'success':
            greens.append(int(result[1]))
        elif res == 'testfailed':
            oranges.append(int(result[1]))
        elif res == 'retry':
            blues.append(int(result[1]))
        elif res == 'exception' or res == 'busted':
            reds.append(int(result[1]))
        totals.append(int(result[1]))

    cursor.close()
    db.close()

    bins = map(lambda x: x*60, [10, 20, 30, 40, 50]) #minutes

    data = {}
    data['total'] = len(greens) + len(oranges) + len(reds) + len(blues) 
    data['labels'] = ["< 10","10 - 20","20 - 30","30 - 40","40 - 50","> 50"]
    data['green'] = binify(bins, greens)
    data['orange'] = binify(bins, oranges)
    data['red'] = binify(bins, reds)
    data['blue'] = binify(bins, blues)
    data['totals'] = binify(bins, totals)

    return json.dumps(data)


def run_slaves_query():
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cursor = db.cursor()

    cursor.execute("""select slave, result from testjobs
                      where result="retry" or result="testfailed"
                      order by slave;""")

    data = {}
    summary = {result: 0 for result in ['retry', 'fail', 'total']}

    for name, result in cursor.fetchall():
        data.setdefault(name, summary.copy())
        if result == 'testfailed':
            data[name]['fail'] += 1
        else:
            data[name]['retry'] += 1
        data[name]['total'] += 1

    cursor.close()
    db.close()

    return json.dumps(data)


def run_platform_query(platform):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cursor = db.cursor()
    cursor.execute("""select distinct revision from testjobs
                      where platform = '%s' and branch = 'mozilla-central'
                      order by date desc limit 30;""" % platform)

    csets = cursor.fetchall()

    cset_summaries = []
    test_summaries = {}

    for cset in csets:
        cset_id = cset[0]

        cursor.execute("""select result,testtype from testjobs
                          where platform='%s' and buildtype='opt' and revision='%s'
                          order by testtype""" % (platform, cset_id))

        test_results = cursor.fetchall()

        cset_summary = CSetSummary(cset_id)

        for res, testtype in test_results:

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
        percentage[key] = '%.2f' % (100.0 * total[key] / test_count)

    fail_rate = '%.2f' % (100.0 - 100.0 * total['green'] / test_count)
    fail_rate_exclude_retries = '%.2f' % (100.0 - 100.0 * total['green'] / (test_count - total['blue']))

    test_summaries['total'] = total
    test_summaries['percentage'] = percentage

    result = {'testTypes': test_types,
              'byRevision': cset_summaries,
              'byTest': test_summaries,
              'failureRate': fail_rate,
              'failureRateNoRetries': fail_rate_exclude_retries}

    return json.dumps(result, default=serialize_to_json)


def application(environ, start_response):

    if "REQUEST_METHOD" in environ and environ["REQUEST_METHOD"] == "GET":
        pass
    elif "REQUEST_METHOD" in environ and environ["REQUEST_METHOD"] == "POST":
        pass

    request = urlparse(environ.get('REQUEST_URI', environ['PATH_INFO']))
    query_dict = parse_qs(request.query)

    if request.path == '/data/results':
        platform = query_dict.get('platform', ['android4.0'])[0]
        print('>>>> platform: ', platform)
        response_body = run_resultstimeseries_query(platform)

    elif request.path == '/data/slaves':
        response_body = run_slaves_query()

    elif request.path == '/data/platform':
        platform = query_dict['platform'][0]
        print('>>> platform', platform)
        response_body = run_platform_query(platform)

    else:
        raise Exception('Unhandled request')

    status = "200 OK"
    response_headers = [("Content-Type", "application/json"),
                        ("Content-Length", str(len(response_body)))]
    start_response(status, response_headers)
    return response_body


if __name__ == '__main__':
    httpd = make_server("0.0.0.0", 8314, application)
    httpd.serve_forever()
