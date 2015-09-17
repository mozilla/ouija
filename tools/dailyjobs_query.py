import MySQLdb
import datetime
from argparse import ArgumentParser
import sys

revisions_dict = {}
database = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")
cur = database.cursor()

branches = ["mozilla-inbound", "fx-team", "try"]
platforms = ["linux", "osx", "win", "android"]


def parse_args(argv=None):
    parser = ArgumentParser()
    parser.add_argument("-s", "--start-date",
                        metavar="YYYY-MM-DD",
                        default = datetime.date.today() - datetime.timedelta(days=1),
                        dest="start_date",
                        help="starting date."
                        )

    parser.add_argument("-e", "--end-date",
                        metavar="YYYY-MM-DD",
                        default = datetime.date.today(),
                        dest="end_date",
                        help="ending date."
                        )

    options = parser.parse_args(argv)
    return options


def updatedb(date, platform, branch, numpushes, numjobs, sumduration):
    cur.execute('delete from dailyjobs where date="%s" and branch="%s" and platform="%s"' \
                % (date, branch, platform))
    query = 'insert into dailyjobs (date, platform, branch, numpushes, numjobs, sumduration) \
             values ("{0}", "{1}", "{2}", {3}, {4}, {5})'
    query = query.format(date, platform, branch, numpushes, numjobs, sumduration)
    print query
    cur.execute(query)


def summarize(date, branch):
    for platform in platforms:
        numpushes = 0
        numjobs = 0
        sumduration = 0

        for rev in revisions_dict:
            if platform not in revisions_dict[rev]:
                continue

            value = revisions_dict[rev][platform]
            if value[0] != date:
                continue

            numpushes += 1
            numjobs += value[1]
            if (value[2] >= 0):
              sumduration += value[2]

        updatedb(date, platform, branch, numpushes, numjobs, sumduration)


def retrievedb(branch, date):
    query = "select revision,count(result),sum(duration),platform from testjobs \
             where branch='{0}' and date like '{1}%' and testtype not like '%build%' and testtype!='valgrind' group by revision,platform;"
    query = query.format(branch, date)
    print query
    cur.execute(query)

    for rows in cur.fetchall():
        revision = rows[0]
        jobs = int(rows[1])
        duration = int(rows[2])
        platform = rows[3]
        found = False
        for p in platforms:
            if platform.startswith(p):
                platform = p
                found = True
                break

        # we can skip b2g/mulet or other platforms that don't match our core set
        if not found:
            continue

        if revision not in revisions_dict:
            revisions_dict[revision] = {}
            for p in platforms:
                revisions_dict[revision][p] = [date, 0, 0]

        revisions_dict[revision][platform][1] += jobs
        revisions_dict[revision][platform][2] += duration


if __name__ == "__main__":
    options = parse_args()

    if type(options.start_date) == str:
        options.start_date = datetime.datetime.strptime(options.start_date, "%Y-%m-%d").date()
    if type(options.end_date) == str:
        options.end_date = datetime.datetime.strptime(options.end_date, "%Y-%m-%d").date()

    if options.start_date and not options.end_date:
        options.end_date = options.start_date

    if options.start_date > options.end_date:
        raise Exception("start_date should be less than or equal to the end_date")

    if options.end_date == options.start_date:
        timedelta = 1
    else:
        timedelta = int(str(options.end_date - options.start_date).split(" day")[0])

    start_at = options.start_date - datetime.timedelta(days=1)
    end_at = options.end_date + datetime.timedelta(days=1)

    for branch in branches:
         current_date = start_at
         while current_date <= end_at:
            retrievedb(branch, str(current_date))
            current_date = current_date + datetime.timedelta(days=1)

         current_date = options.start_date
         while current_date <= options.end_date:
            summarize(str(current_date), branch)
            current_date = current_date + datetime.timedelta(days=1)
