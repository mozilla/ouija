import MySQLdb

TEST_FAILURE  = 1
BUILD_FAILURE = -1
NO_FAILURE    = 0

def run_query(query):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="root",
                         db="ouija")

    cur = db.cursor()
    cur.execute(query)

    results = []
    # each row is in ('val',) format, we want 'val'
    for rows in cur.fetchall():
        results.append(rows[0])

    cur.close()
    return results

def annotate_jobs_with_bugidrevision():
    # this query is 99.x% effective
    query = """select distinct bugid from testjobs where bugid like '____________' 
               and bugid not like '%%bug%%' and bugid not like '%%trigger%%' 
               and bugid!='intermittent' and bugid not like '%%tbpl%%' and regression=%s""" % (NO_FAILURE)

    print query
    results = run_query(query)
    print "updating %s regressions" % len(results)
    for uniquefailure in results:
        query = "update testjobs set regression=%s where bugid='%s'" % (TEST_FAILURE, uniquefailure)
        print query
        run_query(query)
    return len(results)

def annotate_jobs_that_only_fail_on_build():
    # NOTE: we annotate all failures as test failures, now we look for regressions that are related to builds
    query = """update testjobs set regression=-1 where regression=%s and (buildtype='leak' or buildtype='build')""" % (TEST_FAILURE)
    print query
    results = run_query(query)

    query = """update testjobs set regression=-1 where regression=%s and testtype like '%%build%%'""" % (TEST_FAILURE)
    print query
    results = run_query(query)

if __name__ == "__main__":
    num_regressions = annotate_jobs_with_bugidrevision()
    if num_regressions > 0:
        annotate_jobs_that_only_fail_on_build()

