from rq import Queue
from worker import conn
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from trigger_jobs import (
    trigger_failures,
    trigger_migratedb,
    trigger_update_job_priority_table,
)


logger = logging.info(__name__)
sched = BlockingScheduler()
q = Queue(connection=conn)


# It will triggers updatedb.py on 1:00 and 13:00 everyday(from Monday to Sunday)
# and trigger failures.py in every 2:00.
@sched.scheduled_job('cron', day_of_week='mon-sun', hour=1)
def timed_trigger_updatedb():
    q.enqueue(trigger_migratedb)

@sched.scheduled_job('cron', day_of_week='mon-sun', hour=13)
def timed_trigger_updatedb_sec():
    q.enqueue(trigger_migratedb)


@sched.scheduled_job('cron', day_of_week='mon-sun', hour=12)
def timed_trigger_updatedb():
    q.enqueue(trigger_update_job_priority_table)


@sched.scheduled_job('cron', day_of_week='mon-sun', hour=14)
def timed_trigger_failures():
    q.enqueue(trigger_failures)

sched.start()
