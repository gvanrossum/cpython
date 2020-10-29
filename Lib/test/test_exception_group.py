
import unittest
import collections.abc
from exception_group import ExceptionGroup, TracebackGroup


class ExceptionGroupTestBase(unittest.TestCase):

    def assertExceptionMatchesTemplate(self, exc, template):
        """ Assert that the exception matches the template """
        if isinstance(exc, ExceptionGroup):
            self.assertIsInstance(template, collections.abc.Sequence)
            self.assertEqual(len(exc.excs), len(template))
            for e, t in zip(exc.excs, template):
              self.assertExceptionMatchesTemplate(e, t)
        else:
            self.assertIsInstance(template, BaseException)
            self.assertEqual(type(exc), type(template))
            self.assertEqual(exc.args, template.args)

class ExceptionGroupTestUtils(ExceptionGroupTestBase):
    def raiseValueError(self, v):
        raise ValueError(v)

    def raiseTypeError(self, t):
        raise TypeError(t)

    def get_test_exceptions(self, x):
        return [
            (self.raiseValueError, ValueError, x+1),
            (self.raiseTypeError, TypeError, 'int'),
            (self.raiseValueError, ValueError, x+2),
            (self.raiseValueError, ValueError, x+3),
            (self.raiseTypeError, TypeError, 'list'),
        ]

    def get_test_exceptions_list(self, x):
        return [t(arg) for _, t, arg in self.get_test_exceptions(x)]

    def simple_exception_group(self, x):
        excs = []
        for f, _, arg in self.get_test_exceptions(x):
            try:
                f(arg)
            except Exception as e:
                excs.append(e)
        raise ExceptionGroup(excs)

    def nested_exception_group(self):
        excs = []
        for x in [1,2,3]:
            try:
                self.simple_exception_group(x)
            except ExceptionGroup as e:
                excs.append(e)
        raise ExceptionGroup(excs)

    def funcnames(self, tb):
        """ Extract function names from a traceback """
        funcname = lambda tb_frame: tb_frame.f_code.co_name
        names = []
        while tb:
            names.append(funcname(tb.tb_frame))
            tb = tb.tb_next
        return names

    def test_utility_functions(self):
        self.assertRaises(ValueError, self.raiseValueError, 42)
        self.assertRaises(TypeError, self.raiseTypeError, float)
        self.assertRaises(ExceptionGroup, self.simple_exception_group, 42)
        self.assertRaises(ExceptionGroup, self.nested_exception_group)

        test_excs = self.get_test_exceptions_list(42)
        self.assertEqual(len(test_excs), 5)
        expected = [("TypeError", 'int'),
                    ("TypeError", 'list'),
                    ("ValueError", 43),
                    ("ValueError", 44),
                    ("ValueError", 45)]
        self.assertSequenceEqual(expected,
            sorted((type(e).__name__, e.args[0]) for e in test_excs))

class ExceptionGroupConstructionTests(ExceptionGroupTestUtils):

    def test_construction_simple(self):
        # create a simple exception group and check that
        # it is constructed as expected
        try:
            self.simple_exception_group(0)
            self.assertFalse(True, 'exception not raised')
        except ExceptionGroup as eg:
            # check eg.excs
            self.assertIsInstance(eg.excs, collections.abc.Sequence)
            self.assertExceptionMatchesTemplate(eg, self.get_test_exceptions_list(0))

            # check iteration
            self.assertEqual(list(eg), list(eg.excs))

            # check eg.__traceback__
            self.assertEqual(self.funcnames(eg.__traceback__),
                ['test_construction_simple', 'simple_exception_group'])

            # check eg.__traceback_group__
            tbg = eg.__traceback_group__
            self.assertEqual(len(tbg.tb_next_map), 5)
            self.assertEqual(tbg.tb_next_map.keys(), set(eg.excs))
            for e, tb in tbg.tb_next_map.items():
                self.assertEqual(self.funcnames(tb), ['raise'+type(e).__name__])

        else:
            self.assertFalse(True, 'exception not caught')

    def test_construction_nested(self):
        # create a nested exception group and check that
        # it is constructed as expected
        try:
            self.nested_exception_group()
            self.assertFalse(True, 'exception not raised')
        except ExceptionGroup as eg:
            # check eg.excs
            self.assertIsInstance(eg.excs, collections.abc.Sequence)
            self.assertEqual(len(eg.excs), 3)

            # each of eg.excs is an EG with 3xValueError and 2xTypeErrors
            all_excs = []
            for e in eg.excs:
                self.assertIsInstance(e, ExceptionGroup)
                self.assertEqual(len(e.excs), 5)
                etypes = [type(e) for e in e.excs]
                self.assertEqual(etypes.count(ValueError), 3)
                self.assertEqual(etypes.count(TypeError), 2)
                all_excs.extend(e.excs)

            expected_excs = []
            expected_excs.append(self.get_test_exceptions_list(1))
            expected_excs.append(self.get_test_exceptions_list(2))
            expected_excs.append(self.get_test_exceptions_list(3))
            self.assertExceptionMatchesTemplate(eg, expected_excs)

            # check iteration
            self.assertEqual(list(eg), all_excs)

            # check eg.__traceback__
            tb = eg.__traceback__
            self.assertEqual(self.funcnames(tb),
                ['test_construction_nested', 'nested_exception_group'])

            # check eg.__traceback_group__
            tbg = eg.__traceback_group__
            self.assertEqual(len(tbg.tb_next_map), 15)

            self.assertEqual(list(tbg.tb_next_map.keys()), all_excs)
            for e, tb in tbg.tb_next_map.items():
                self.assertEqual(self.funcnames(tb),
                    ['simple_exception_group', 'raise'+type(e).__name__])
        else:
            self.assertFalse(True, 'exception not caught')

class ExceptionGroupSplitTests(ExceptionGroupTestUtils):
    def test_split_simple(self):
        try:
            self.simple_exception_group(5)
            self.assertFalse(True, 'exception not raised')
        except ExceptionGroup as eg:
            syntaxError, ref = eg.split(SyntaxError)
            # TODO: check everything
            valueError, ref = eg.split(ValueError)
            # TODO: check everything
            typeError, ref = eg.split(TypeError)
            # TODO: check everything
            valueError, ref = eg.split((ValueError, SyntaxError))
            # TODO: check everything
            valueError, ref = eg.split((ValueError, TypeError))
            # TODO: check everything
        else:
            self.assertFalse(True, 'exception not caught')

    def test_split_nested(self):
        try:
            self.nested_exception_group()
            self.assertFalse(True, 'exception not raised')
        except ExceptionGroup as eg:
            syntaxError, ref = eg.split(SyntaxError)
            # TODO: check everything
            valueError, ref = eg.split(ValueError)
            # TODO: check everything
            typeError, ref = eg.split(TypeError)
            # TODO: check everything
            valueError, ref = eg.split((ValueError, SyntaxError))
            # TODO: check everything
            valueError, ref = eg.split((ValueError, TypeError))
            # TODO: check everything
        else:
            self.assertFalse(True, 'exception not caught')


class ExceptionGroupCatchTests(ExceptionGroupTestUtils):
    pass # TODO - write the catch context manager and add tests


if __name__ == '__main__':
    unittest.main()
