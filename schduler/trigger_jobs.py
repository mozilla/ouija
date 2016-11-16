import os


def trigger_updatedb():
    os.system("python src/updatedb.py --delta 24 --threads 4")


def trigger_migratedb():
    os.system("python tools/database_migration.py")


def trigger_failures():
    os.system("python tools/failures.py")


def trigger_update_job_priority_table():
    os.system("python tools/update_runnablejobs.py")