import os
import json
import logging
LOG = logging.getLogger(__name__)


def _getgroup(name):
    """
    It's about to get group for the test job, like crashtest for crashtest-1.
    """
    try:
        group = name.split('-')[0]
    except:
        group = ''
    return group


def _getgroupCode(tbplnames, name):
    """
    It's about get group code by given testname, like T-e10s for tp5o-e10s.
    And there has some useless blank in testname like " mochitest-devtools-chrome-3"
    to strip that blank off, so we can get the code appropriately.
    """
    try:
        code = tbplnames[name.strip()]['group']
    except:
        code = ''
    return code


def _getcode(tbplnames, name):
    """
    It's about get the code by given testname, it usually related with the group code
    like '2' for web-platform-tests-2.   And there has some useless blank in testname
    like " mochitest-devtools-chrome-3" to strip that blank off,
    so we can get the code appropriately.
    """
    try:
        code = tbplnames[name.strip()]['code']
    except:
        code = ''
    return code


class Treecodes:
    """This class contain all the mapping we need in SETA and make it works"""

    def __init__(self, repo_name='mozilla-inbound'):
        # default to query all jobs on mozilla-inbound branch
        self.tbplnames = {}
        self.jobtypes = []
        self.jobnames = []
#TODO: figure out how to make this work for apache
#        with open(os.getcwd() + '/runnablejobs.json') as data:
        with open('/home/ubuntu/ouija/runnablejobs.json') as data:
            joblist = json.loads(data.read())['results']

        # skipping pgo - We run this infrequent enough that we should have all pgo results tested
        self.joblist = [job for job in joblist if job['platform_option'] != 'pgo']
        if len(self.joblist) > 0:
            for job in self.joblist:
                testtype = ''

                # the testtype of builbot job can been found in 'ref_data_name'
                # like web-platform-tests-4 in "Ubuntu VM 12.04 x64 mozilla-inbound
                #  opt test web-platform-tests-4"
                if job['build_system_type'] == 'buildbot':
                    testtype = job['ref_data_name'].split(' ')[-1]

                # taskcluster's testtype is a part of its 'job_type_name' like reftest-2
                # for [TC] Linux64 reftest-2
                else:
                    testtype = job['job_type_name'].split(' ')[-1]

                # we don't need non-test job for seta, but we still need to verify this type list
                if testtype in ['dep', 'nightly', 'non-unified', 'valgrind', 'build']:
                    continue

                elif 'mulet' in job['platform']:
                    continue

                else:
                    try:
                        platform = job['platform']
                        buildtype = job['platform_option']
                        self.jobtypes.append([platform, buildtype, testtype])

                        # It's about get jobnames and both buildbot and taskcluster job has '?'
                        # when the job_group_symbol is unknown.
                        self.jobnames.append(self._get_jobnames(job, testtype,
                                                                job['ref_data_name']))
                        job_group_symbol = job['job_group_symbol'] \
                            if job['job_group_symbol'] != '?' else ''
                        job_type_symbol = job['job_type_symbol'] if job['job_type_symbol'] else ''
                        self.tbplnames.update({testtype: {'group': job_group_symbol,
                                                          'code': job_type_symbol}})
                    except Exception as e:
                        LOG.error(e)

    def jobtype_query(self):
        """Query all available jobtypes and return it as list"""
        return self.jobtypes

    def jobnames_query(self):
        """Query all jobnames including buildtype and groupcode, then return them as list"""
        return self.jobnames

    def _get_jobnames(self, job, testtype, buildername):
        signature = ''  # TH specific
        buildtype = job['platform_option']
        platform = job['platform']
        name = testtype
        jobname = ''  # TH specific
        buildername = buildername
        group = _getgroup(name)
        groupcode = _getgroupCode(self.tbplnames, name)
        code = _getcode(self.tbplnames, name)
        data = {'jobname': jobname, 'signature': signature,
                'job_type_name': group, 'job_group_symbol': groupcode,
                'name': name, 'job_type_symbol': code,
                'ref_data_name': buildername,
                'platform': platform, 'buildtype': buildtype}
        return data
