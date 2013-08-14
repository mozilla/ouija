
from wsgiref.simple_server import make_server
from cgi import parse_qs, escape

import json
import MySQLdb

class CSetSummary(object):
    def __init__(self, cset_id):
        self.cset_id = cset_id
        self.green = []
        self.orange = []
        self.red = []
        self.blue = []

class TestSummary(object):
    def __init__(self, testtype):
        self.testtype = testtype
        self.green = 0
        self.orange = 0
        self.red = 0
        self.blue = 0

def run_slaves_query():
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cursor = db.cursor()

    cursor.execute("""select slave,testtype,result from testjobs where result="retry" or result="testfailed" order by slave;""")

    results = {}

    slaves = cursor.fetchall()
    for slave in slaves:
        name = slave[0]
        result = slave[2]

        if results.has_key(name):
            if result == 'testfailed':
                results[name]['fail'] += 1
            else:
                results[name]['retry'] += 1

            results[name]['total'] += 1
        else:
            summary = {}
            summary['retry'] = 0
            summary['fail'] = 0
            summary['total'] = 0
            results[name] = summary

    cursor.close()
    db.close()

    return results

def run_platform_query(platform):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cursor = db.cursor()
    cursor.execute("""SELECT distinct revision FROM `testjobs` WHERE platform = '%s' AND branch = 'mozilla-central' order by date asc limit 30;""" % platform)

    csets = cursor.fetchall()

    cset_summaries = []
    test_summaries = {}

    for cset in csets:
        cset_id = cset[0]

        cursor.execute("""SELECT result,testtype FROM `testjobs` WHERE platform='%s' and buildtype='opt' and revision='%s' order by testtype""" % (platform, cset_id))
        test_results = cursor.fetchall()

        cset_summary = CSetSummary(cset_id)

        for result in test_results:
            res = result[0]
            testtype = result[1]

            if test_summaries.has_key(testtype):
                test_summary = test_summaries[testtype]
            else:
                test_summary = TestSummary(testtype)
                test_summaries[testtype] = test_summary

            if res == 'success':
                cset_summary.green.append(testtype)
                test_summary.green += 1
            elif res == 'testfailed':
                cset_summary.orange.append(testtype)
                test_summary.orange += 1
            elif res == 'retry':
                cset_summary.blue.append(testtype)
                test_summary.blue += 1
            elif res == 'exception' or res == 'busted':
                cset_summary.red.append(testtype)
                test_summary.red += 1
            elif res == 'usercancel':
                print('>>>> usercancel')
            else:
                print('>>>> UNRECOGNIZED RESULT: ', result)

        cset_summaries.append(cset_summary)

    cursor.close()
    db.close()

    return cset_summaries, test_summaries

def generate_slave_response(host, platform):
    html = "<h1>slaves</h1>"

    slaves = run_slaves_query().items()
    slaves = sorted(slaves, key=lambda x: x[1]['total'], reverse=True)
    html += '<table><tr><td>Slave</td><td>fails</td><td>retries</td><td>total</td></tr>'
    for slave in slaves:
        html += '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td></tr>' % (slave[0], slave[1]['fail'], slave[1]['retry'], slave[1]['total'])

    html += '</table>'
    return  html

def generate_platform_response(host, platform):

    cset_summaries, test_summaries = run_platform_query(platform)
    tests = sorted(test_summaries.keys())

    total_green = 0
    total_orange = 0
    total_red = 0
    total_blue = 0
    for summary in cset_summaries:
        total_green += len(summary.green)
        total_orange += len(summary.orange)
        total_red += len(summary.red)
        total_blue += len(summary.blue)

    total = float(total_green + total_orange + total_red + total_blue)
    revhtml = '<img src="http://%s/ouija.gif" width=200/>' % host
    revhtml += '<h1>%s</h1>' % platform
    revhtml += '<table><tr><td></td><td>&nbsp;</td>'
    for test in tests:
        revhtml += '<td class="result">%s</td>' % test

    revhtml += '<td></td><td>Total</td><td>Percentage</td></tr>'

    # Green
    revhtml += '<tr><td>Green</td><td></td>'
    for test in tests:
        summary = test_summaries[test]
        revhtml += "<td>%d</td>" % summary.green
    revhtml += '<td></td><td>%d</td><td>%.2f</td></tr>' % (total_green, 100.0 * total_green / total)

    revhtml += '<tr><td>Orange</td><td></td>'
    for test in tests:
        summary = test_summaries[test]
        revhtml += "<td>%d</td>" % summary.orange
    revhtml += '<td></td><td>%d</td><td>%.2f</td></tr>' % (total_orange, 100.0 * total_orange / total)

    revhtml += '<tr><td>Red</td><td></td>'
    for test in tests:
        summary = test_summaries[test]
        revhtml += "<td>%d</td>" % summary.red
    revhtml += '<td></td><td>%d</td><td>%.2f</td></tr>' % (total_red, total_red / total)

    revhtml += '<tr><td>Blue</td><td></td>'
    for test in tests:
        summary = test_summaries[test]
        revhtml += "<td>%d</td>" % summary.blue
    revhtml += '<td></td><td>%d</td><td>%.2f</td></tr>' % (total_blue, 100.0 * total_blue / total)

    revhtml += '</table>'
    revhtml += '<p><b>Total Failure Rate: %.2f</b>' % (100.0 - 100.0*total_green/total)
    revhtml += '<p><b>Total Failure Rate (excluding retries): %.2f</b>' % (100.0 - 100.0*total_green/(total - total_blue))

    revhtml += '<p>greenResults'
    revhtml += '<table><tr><td class="cset">changeset</td><td>&nbsp;</td>'
    for test in tests:
        revhtml += '<td class="result">%s</td>' % test
    revhtml += "</tr><tr>"

    for summary in cset_summaries:
        revhtml += "<tr><td>%s</td><td></td>" % summary.cset_id
        for test in tests:
            sum = summary.green.count(test)
            revhtml += "<td>%s</td>" % sum
        revhtml += "</tr>"
    revhtml += "</table>"

    return revhtml

def application(environ, start_response):

    host = environ['HTTP_HOST'].split(':')[0]

    if "REQUEST_METHOD" in environ and environ["REQUEST_METHOD"] == "GET":
        pass
    elif "REQUEST_METHOD" in environ and environ["REQUEST_METHOD"] == "POST":
        pass

    html = """
<html>
<head></head>
<body>
%s
</body>
</html>
"""

    platform = environ['PATH_INFO'][1:]

    if platform == 'slaves':
        revhtml = generate_slave_response(host, platform)
    else:
        revhtml = generate_platform_response(host, platform)

    response_body = html % revhtml
    status = "200 OK"
    response_headers = [("Content-Type", "text/html"),
                        ("Content-Length", str(len(response_body)))]
    start_response(status, response_headers)
    return [str(response_body)]

if __name__ == '__main__':
    httpd = make_server("0.0.0.0", 8080, application)
    httpd.serve_forever()

