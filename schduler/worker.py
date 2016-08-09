import os

import redis
from rq import Worker, Queue, Connection

listen = ['high', 'default', 'low']

# It sets url for redis server to listening
# and it use localhost:6379 as default
redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
