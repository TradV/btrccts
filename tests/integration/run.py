import pandas
import time
import os
import sys
import unittest
from sccts.algorithm import AlgorithmBase
from sccts.run import ExitReason, \
    execute_algorithm, parse_params_and_execute_algorithm, main_loop
from sccts.timeframe import Timeframe
from tests.common import pd_ts
from unittest.mock import patch, MagicMock

here = os.path.dirname(__file__)
data_dir = os.path.join(here, 'run', 'data_dir')


class TestAlgo(AlgorithmBase):

    @staticmethod
    def configure_argparser(argparser):
        argparser.add_argument('--algo-bool', action='store_true')
        argparser.add_argument('--some-string', default='')

    def __init__(self, context, args):
        self.args = args
        self.exit_reason = None
        self.iterations = 0
        self.kraken = context.create_exchange('kraken')
        self.okex3 = context.create_exchange('okex3')

    def next_iteration(self):
        self.iterations += 1
        if self.iterations == 1:
            self.okex3.create_order(type='market', side='sell',
                                    symbol='ETH/BTC', amount=2)
        if self.iterations == 4:
            self.kraken.create_order(type='market', side='buy',
                                     symbol='BTC/USD', amount=0.1)

    def exit(self, reason):
        self.exit_reason = reason


def assert_test_algo_result(self, result):
    self.assertEqual(type(result), TestAlgo)
    self.assertEqual(result.exit_reason, ExitReason.FINISHED)
    self.assertEqual(result.iterations, 4)
    self.assertEqual(result.okex3.fetch_balance()['total'],
                     {'BTC': 199.40045, 'ETH': 1.0})
    self.assertEqual(result.kraken.fetch_balance()['total'],
                     {'BTC': 0.09974, 'USD': 99.09865})


class LiveTestAlgo(AlgorithmBase):

    def __init__(self, context, args):
        self.iterations = 0
        self.iteration_dates = []

    @staticmethod
    def get_test_time_parameters():
        pd_timedelta = pandas.Timedelta(seconds=2)
        start = pandas.Timestamp.now(tz='UTC').floor(pd_timedelta)
        return {
            'pd_start_date': start,
            'pd_end_date': start + 7 * pd_timedelta,
            'pd_timedelta': pd_timedelta,
        }

    def next_iteration(self):
        self.iteration_dates.append(pandas.Timestamp.now(tz='UTC'))
        if self.iterations == 2:
            time.sleep(6.95)
        if self.iterations == 4:
            time.sleep(2.95)
        self.iterations += 1

    def exit(self, reason):
        self.exit_reason = reason


def assert_test_live_algo_result(test, result, time_parameters):
    test.assertEqual(type(result), LiveTestAlgo)
    test.assertEqual(result.exit_reason, ExitReason.FINISHED)
    test.assertEqual(result.iterations, 6)

    round_to = pandas.Timedelta(seconds=0.1)
    iteration_dates_round = [i.round(round_to) for i in result.iteration_dates]
    start = time_parameters['pd_start_date']
    delta = time_parameters['pd_timedelta']
    test.assertTrue(start < result.iteration_dates[0] < start + delta)
    test.assertEqual(
        iteration_dates_round[1:],
        [start + delta,
         start + 2 * delta,
         start + 5.5 * delta,
         start + 6 * delta,
         start + 7.5 * delta,
         ])


class ExecuteAlgorithmIntegrationTests(unittest.TestCase):

    def test__execute_algorithm(self):
        result = execute_algorithm(exchange_names=['kraken', 'okex3'],
                                   symbols=[],
                                   AlgorithmClass=TestAlgo,
                                   args=self,
                                   start_balances={'okex3': {'ETH': 3},
                                                   'kraken': {'USD': 100}},
                                   pd_start_date=pd_ts('2019-10-01 10:10'),
                                   pd_end_date=pd_ts('2019-10-01 10:16'),
                                   pd_timedelta=pandas.Timedelta(minutes=2),
                                   data_dir=data_dir)
        self.assertEqual(result.args, self)
        assert_test_algo_result(self, result)


def execute_algorithm_return_args(**kwargs):
    return kwargs['args']


class ParseParamsAndExecuteAlgorithmIntegrationTests(unittest.TestCase):

    def create_sys_argv(self, argv_params):
        argv_dict = {'--data-directory': data_dir,
                     '--exchanges': 'kraken',
                     '--symbol': 'BTC/USD',
                     '--start-date': '2001'}
        argv_dict.update(argv_params)
        sys_argv = ['file.py']
        for x, y in argv_dict.items():
            sys_argv.append(x)
            if y is not None:
                sys_argv.append(y)
        return sys_argv

    def test__parse_params_and_execute_algorithm(self):
        sys_argv = self.create_sys_argv({
            '--start-balances': '{"okex3": {"ETH": 3},'
                                ' "kraken": {"USD": 100}}',
            '--exchanges': 'kraken,okex3',
            '--symbols': '',
            '--start-date': '2019-10-01 10:10',
            '--end-date': '2019-10-01 10:16',
            '--algo-bool': None,
            '--some-string': 'testSTR',
            '--timedelta': '2m'})
        with patch.object(sys, 'argv', sys_argv):
            with self.assertLogs():
                result = parse_params_and_execute_algorithm(TestAlgo)
        assert_test_algo_result(self, result)
        self.assertEqual(result.args.algo_bool, True)
        self.assertEqual(result.args.some_string, 'testSTR')
        self.assertEqual(result.args.live, False)


class MainLoopIntegrationTest(unittest.TestCase):

    def test__main_loop__live(self):
        algo = LiveTestAlgo(MagicMock(), MagicMock())
        time_params = LiveTestAlgo.get_test_time_parameters()
        timeframe = Timeframe(pd_start_date=time_params['pd_start_date'],
                              pd_end_date=time_params['pd_end_date'],
                              pd_timedelta=time_params['pd_timedelta'])
        result = main_loop(timeframe=timeframe, algorithm=algo, live=True)

        assert_test_live_algo_result(self, result, time_params)
