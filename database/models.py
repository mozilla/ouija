"""This file define all the model we will need in seta"""
import logging
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.schema import MetaData
from sqlalchemy.ext.declarative import declarative_base
from config import engine


logger = logging.getLogger(__name__)
Metadata = MetaData(bind=engine)
MetaBase = declarative_base(metadata=Metadata)


class Dailyjobs(MetaBase):
    __tablename__ = 'dailyjobs'

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False, index=True)
    platform = Column(String(32), nullable=False)
    branch = Column(String(64), nullable=False)
    numpushes = Column(Integer, nullable=False)
    numjobs = Column(Integer, nullable=False)
    sumduration = Column(Integer, nullable=False)

    def __init__(self, date, platform, branch, numpushes,
                 numjobs, sumduration):
        self.date = date
        self.platform = platform
        self.branch = branch
        self.numpushes = numpushes
        self.numjobs = numjobs
        self.sumduration = sumduration


class Testjobs(MetaBase):
    __tablename__ = 'testjobs'

    id = Column(Integer, primary_key=True)
    slave = Column(String(64), nullable=False)
    result = Column(String(64), nullable=False)
    build_system_type = Column(String(64), nullable=False)
    duration = Column(Integer, nullable=False)
    platform = Column(String(32), nullable=False)
    buildtype = Column(String(32), nullable=False)
    testtype = Column(String(64), nullable=False)
    bugid = Column(Text, nullable=False)
    branch = Column(String(64), nullable=False)
    revision = Column(String(32), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    failure_classification = Column(Integer, nullable=False)
    failures = Column(String(1024), nullable=False)

    def __init__(self, slave, result, build_system_type,
                 duration, platform, buildtype,
                 testtype, bugid, branch, revision, date,
                 failure_classification, failures):
        self.slave = slave
        self.result = result
        self.build_system_type = build_system_type
        self.duration = duration
        self.platform = platform
        self.buildtype = buildtype
        self.testtype = testtype
        self.bugid = bugid
        self.branch = branch
        self.revision = revision
        self.date = date
        self.failure_classification = failure_classification
        self.failures = failures


# TODO: deprecate this!
class TaskRequests(MetaBase):
    __tablename__ = 'taskrequests'

    id = Column(Integer, primary_key=True)
    branch = Column(String(128), nullable=False, index=True)
    counter = Column(Integer, nullable=False)
    datetime = Column(DateTime, nullable=False)
    reset_delta = Column(Integer, nullable=False)

    def __init__(self, branch, counter, datetime, reset_delta):
        self.branch = branch
        self.counter = counter
        self.datetime = datetime
        self.reset_delta = reset_delta


class JobPriorities(MetaBase):
    __tablename__ = 'jobpriorities'

    id = Column(Integer, primary_key=True)
    testtype = Column(String(128), nullable=False, index=True)
    buildtype = Column(String(64), nullable=False, index=True)
    platform = Column(String(64), nullable=False, index=True)
    priority = Column(Integer)
    timeout = Column(Integer)
    expires = Column(DateTime)
    buildsystem = Column(String(64), nullable=False, index=True)

    def __init__(self, testtype, buildtype, platform, priority, timeout, expires, buildsystem):
        self.testtype = testtype
        self.buildtype = buildtype
        self.platform = platform
        self.priority = priority
        self.timeout = timeout
        self.expires = expires
        self.buildsystem = buildsystem


if __name__ == "__main__":
    # create all table and column, so we must call this before
    # all things begin.
    Metadata.create_all(bind=engine, checkfirst=True)
