import argparse
import requests
import logging
from redo import retry
from database.config import session
from database.models import Testjobs

# alertmanager server URL
URL = "http://alertmanager.allizom.org/data/dump/?limit=%d&offset=%d"
logger = logging.getLogger(__name__)


def migration(args):
    limit = int(args.limit)
    offset = 0
    url = URL % (limit, offset)
    response = retry(requests.get, args=(url, )).json()
    datasets = response['result']

    session.query(Testjobs).filter(Testjobs.date>'2016-01-01 00:00:00').delete()

    while len(datasets) > 0:
        for data in datasets:
            testtype = data['testtype']

            # spidermonkey builds
            if len(testtype.split('pider')) > 1:
                continue

            # docker generation jobs
            if len(testtype.split('ocker')) > 1:
                continue

            # hazzard builds
            if len(testtype.split('az')) > 1:
                continue

            # decision tasks
            if len(testtype.split('ecision')) > 1:
                continue

            # TODO: figure out a better naming strategy here
            # builds, linting, etc.
            if testtype.startswith('[TC]'):
                continue

            # skip talos jobs
            if testtype in ['chromez', 'tp5o', 'g1', 'g2', 'g3', 'g4', 'xperf',
                            'chromez-e10s', 'tp5o-e10s', 'g1-e10s', 'g2-e10s', 'g3-e10s',
                            'g4-e10s', 'xperf-e10s', 'dromaeojs', 'dromaeojs-e10s',
                            'svgr', 'svgr-e10s', 'remote-tsvgx', 'remote-tp4m_chrome',
                            'other', 'other-e10s']:
                continue

            # linter jobs
            if testtype in ['Static Analysis Opt', 'ESLint', 'Android lint', 'lint']:
                continue

            # builds
            if testtype in ['nightly', 'Android armv7 API 15+', 'ASan Dbg', 'valgrind',
                            'Android armv7 API 15+ Dbg', 'ASan Debug', 'pgo-build',
                            'ASan Opt', 'build']:
                continue

            # hidden/lower tier tests, not sure of CI system, old jobs
            if testtype in ['media-youtube-tests', 'external-media-tests', 'luciddream', 'media-tests']:
                continue

            Testjob = Testjobs(data['slave'], data['result'], data['build_system_type'],
                               data['duration'], data['platform'], data['buildtype'], testtype,
                               data['bugid'], data['branch'], data['revision'], data['date'],
                               data['failure_classification'], data['failures'])
            try:
                session.add(Testjob)
                session.commit()

            except Exception as error:
                logging.warning(error)
                session.rollback()

        session.close()

        # The process will move forward by set offset
        offset += limit
        url = URL % (limit, offset)
        response = retry(requests.get, args=(url, )).json()
        datasets = response['result']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='migrate the seta database.')
    parser.add_argument('--limit', dest='limit', default=20,
                        help='How much data sets will be migrated for one time.')

    args = parser.parse_args()
    migration(args)
