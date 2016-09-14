import os
from rq import Queue
from worker import conn
import logging
from apscheduler.schedulers.blocking import BlockingScheduler


logger = logging.info(__name__)
sched = BlockingScheduler()
q = Queue(connection=conn)


def trigger_updatedb():
    os.system("python src/updatedb.py --delta 24 --threads 4")

def trigger_migratedb():
    os.system("python tools/database_migration.py")

def trigger_failures():
    os.system("python tools/failures.py")


# It will triggers updatedb.py on 1:00 and 13:00 everyday(from Monday to Sunday)
# and trigger failures.py in every 2:00.
@sched.scheduled_job('cron', day_of_week='mon-sun', hour=1)
def timed_trigger_updatedb():
    q.enqueue(trigger_migratedb())

@sched.scheduled_job('cron', day_of_week='mon-sun', hour=13)
def timed_trigger_updatedb_sec():
    q.enqueue(trigger_migratedb())


@sched.scheduled_job('cron', day_of_week='mon-sun', hour=2)
def timed_trigger_failures():
    q.enqueue(trigger_failures())

sched.start()
