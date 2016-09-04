"""This file defined all the objects will been used in seta"""
# These are branches seta supports
SETA_BRANCHES = ['fx-team', 'mozilla-inbound', 'autoland']


class RequestCounter():
    """It's a object which used to counter request from each branch"""
    BRANCH_COUNTER = {}
    for branch in SETA_BRANCHES:
        BRANCH_COUNTER[branch] = 0

    @staticmethod
    def increase_the_counter(branch):
        RequestCounter.BRANCH_COUNTER[branch] += 1

    @staticmethod
    def reset(branch):
        RequestCounter.BRANCH_COUNTER[branch] = 0

    @staticmethod
    def decrease_the_counter(branch):
        RequestCounter.BRANCH_COUNTER[branch] -= 1
