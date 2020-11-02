
import functools
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

    def tracebackGroupSanityCheck(self, exc):
        if not isinstance(exc, ExceptionGroup):
            return

        tbg = exc.__traceback_group__
        all_excs = list(exc)
        self.assertEqual(len(tbg.tb_next_map), len(all_excs))
        self.assertEqual([i for i in tbg.tb_next_map],
                         [id(e) for e in exc])

        for e in exc.excs:
            self.tracebackGroupSanityCheck(e)

    def to_template(self, exc):
        if isinstance(exc, ExceptionGroup):
            return [self.to_template(e) for e in exc.excs]
        else:
            return exc

class ExceptionGroupTestUtils(ExceptionGroupTestBase):

    def create_EG(self, raisers):
        excs = []
        for r in raisers:
            try:
                r()
            except (Exception, ExceptionGroup) as e:
                excs.append(e)
        try:
            raise ExceptionGroup(excs)
        except ExceptionGroup as e:
            return e

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
        bind = functools.partial
        eg = self.create_EG(
            [bind(self.raiseValueError, 1),
             bind(self.raiseTypeError, int),
             bind(self.raiseValueError, 2),
            ])

        self.assertEqual(len(eg.excs), 3)
        self.assertMatchesTemplate(eg,
            [ValueError(1), TypeError(int), ValueError(2)])

        # check iteration
        self.assertEqual(list(eg), list(eg.excs))

        # check tracebacks
        for e in eg:
            expected = [
                'create_EG',
                'create_EG',
                'raise'+type(e).__name__,
            ]
            etb = eg.extract_traceback(e)
            self.assertEqual(expected, [self.funcname(f) for f in etb])

    def test_construction_nested(self):
        # create a nested exception group and check that
        # it is constructed as expected
        bind = functools.partial
        level1 = lambda i: self.create_EG([
                bind(self.raiseValueError, i),
                bind(self.raiseTypeError, int),
                bind(self.raiseValueError, i+1),
            ])

        def raiseException(e): raise e
        level2 = lambda i : self.create_EG([
                bind(raiseException, level1(i)),
                bind(raiseException, level1(i+1)),
                bind(self.raiseValueError, i+2),
            ])

        level3 = lambda i : self.create_EG([
                bind(raiseException, level2(i+1)),
                bind(self.raiseValueError, i+2),
            ])
        eg = level3(5)

        self.assertMatchesTemplate(eg,
            [
                [
                    [ValueError(6), TypeError(int), ValueError(7)],
                    [ValueError(7), TypeError(int), ValueError(8)],
                    ValueError(8),
                ],
                ValueError(7)
            ])

        # check iteration

        self.assertEqual(len(list(eg)), 8)

        # check tracebacks

        self.tracebackGroupSanityCheck(eg)

        all_excs = list(eg)
        for e in all_excs[0:6]:
            expected = [
                'create_EG',
                'create_EG',
                'raiseException',
                'create_EG',
                'create_EG',
                'raiseException',
                'create_EG',
                'create_EG',
                'raise'+type(e).__name__,
            ]
            etb = eg.extract_traceback(e)
            self.assertEqual(expected, [self.funcname(f) for f in etb])
        self.assertEqual(['create_EG', 'create_EG', 'raiseException',
            'create_EG', 'create_EG', 'raiseValueError'],
            [self.funcname(f) for f in eg.extract_traceback(all_excs[6])])
        self.assertEqual(['create_EG', 'create_EG', 'raiseValueError'],
            [self.funcname(f) for f in eg.extract_traceback(all_excs[7])])


class ExceptionGroupSplitTests(ExceptionGroupTestUtils):

    def _split_exception_group(self, eg, types):
        """ Split an EG and do some sanity checks on the result """
        self.assertIsInstance(eg, ExceptionGroup)
        fnames = self.funcnames(eg.__traceback__)
        all_excs = list(eg)

        match, rest = eg.split(types)

        self.assertIsInstance(match, ExceptionGroup)
        self.assertIsInstance(rest, ExceptionGroup)
        self.assertEqual(len(list(all_excs)), len(list(match)) + len(list(rest)))

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

    def test_split_nested(self):
        # create a nested exception group and check that
        # it is constructed as expected
        bind = functools.partial
        level1 = lambda i: self.create_EG([
                bind(self.raiseValueError, i),
                bind(self.raiseTypeError, int),
                bind(self.raiseValueError, i+10),
            ])

        def raiseException(e): raise e
        level2 = lambda i : self.create_EG([
                bind(raiseException, level1(i)),
                bind(raiseException, level1(i+20)),
                bind(self.raiseValueError, i+30),
            ])

        level3 = lambda i : self.create_EG([
                bind(raiseException, level2(i+40)),
                bind(self.raiseValueError, i+50),
            ])
        try:
            raise level3(5)
        except ExceptionGroup as e:
            eg = e

        fnames = ['test_split_nested', 'create_EG']
        self.assertEqual(self.funcnames(eg.__traceback__), fnames)

        eg_template = [
                        [
                            [ValueError(45), TypeError(int), ValueError(55)],
                            [ValueError(65), TypeError(int), ValueError(75)],
                            ValueError(75),
                        ],
                        ValueError(55)
                      ]
        self.assertMatchesTemplate(eg, eg_template)

        # Match Nothing
        match, rest = self._split_exception_group(eg, SyntaxError)
        self.assertTrue(match.is_empty())
        self.assertMatchesTemplate(rest, eg_template)

        # Match Everything
        match, rest = self._split_exception_group(eg, BaseException)
        self.assertMatchesTemplate(match, eg_template)
        self.assertTrue(rest.is_empty())
        match, rest = self._split_exception_group(eg, (ValueError, TypeError))
        self.assertMatchesTemplate(match, eg_template)
        self.assertTrue(rest.is_empty())

        # Match ValueErrors
        match, rest = self._split_exception_group(eg, ValueError)
        self.assertMatchesTemplate(match,
            [
                [
                    [ValueError(45), ValueError(55)],
                    [ValueError(65), ValueError(75)],
                    ValueError(75),
                ],
                ValueError(55)
            ])
        self.assertMatchesTemplate(
            rest, [[[TypeError(int)],[TypeError(int)]]])

        # Match TypeErrors
        match, rest = self._split_exception_group(eg, (TypeError, SyntaxError))
        self.assertMatchesTemplate(
            match, [[[TypeError(int)],[TypeError(int)]]])
        self.assertMatchesTemplate(rest,
            [
                [
                    [ValueError(45), ValueError(55)],
                    [ValueError(65), ValueError(75)],
                    ValueError(75),
                ],
                ValueError(55)
            ])


class ExceptionGroupCatchTests(ExceptionGroupTestUtils):
    def checkMatch(self, exc, template, reference_tbs):
        self.assertMatchesTemplate(exc, template)
        for e in exc:
            result = [self.funcname(f) for f in exc.extract_traceback(e)]
            ref = reference_tbs[(type(e), e.args)]
            # result has more frames from the Catcher context
            # manager, ignore them
            try:
                result.remove('__exit__')
            except ValueError:
                pass
            if result != ref:
                self.assertEqual(result[-len(ref):], ref)

    def test_catch_simple_eg_swallowing_handler(self):
        try:
            self.simple_exception_group(12)
        except ExceptionGroup as eg:
            ref_tbs = {}
            for e in eg:
                tb = [self.funcname(f) for f in eg.extract_traceback(e)]
                ref_tbs[(type(e), e.args)] = tb
            eg_template = self.to_template(eg)

        def handler(eg):
            nonlocal caught
            caught = eg

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                self.simple_exception_group(12)
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, eg_template, ref_tbs)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                self.simple_exception_group(12)
        finally:
            self.checkMatch(caught, eg_template, ref_tbs)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.simple_exception_group(12)
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, self._reduce(eg_template, ValueError), ref_tbs)
        self.checkMatch(caught, self._reduce(eg_template, TypeError), ref_tbs)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.simple_exception_group(12)
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, self._reduce(eg_template, TypeError), ref_tbs)
        self.checkMatch(caught, self._reduce(eg_template, ValueError), ref_tbs)

    def test_catch_nested_eg_swallowing_handler(self):
        try:
            self.nested_exception_group()
        except ExceptionGroup as eg:
            ref_tbs = {}
            for e in eg:
                tb = [self.funcname(f) for f in eg.extract_traceback(e)]
                ref_tbs[(type(e), e.args)] = tb
            eg_template = self.to_template(eg)

        def handler(eg):
            nonlocal caught
            caught = eg

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, eg_template, ref_tbs)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                self.nested_exception_group()
        finally:
            self.checkMatch(caught, eg_template, ref_tbs)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, self._reduce(eg_template, ValueError), ref_tbs)
        self.checkMatch(caught, self._reduce(eg_template, TypeError), ref_tbs)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, self._reduce(eg_template, TypeError), ref_tbs)
        self.checkMatch(caught, self._reduce(eg_template, ValueError), ref_tbs)

    def test_catch_nested_eg_handler_raises_new_exceptions(self):
        def handler(eg):
            nonlocal caught
            caught = eg
            return ExceptionGroup(
                       [ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])

        try:
            self.nested_exception_group()
        except ExceptionGroup as eg:
            eg1 = eg
            eg_template = self.to_template(eg)

        try:
            raise handler(None)
        except ExceptionGroup as eg:
            eg2 = eg
            raised_template = self.to_template(eg)

        ref_tbs = {}
        for eg in (eg1, eg2):
            for e in eg:
                tb = [self.funcname(f) for f in eg.extract_traceback(e)]
                ref_tbs[(type(e), e.args)] = tb

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, eg_template, ref_tbs)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, raised_template, ref_tbs)
        self.checkMatch(caught, eg_template, ref_tbs)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised,
                   [self._reduce(eg_template, ValueError), raised_template],
                   ref_tbs)
        self.checkMatch(caught, self._reduce(eg_template, TypeError), ref_tbs)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised,
                   [self._reduce(eg_template, TypeError), raised_template],
                   ref_tbs)
        self.checkMatch(caught, self._reduce(eg_template, ValueError), ref_tbs)

    def test_catch_nested_eg_handler_reraise_all_matched(self):
        def handler(eg):
            return eg

        try:
            self.nested_exception_group()
        except ExceptionGroup as eg:
            eg1 = eg
            eg_template = self.to_template(eg)

        ref_tbs = {}
        for e in eg1:
            tb = [self.funcname(f) for f in eg1.extract_traceback(e)]
            ref_tbs[(type(e), e.args)] = tb

        try: ######### Catch TypeErrors:
            raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, eg_template, ref_tbs)

        try: ######### Catch ValueErrors:
            raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, eg_template, ref_tbs)

    def test_catch_nested_eg_handler_reraise_new_and_all_old(self):
        def handler(eg):
            return ExceptionGroup(
                       [eg,
                        ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])

        try:
            self.nested_exception_group()
        except ExceptionGroup as eg:
            eg1 = eg
            eg_template = self.to_template(eg)

        class DummyException(Exception): pass
        try:
            raise handler(DummyException())
        except ExceptionGroup as eg:
            _, eg2 = eg.split(DummyException)
            new_raised_template = self.to_template(eg2)

        ref_tbs = {}
        for eg in (eg1, eg2):
            for e in eg:
                tb = [self.funcname(f) for f in eg.extract_traceback(e)]
                ref_tbs[(type(e), e.args)] = tb

        try: ######### Catch TypeErrors:
            raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, [eg_template, new_raised_template], ref_tbs)

        try: ######### Catch ValueErrors:
            raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, [eg_template, new_raised_template], ref_tbs)

    def test_catch_nested_eg_handler_reraise_new_and_some_old(self):
        def handler(eg):
            ret = ExceptionGroup(
                       [eg.excs[1],
                        ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])
            return ret

        try:
            self.nested_exception_group()
        except ExceptionGroup as eg:
            eg1 = eg
            eg_template = self.to_template(eg)

        class DummyException(Exception): pass
        try:
            eg = ExceptionGroup([DummyException(), DummyException()])
            raise handler(eg)
        except ExceptionGroup as eg:
            _, eg2 = eg.split(DummyException)
            new_raised_template = self.to_template(eg2)

        ref_tbs = {}
        for eg in (eg1, eg2):
            for e in eg:
                tb = [self.funcname(f) for f in eg.extract_traceback(e)]
                ref_tbs[(type(e), e.args)] = tb

        try: ######### Catch TypeErrors:
            raised = None
            with ExceptionGroup.catch(TypeError, handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised,
                        [
                         [ self._reduce(eg_template[0], ValueError),
                           eg_template[1],
                           self._reduce(eg_template[2], ValueError),
                         ],
                         new_raised_template],
                        ref_tbs)

        try: ######### Catch ValueErrors:
            raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                self.nested_exception_group()
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised,
                        [
                         [ self._reduce(eg_template[0], TypeError),
                           eg_template[1],
                           self._reduce(eg_template[2], TypeError),
                         ],
                         new_raised_template],
                        ref_tbs)

if __name__ == '__main__':
    unittest.main()
