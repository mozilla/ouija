import argparse
import requests
from redo import retry
from database.config import session
from database.models import Testjobs

# alertmanager server URL
URL = "http://alertmanager.allizom.org/data/dump/?limit=%d&offset=%d"


def migration(args):
    limit = int(args.limit)
    offset = 0
    url = URL % (limit, offset)
    response = retry(requests.get, args=(url, )).json()
    datasets = response['result']
    while len(datasets) > 0:
        for data in datasets:
            Testjob = Testjobs(data['slave'], data['result'], data['build_system_type'],
                               data['duration'], data['platform'], data['buildtype'], data['testtype'],
                               data['bugid'], data['branch'], data['revision'], data['date'],
                               data['failure_classification'], data['failures'])
            try:
                session.add(Testjob)
                session.commit()

            except:
                session.rollback()

            finally:
                session.close()

        # The process will move forward by set offset
        offset += limit
        response = retry(requests.get, args=(url, )).json()
        datasets = response['result']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='migrate the seta database.')
    parser.add_argument('--limit', dest='limit', default=20,
                        help='How much data sets will be migrated for one time.')

    args = parser.parse_args()
    migration(args)
