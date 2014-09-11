import sys
import logging
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
sys.path.insert(0, '/home/ubuntu/ouija/src')

from server import app as application
