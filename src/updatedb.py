import argparse
import json, urllib, httplib
import re
import MySQLdb
import datetime
import sys
import time

branch_paths = {
    'mozilla-central': 'mozilla-central',
    'mozilla-inbound': 'integration/mozilla-inbound',
    'b2g-inbound': 'integration/b2g-inbound',
    'fx-team': 'integration/fx-team'
}

branches = ['mozilla-central', 'mozilla-inbound', 'b2g-inbound', 'fx-team']

platformXRef = {
    'Linux'                            : 'linux32',
    'Ubuntu HW 12.04'                  : 'linux32',
    'Ubuntu VM 12.04'                  : 'linux32',
    'Rev3 Fedora 12'                   : 'linux32',
    'Linux x86-64'                     : 'linux64',
    'Rev3 Fedora 12x64'                : 'linux64',
    'Ubuntu VM 12.04 x64'              : 'linux64',
    'Ubuntu HW 12.04 x64'              : 'linux64',
    'Ubuntu ASAN VM 12.04 x64'         : 'linux64',
    'Rev4 MacOSX Snow Leopard 10.6'    : 'osx10.6',
    'Rev4 MacOSX Lion 10.7'            : 'osx10.7',
    'OS X 10.7'                        : 'osx10.7',
    'Rev5 MacOSX Mountain Lion 10.8'   : 'osx10.8',
    'WINNT 5.2'                        : 'winxp',
    'Windows XP 32-bit'                : 'winxp',
    'Windows 7 32-bit'                 : 'win7',
    'Windows 7 64-bit'                 : 'win764',
    'WINNT 6.1 x86-64'                 : 'win764',
    'WINNT 6.2'                        : 'win8',
    'Android Armv6'                    : 'android-armv6',
    'Android 2.2 Armv6'                : 'android-armv6',
    'Android Armv6 Tegra 250'          : 'android-armv6',
    'Android X86'                      : 'android-x86',
    'Android 2.2'                      : 'android2.2',
    'Android 2.2 Tegra'                : 'android2.2',
    'Android 2.3 Emulator'             : 'android2.3',
    'Android no-ionmonkey'             : 'android-no-ion',
    'Android 4.0 Panda'                : 'android4.0',
    'b2g_emulator_vm'                  : 'b2g-vm',
    'b2g_ubuntu64_vm'                  : 'b2g-vm',
    'b2g_ubuntu32_vm'                  : 'b2g-vm',
    'b2g_ics_armv7a_gecko_emulator_vm' : 'b2g-vm',
    'b2g_ics_armv7a_gecko_emulator'    : 'b2g-emulator'
}

#
# The following platforms were not added
# We might want to add them in the future
#
'''
b2g_mozilla-central_macosx64_gecko build opt
b2g_mozilla-central_macosx64_gecko-debug build opt
b2g_macosx64 opt gaia-ui-test

linux64-br-haz_mozilla-central_dep opt

Android 4.2 x86 build
Android 4.2 x86 Emulator opt androidx86-set-4

b2g_mozilla-central_win32_gecko-debug build opt
b2g_mozilla-central_win32_gecko build opt
b2g_mozilla-central_linux32_gecko build opt
b2g_mozilla-central_linux32_gecko-debug build opt

b2g_mozilla-central_emulator-kk_periodic opt
b2g_mozilla-central_emulator-kk-debug_periodic opt
b2g_mozilla-central_emulator-kk_nonunified opt
b2g_mozilla-central_emulator-kk-debug_nonunified opt

b2g_mozilla-central_emulator-jb-debug_dep opt
b2g_mozilla-central_emulator_dep opt
b2g_mozilla-central_emulator-debug_dep opt
b2g_mozilla-central_emulator-jb_dep opt
b2g_mozilla-central_emulator_nonunified opt
b2g_mozilla-central_emulator-debug_nonunified opt
b2g_mozilla-central_emulator-jb-debug_nonunified opt
b2g_mozilla-central_emulator-jb_nonunified opt

b2g_mozilla-central_nexus-4_periodic opt
b2g_mozilla-central_nexus-4_eng_periodic opt

b2g_mozilla-central_linux64_gecko build opt
b2g_mozilla-central_linux64_gecko-debug build opt

b2g_mozilla-central_hamachi_eng_dep opt
b2g_mozilla-central_hamachi_periodic opt

b2g_mozilla-central_flame_eng_dep opt
b2g_mozilla-central_flame_periodic opt

b2g_mozilla-central_helix_periodic opt

b2g_mozilla-central_wasabi_periodic opt
'''

def getCSetResults(branch, revision):
    """
      https://tbpl.mozilla.org/php/getRevisionBuilds.php?branch=mozilla-inbound&rev=3435df09ce34

      no caching as data will change over time.  Some results will be in asap, others will take
      up to 12 hours (usually < 4 hours)
    """
    conn = httplib.HTTPSConnection('tbpl.mozilla.org')
    cset = "/php/getRevisionBuilds.php?branch=%s&rev=%s&showall=1" % (branch, revision)
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
            ymd = map(int, matches.groups(2)[0].split('-'))
            hms = map(int, matches.groups(2)[1].split(':'))
            date = datetime.datetime(ymd[0], ymd[1], ymd[2], hms[0], hms[1], hms[2])

        if push and date and date >= startdate:
            pushes.append([push, date])
            push = None
            date = None
    return pushes

def parseBuilder(buildername, branch):
    # Split on " " + branch + " " because the new platforms have the string mozilla-central
    # in the platform name. Thus, splitting on just the branch would most likely cause
    # the logic after the splitting work not so well.
    parts = buildername.split(" " + branch + " ")
    platform = parts[0]
    buildtype = branch.join(parts[1:])

    types = buildtype.split('test')
    buildtype, testtype = types[0].strip(), 'test'.join(types[1:]).strip()
    buildtype = buildtype.strip()

    if buildtype not in ['opt', 'debug', 'build'] and not testtype:
        testtype = buildtype
        buildtype = 'opt'

    for p in platformXRef:
        if re.match(p, platform.strip()):
            return platformXRef[p], buildtype, testtype
    return '','',''

def clearResults(branch, startdate):

    date_183_days_ago = datetime.date.today() - datetime.timedelta(days=183)
    delete_delta_and_old_data = 'delete from testjobs where branch="%s" and (date >= "%04d-%02d-%02d %02d:%02d:%02d" or date < "%04d-%02d-%02d")' % (branch, startdate.year, startdate.month, startdate.day, startdate.hour, startdate.minute, startdate.second, date_183_days_ago.year, date_183_days_ago.month, date_183_days_ago.day)

    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()
    cur.execute(delete_delta_and_old_data)
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
    startdate = datetime.datetime.utcnow() - datetime.timedelta(hours=args.delta)

    if args.branch == 'all':
        result_branches = branches
    else:
        result_branches = [args.branch]

    for branch in result_branches:
        revisions = getPushLog(branch, startdate)

        clearResults(branch, startdate)
        for revision,date in revisions:
            print "%s - %s" % (revision, date)
            data = getCSetResults(branch, revision)
            uploadResults(data, branch, revision, date)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update ouija database.')
    parser.add_argument('--branch', dest='branch', default='all',
                        help='Branch for which to retrieve results.')
    parser.add_argument('--delta', dest='delta', type=int, default=12,
                        help='Number of hours in past to use as start time.')
    args = parser.parse_args()
    if args.branch != 'all' and args.branch not in branches:
        print('error: unknown branch: ' + args.branch)
        sys.exit(1)
    parseResults(args)
