"""This file contains tests for src/update_runnablejobs.py."""
import json
import os
import unittest
import datetime
import time
import logging
import shutil


from mock import patch, Mock
from tools.update_runnablejobs import (update_runnableapi,
                                       add_new_jobs_into_pressed)


TMP_RUNNABLE_FILENAME = os.path.join(os.getcwd(),
                                     "temp_runnablejobs.json")
ORI_RUNNABLE_PATH = os.path.join(os.getcwd(),
                                 "runnablejobs.json")

TMP_PRESEED_FILENAME = os.path.join(os.getcwd(),
                                    "src/temp_preseed.json")
ORI_PRESEED_PATH = os.path.join(os.getcwd(),
                                "src/preseed.json")

logger = logging.getLogger(__name__)


def mock_response(content, status):
    """Mock of requests.get"""
    response = Mock()
    json_content = json.dumps(content)

    def mock_response_json():
        return json.loads(json_content)

    response.content = content
    response.json = mock_response_json
    response.status_code = status
    response.reason = 'Ready'
    return response


def data_generator():
    """
    This function is been used to generate a bunch of fake runnablejobs, and AFAIK,
    we only need "meta" with "timetamp" and "results" with ref_data_name, platform_option
    job_type_name,

    :return it will return you a list of runnablejob
    """
    results = []
    for platform_option in ["debug", "opt", "asan"]:
        for build_system_type in ["buildbot", "taskcluster"]:
            if build_system_type == "buildbot":
                for build_platform in ["windows8-64", "windowsxp"]:
                    # It's little different from the really ref_data_name and buildername
                    # for buildbot, but I think it's enough for a test case.
                    temp = "{build_platform} {platform_option} test test-for-{build_platform}"
                    ref_data_name = temp.format(build_platform=build_platform,
                                                platform_option=platform_option)
                    results.append({'build_system_type': build_system_type,
                                    'platform_option': platform_option,
                                    'ref_data_name': ref_data_name,
                                    'build_platform': build_platform})
            else:
                for build_platform in ["linux64", "android-4-3-armv7-api15"]:
                    temp = "desktop-test-{build_platform}/" \
                           "{platform_option}-test-for-{build_platform}"
                    ref_data_name = temp.format(build_platform=build_platform,
                                                platform_option=platform_option)
                    results.append({'build_system_type': build_system_type,
                                    'platform_option': platform_option,
                                    'job_type_name': ref_data_name,
                                    'ref_data_name': ref_data_name,
                                    'build_platform': build_platform})

    return {"results": results}


class TestUpdateRunnableapi(unittest.TestCase):
    """This class is used to test the update_runnableapi function"""

    MOCK_DATA = data_generator()
    MOCK_PUSH = {"taskId": 123456, "expires": "2017-07-04T22:13:23"}

    def setUp(self):
        """Setting up values that will be used in every test."""
        self.expected = self.MOCK_DATA

        # we need to create two timetamp to mock the new one and old one
        today = datetime.date.today().strftime('%Y-%m-%d')
        time_tuple = datetime.datetime.strptime(today, "%Y-%m-%d").timetuple()
        old_time = (datetime.date.today() -
                    datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        old_time_tuple = datetime.datetime.strptime(old_time, "%Y-%m-%d").timetuple()
        self.new_timestamp = time.mktime(time_tuple)
        self.old_timestamp = time.mktime(old_time_tuple)

        # rename the runnablejob.json and preseed.json file until the end of test
        try:
            if os.path.isfile(ORI_RUNNABLE_PATH):
                os.rename(ORI_RUNNABLE_PATH, TMP_RUNNABLE_FILENAME)
            shutil.copy2(ORI_PRESEED_PATH, TMP_PRESEED_FILENAME)

        except Exception as e:
            logger.warning(e)

    def tearDown(self):
        """Clean up after every test."""
        try:
            if os.path.isfile(ORI_RUNNABLE_PATH):
                os.remove(ORI_RUNNABLE_PATH)
                os.rename(TMP_RUNNABLE_FILENAME, ORI_RUNNABLE_PATH)

        except Exception as e:
            logger.warning(e)

        try:
            if os.path.isfile(ORI_PRESEED_PATH):
                os.remove(ORI_PRESEED_PATH)
                os.rename(TMP_PRESEED_FILENAME, ORI_PRESEED_PATH)

        except Exception as e:
            logger.warning(e)

    @patch('requests.get', return_value=mock_response(MOCK_PUSH, 200))
    @patch('tools.update_runnablejobs.query_the_runnablejobs',
           return_value=MOCK_DATA)
    def test_call_update_runnablejobs_firstime(self, get, query_the_runnablejobs):
        # let's make sure we don't have any runnablejobs file
        if os.path.isfile(ORI_RUNNABLE_PATH):
            os.remove(ORI_RUNNABLE_PATH)

        update_runnableapi()
        get.assert_called_once()
        assert os.path.isfile(ORI_RUNNABLE_PATH) is True
        with open(ORI_RUNNABLE_PATH, 'r') as f:
            temp = json.loads(f.read())['results']
            assert temp == self.expected['results']

    def test_add_new_jobs_into_pressed(self):
        # let's ceate a runnablejobs.json for the test case
        if os.path.isfile(ORI_RUNNABLE_PATH):
            os.remove(ORI_RUNNABLE_PATH)

        # we need a shallow copy for it.
        data = list(self.MOCK_DATA['results'])

        # we need to know which job need to been pressed into the preseed.json
        # and let's make it random
        missing_data = []
        for job in data:
            if job['platform_option'] == 'debug':
                missing_data.append(job)
        for j in missing_data:
            data.remove(j)

        with open(ORI_RUNNABLE_PATH, 'w') as f:
            json.dump({'results': data}, f)

        with open(ORI_PRESEED_PATH, 'r') as f:
            old_preseedjobs = json.loads(f.read())
        old_length = len(old_preseedjobs)

        add_new_jobs_into_pressed(self.MOCK_DATA)

        assert os.path.isfile(ORI_PRESEED_PATH) is True
        with open(ORI_PRESEED_PATH, 'r') as f:
            new_preseedjobs = json.loads(f.read())
        new_length = len(new_preseedjobs)
        assert len(missing_data) == new_length - old_length
