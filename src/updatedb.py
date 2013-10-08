import argparse
import json, urllib, httplib
import re
import MySQLdb
import datetime
import sys
import time

branch_paths = {
    'mozilla-central': 'mozilla-central',
    'mozilla-inbound': 'integration/mozilla-inbound'
}

branches = ['mozilla-central']

def getCSetResults(branch, revision):
    """
      https://tbpl.mozilla.org/php/getRevisionBuilds.php?branch=mozilla-inbound&rev=3435df09ce34

      no caching as data will change over time.  Some results will be in asap, others will take
      up to 12 hours (usually < 4 hours)
    """
    conn = httplib.HTTPSConnection('tbpl.mozilla.org')
    cset = "/php/getRevisionBuilds.php?branch=%s&rev=%s" % (branch, revision)
    conn.request("GET", cset)
    response = conn.getresponse()

    data = response.read()
    response.close()
    cdata = json.loads(data)
    return cdata

def getPushLog(branch, startdate):
    """
      https://hg.mozilla.org/integration/mozilla-inbound/pushlog?startdate=2013-06-19
    """

    conn = httplib.HTTPSConnection('hg.mozilla.org')
    pushlog = "/%s/pushlog?startdate=%04d-%02d-%02d" % (branch_paths[branch], startdate.year, startdate.month, startdate.day)
    conn.request("GET", pushlog)
    response = conn.getresponse()

    data = response.read()
    response.close()

    pushes = []
    csetid = re.compile('.*Changeset ([0-9a-f]{12}).*')
    dateid = re.compile('.*([0-9]{4}\-[0-9]{2}\-[0-9]{2})T([0-9\:]+)Z.*')
    push = None
    date = None
    for line in data.split('\n'):
        matches = csetid.match(line)
        if matches:
            push = matches.group(1)

        matches = dateid.match(line)
        if matches:
            date = "%s %s" % (matches.group(1), matches.group(2))

        if push and date:
            pushes.append([push, date])
            push = None
            date = None
    return pushes

def parseBuilder(buildername, branch):
    parts = buildername.split(branch)
    platform = parts[0]
    buildtype = branch.join(parts[1:])
    types = buildtype.split('test')
    buildtype, testtype = types[0].strip(), 'test'.join(types[1:]).strip()
    buildtype = buildtype.strip()
    if buildtype not in ['opt', 'debug', 'build'] and not testtype:
        testtype = buildtype
        buildtype = 'opt'

    platforms = ['linux32', 'linux32', 'linux32', 'linux32', 'linux64', 'linux64', 'linux64', 'linux64', 'osx10.6', 'osx10.7', 'osx10.7', 'osx10.8', 'winxp', 'winxp', 'win7', 'win764', 'win8', 'android-armv6', 'android-armv6', 'android-x86', 'android2.2', 'android-no-ion', 'android4.0', 'b2g-vm', 'b2g-emulator']

    platformtext = ['Linux', 'Ubuntu HW 12.04', 'Ubuntu VM 12.04', 'Rev3 Fedora 12', 'Linux x86-64', 'Rev3 Fedora 12x64', 'Ubuntu VM 12.04 x64', 'Ubuntu HW 12.04 x64', 'Rev4 MacOSX Snow Leopard 10.6', 'Rev4 MacOSX Lion 10.7', 'OS X 10.7', 'Rev5 MacOSX Mountain Lion 10.8', 'WINNT 5.2', 'Windows XP 32-bit', 'Windows 7 32-bit', 'Windows 7 64-bit', 'WINNT 6.2', 'Android Armv6', 'Android Armv6 Tegra 250', 'Android X86', 'Android 2.2 Tegra', 'Android no-ionmonkey', 'Android 4.0 Panda', 'b2g_ics_armv7a_gecko_emulator_vm', 'b2g_ics_armv7a_gecko_emulator']

    index = 0
    for p in platformtext:
        if re.match(p, platform.strip()):
            break;
        index += 1
    if index < len(platforms):
        platform = platforms[index]
    else:
        return '', '', ''

    return platform, buildtype, testtype

def clearResults(branch, startdate):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()
    cur.execute('delete from testjobs where branch="%s" and date >= "%04d-%02d-%02d"' % (branch, startdate.year, startdate.month, startdate.day)) 
    cur.close()

def uploadResults(data, branch, revision, date):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()

    for item in data:

        if 'result' in item:
            id = '%s' % int(item['_id'])
            cur.execute('select revision from testjobs where id=%s' % id)
            if cur.fetchone():
                continue

            log = item['log']
            slave = item['slave']
            result = item['result']
            duration = '%s' % (int(item['endtime']) - int(item['starttime']))
            platform, buildtype, testtype = parseBuilder(item['buildername'], branch)
            bugid = ''
            if item['notes']:
                bugid = item['notes'][0]['note'].replace("'", '')
            fields = [id, log, slave, result, duration, platform, buildtype, testtype, bugid, branch, revision]
            if not platform:
                continue

            sql = 'insert into testjobs (id, log, slave, result, duration, platform, buildtype, testtype, bugid, branch, revision, date) values ('
            sql += '%s' % id
            sql += ", '%s'" % log
            sql += ", '%s'" % slave
            sql += ", '%s'" % result
            sql += ', %s' % duration
            sql += ", '%s'" % platform
            sql += ", '%s'" % buildtype
            sql += ", '%s'" % testtype
            sql += ", '%s'" % bugid
            sql += ", '%s'" % branch
            sql += ", '%s'" % revision
            sql += ", '%s'" % date
            sql += ')'
            cur.execute(sql)
    cur.close()

def parseResults(args):
    startdate = datetime.date.today() - datetime.timedelta(days=args.delta)
    revisions = getPushLog(args.branch, startdate)

    clearResults(args.branch, startdate)
    for revision,date in revisions:
        print "%s - %s" % (revision, date)
        data = getCSetResults(args.branch, revision)
        uploadResults(data, args.branch, revision, date)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update ouija database.')
    parser.add_argument('--branch', dest='branch', default='mozilla-central',
                        help='Branch for which to retrieve results.')
    parser.add_argument('--delta', dest='delta', type=int, default=1,
                        help='Number of days in past to use as start date.')
    args = parser.parse_args()
    if args.branch not in branches:
        print('error: unknown branch: ' + args.branch)
        sys.exit(1)
    parseResults(args)
