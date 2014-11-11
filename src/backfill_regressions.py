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
               and regression!=%s and regression!=NULL  
            """ % (NO_FAILURE)

    results = run_query(query)
    for uniquefailure in results:
        query = "update testjobs set regression=%s where bugid='%s'" % (TEST_FAILURE, uniquefailure)
        print query
        run_query(query)

def makeint(val):
    if isinstance(val, list):
        val = val[0]
    return int(val)


def annotate_jobs_that_only_fail_on_build():
    query = """select distinct bugid from testjobs where bugid like '____________' 
               and bugid not like '%%bug%%' and bugid not like '%%trigger%%' 
               and regression!=%s and regression!=NULL
            """ % (NO_FAILURE)

    results = run_query(query)
    buildonly = 0
    other = 0
    for uniquefailure in results:
        query = "select count(id) from testjobs where bugid='%s' and result='testfailed'" % uniquefailure
        tests = makeint(run_query(query))
        if tests == 0:
            query = "update testjobs set regression=%s where bugid='%s'" % (BUILD_FAILURE, uniquefailure)
            print query
            run_query(query)
            print "%s is build only" % uniquefailure
            buildonly += 1
        else: 
            other += 1

    print "%s build only issues, %s others to annotate" % (buildonly, other)

if __name__ == "__main__":
    annotate_jobs_with_bugidrevision()
    annotate_jobs_that_only_fail_on_build()

