import MySQLdb

def run_query(query, rows = None):
    db = MySQLdb.connect(host="localhost",
                         user="root",
                         passwd="testing",
                         db="ouija")

    cur = db.cursor()
    cur.execute(query)

    results = []
    if not rows:
        rows = "keyrev"
    for rows in cur.fetchall():
        if len(rows) > 1:
            temp = []
            for r in rows:
                temp.append(r)
        else:
            temp = rows[0]
        results.append(temp)

    cur.close()
    return results

def annotate_jobs_with_bugidrevision():
    # this query is 99.x% effective
    query = "select distinct bugid from testjobs where bugid like '____________' and bugid not like '%bug%' and bugid not like '%trigger%' and regression!=0 and regression!=NULL"

    results = run_query(query)
    origtotal = 0
    newtotal = 0
    for uniquefailure in results:
        query = "update testjobs set regression=1 where bugid='%s'" % uniquefailure
        print query
        tests = run_query(query)

def makeint(val):
    if isinstance(val, list):
        val = val[0]
    return int(val)


def annotate_jobs_that_only_fail_on_build():
    query = "select distinct bugid from testjobs where bugid like '____________' and bugid not like '%bug%' and bugid not like '%trigger%' and regression!=0 and regression!=NULL"

    results = run_query(query)
    buildonly = 0
    other = 0
    for uniquefailure in results:
        query = "select count(id) from testjobs where bugid='%s' and result='testfailed'" % uniquefailure
        tests = makeint(run_query(query))
        if tests == 0:
            query = "update testjobs set regression=-1 where bugid='%s'" % uniquefailure
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

