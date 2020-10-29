
import unittest
import collections.abc
from exception_group import ExceptionGroup, TracebackGroup


class ExceptionGroupTestBase(unittest.TestCase):

    def assertMatchesTemplate(self, exc, template):
        """ Assert that the exception matches the template """
        if isinstance(exc, ExceptionGroup):
            self.assertIsInstance(template, collections.abc.Sequence)
            self.assertEqual(len(exc.excs), len(template))
            for e, t in zip(exc.excs, template):
              self.assertMatchesTemplate(e, t)
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

    def funcname(self, tb_frame):
        return tb_frame.f_code.co_name

    def funcnames(self, tb):
        """ Extract function names from a traceback """

        names = []
        while tb:
            names.append(self.funcname(tb.tb_frame))
            tb = tb.tb_next
        return names

    def _reduce(self, template, types):
        """ reduce a nested list of types to certain types

        The result is a nested list of the same shape as template,
        but with only exceptions that match types
        """
        if isinstance(template, collections.abc.Sequence):
            res = [self._reduce(t, types) for t in template]
            return [x for x in res if x is not None]
        elif isinstance(template, types):
            return template
        else:
            return None

class ExceptionGroupTestUtilsTests(ExceptionGroupTestUtils):
    def test_basic_utility_functions(self):
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

    def test_reduce(self):
        te = TypeError('int')
        se = SyntaxError('blah')
        ve1 = ValueError(1)
        ve2 = ValueError(2)
        template = [[te, ve1], se, [ve2]]
        reduce = self._reduce
        self.assertEqual(reduce(template, ()), [[],[]])
        self.assertEqual(reduce(template, TypeError), [[te],[]])
        self.assertEqual(reduce(template, ValueError), [[ve1],[ve2]])
        self.assertEqual(reduce(template, SyntaxError), [[], se, []])
        self.assertEqual(
            reduce(template, (TypeError, ValueError)), [[te, ve1], [ve2]])
        self.assertEqual(
            reduce(template, (TypeError, SyntaxError)), [[te], se, []])

class ExceptionGroupConstructionTests(ExceptionGroupTestUtils):

    def test_construction_simple(self):
        # create a simple exception group and check that
        # it is constructed as expected
        try:
            eg = None
            self.simple_exception_group(0)
        except ExceptionGroup as e:
            eg = e
        # check eg.excs
        self.assertIsInstance(eg.excs, collections.abc.Sequence)
        self.assertMatchesTemplate(eg, self.get_test_exceptions_list(0))

        # check iteration
        self.assertEqual(list(eg), list(eg.excs))

        # check tracebacks
        for e in eg:
            expected = [
                'test_construction_simple',
                'simple_exception_group',
                'simple_exception_group',
                'raise'+type(e).__name__,
            ]
            etb = eg.extract_traceback(e)
            self.assertEqual(expected, [self.funcname(f) for f in etb])

    def test_construction_nested(self):
        # create a nested exception group and check that
        # it is constructed as expected
        try:
            eg = None
            self.nested_exception_group()
        except ExceptionGroup as e:
            eg = e
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

        eg_template = [self.get_test_exceptions_list(i) for i in [1,2,3]]
        self.assertMatchesTemplate(eg, eg_template)

        # check iteration
        self.assertEqual(list(eg), all_excs)

        # check tracebacks
        for e in eg:
            expected = [
                'test_construction_nested',
                'nested_exception_group',
                'nested_exception_group',
                'simple_exception_group',
                'simple_exception_group',
                'raise'+type(e).__name__,
            ]
            etb = eg.extract_traceback(e)
            self.assertEqual(expected, [self.funcname(f) for f in etb])

class ExceptionGroupSplitTests(ExceptionGroupTestUtils):

    def _split_exception_group(self, eg, types):
        """ Split an EG and do some sanity checks on the result """
        self.assertIsInstance(eg, ExceptionGroup)
        fnames = self.funcnames(eg.__traceback__)
        all_excs = list(eg)

        match, rest = eg.split(types)

        self.assertIsInstance(match, ExceptionGroup)
        self.assertIsInstance(rest, ExceptionGroup)

        self.assertEqual(len(all_excs), len(eg))
        self.assertEqual(len(all_excs), len(match) + len(rest))
        for e in all_excs:
            self.assertIn(e, eg)
            # every exception in all_excs is in eg and
            # in exactly one of match and rest
            self.assertNotEqual(e in match, e in rest)

        for e in match:
            self.assertIsInstance(e, types)
        for e in rest:
            self.assertNotIsInstance(e, types)

        # check tracebacks
        for part in [match, rest]:
            for e in part:
                self.assertEqual(
                    eg.extract_traceback(e),
                    part.extract_traceback(e))

        return match, rest

    def test_split_simple(self):
        checkMatch = self.assertMatchesTemplate
        try:
            eg = None
            self.simple_exception_group(5)
        except ExceptionGroup as e:
            eg = e
        fnames = ['test_split_simple', 'simple_exception_group']
        self.assertEqual(self.funcnames(eg.__traceback__), fnames)

        eg_template = self.get_test_exceptions_list(5)
        checkMatch(eg, eg_template)

        match, rest = self._split_exception_group(eg, SyntaxError)
        checkMatch(eg, eg_template)
        checkMatch(match, [])
        checkMatch(rest, eg_template)

        match, rest = self._split_exception_group(eg, ValueError)
        checkMatch(eg, eg_template)
        checkMatch(match, self._reduce(eg_template, ValueError))
        checkMatch(rest, self._reduce(eg_template, TypeError))

        match, rest = self._split_exception_group(eg, TypeError)
        checkMatch(eg, eg_template)
        checkMatch(match, self._reduce(eg_template, TypeError))
        checkMatch(rest, self._reduce(eg_template, ValueError))

        match, rest = self._split_exception_group(eg, (ValueError, SyntaxError))
        checkMatch(eg, eg_template)
        checkMatch(match, self._reduce(eg_template, ValueError))
        checkMatch(rest, self._reduce(eg_template, TypeError))

        match, rest = self._split_exception_group(eg, (ValueError, TypeError))
        checkMatch(eg, eg_template)
        checkMatch(match, eg_template)
        checkMatch(rest, [])

    def test_split_nested(self):
        checkMatch = self.assertMatchesTemplate
        try:
            eg = None
            self.nested_exception_group()
        except ExceptionGroup as e:
            eg = e
        fnames = ['test_split_nested', 'nested_exception_group']
        self.assertEqual(self.funcnames(eg.__traceback__), fnames)

        eg_template = [self.get_test_exceptions_list(i) for i in [1,2,3]]
        checkMatch(eg, eg_template)

        match, rest = self._split_exception_group(eg, SyntaxError)
        checkMatch(eg, eg_template)
        checkMatch(match, [[],[],[]])
        checkMatch(rest, eg_template)

        match, rest = self._split_exception_group(eg, ValueError)
        checkMatch(eg, eg_template)
        checkMatch(match, self._reduce(eg_template, ValueError))
        checkMatch(rest, self._reduce(eg_template, TypeError))

        match, rest = self._split_exception_group(eg, TypeError)
        checkMatch(eg, eg_template)
        checkMatch(match, self._reduce(eg_template, TypeError))
        checkMatch(rest, self._reduce(eg_template, ValueError))

        match, rest = self._split_exception_group(eg, (ValueError, SyntaxError))
        checkMatch(eg, eg_template)
        checkMatch(match, self._reduce(eg_template, ValueError))
        checkMatch(rest, self._reduce(eg_template, TypeError))

        match, rest = self._split_exception_group(eg, (ValueError, TypeError))
        checkMatch(eg, eg_template)
        checkMatch(match, eg_template)
        checkMatch(rest, [[],[],[]])

class ExceptionGroupCatchTests(ExceptionGroupTestUtils):
    def test_catch_simple_eg_swallowing_handler(self):
        checkMatch = self.assertMatchesTemplate

        def handler(eg):
            nonlocal caught
            caught = eg

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                self.simple_exception_group(7)
        except ExceptionGroup as eg:
            raised = eg
        eg_template = self.get_test_exceptions_list(7)
        checkMatch(raised, eg_template)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                self.simple_exception_group(8)
        finally:
            eg_template = self.get_test_exceptions_list(8)
            checkMatch(caught, eg_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.simple_exception_group(6)
        except ExceptionGroup as eg:
            raised = eg
        eg_template = self.get_test_exceptions_list(6)
        checkMatch(raised, self._reduce(eg_template, ValueError))
        checkMatch(caught, self._reduce(eg_template, TypeError))

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.simple_exception_group(6)
        except ExceptionGroup as eg:
            raised = eg
        eg_template = self.get_test_exceptions_list(6)
        checkMatch(raised, self._reduce(eg_template, TypeError))
        checkMatch(caught, self._reduce(eg_template, ValueError))

    def test_catch_nested_eg_swallowing_handler(self):
        checkMatch =self.assertMatchesTemplate

        eg_template = [self.get_test_exceptions_list(i) for i in [1,2,3]]

        def handler(eg):
            nonlocal caught
            caught = eg

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised, eg_template)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                self.nested_exception_group()
        finally:
            checkMatch(caught, eg_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised, self._reduce(eg_template, ValueError))
        checkMatch(caught, self._reduce(eg_template, TypeError))

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised, self._reduce(eg_template, TypeError))
        checkMatch(caught, self._reduce(eg_template, ValueError))

    def test_catch_nested_eg_raising_handler(self):
        checkMatch =self.assertMatchesTemplate

        eg_template = [self.get_test_exceptions_list(i) for i in [1,2,3]]
        raised_template = [ValueError('foo'), 
                           [SyntaxError('bar'), ValueError('baz')]
                          ]

        def handler(eg):
            nonlocal caught
            caught = eg
            return ExceptionGroup(
                       [ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised, eg_template)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised, raised_template)
        checkMatch(caught, eg_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised,
                   self._reduce(eg_template, ValueError)  + raised_template)
        checkMatch(caught, self._reduce(eg_template, TypeError))

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        checkMatch(raised,
                   self._reduce(eg_template, TypeError) + raised_template)
        checkMatch(caught, self._reduce(eg_template, ValueError))

if __name__ == '__main__':
    unittest.main()
