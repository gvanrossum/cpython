
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

class ExceptionGroupTestUtils(ExceptionGroupTestBase):

    def create_EG(self, raisers, message=None):
        excs = []
        for r in raisers:
            try:
                r()
            except (Exception, ExceptionGroup) as e:
                excs.append(e)
        try:
            raise ExceptionGroup(excs, message=message)
        except ExceptionGroup as e:
            return e

    def raiseValueError(self, v):
        raise ValueError(v)

    def raiseTypeError(self, t):
        raise TypeError(t)

    def funcname(self, tb_frame):
        return tb_frame.f_code.co_name

    def funcnames(self, tb):
        """ Extract function names from a traceback """
        names = []
        while tb:
            names.append(self.funcname(tb.tb_frame))
            tb = tb.tb_next
        return names

class ExceptionGroupConstructionTests(ExceptionGroupTestUtils):

    def test_construction_simple(self):
        # create a simple exception group and check that
        # it is constructed as expected
        bind = functools.partial
        eg = self.create_EG(
            [bind(self.raiseValueError, 1),
             bind(self.raiseTypeError, int),
             bind(self.raiseValueError, 2),
            ], message='hello world')

        self.assertEqual(len(eg.excs), 3)
        self.assertMatchesTemplate(eg,
            [ValueError(1), TypeError(int), ValueError(2)])

        # check iteration
        self.assertEqual(list(eg), list(eg.excs))

        # check message
        self.assertEqual(eg.message, 'hello world')
        self.assertEqual(eg.args, ('hello world',))

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
        # create a nested exception group
        bind = functools.partial
        level1 = lambda i: self.create_EG([
                bind(self.raiseValueError, i),
                bind(self.raiseTypeError, int),
                bind(self.raiseValueError, i+11),
            ])

        def raiseException(e): raise e
        level2 = lambda i : self.create_EG([
                bind(raiseException, level1(i)),
                bind(raiseException, level1(i+22)),
                bind(self.raiseValueError, i+33),
            ])

        level3 = lambda i : self.create_EG([
                bind(raiseException, level2(i+44)),
                bind(self.raiseValueError, i+55),
            ])
        try:
            raise level3(6)
        except ExceptionGroup as e:
            eg = e

        fnames = ['test_split_nested', 'create_EG']
        self.assertEqual(self.funcnames(eg.__traceback__), fnames)

        eg_template = [
                        [
                            [ValueError(50), TypeError(int), ValueError(61)],
                            [ValueError(72), TypeError(int), ValueError(83)],
                            ValueError(83),
                        ],
                        ValueError(61)
                      ]
        self.assertMatchesTemplate(eg, eg_template)

        valueErrors_template = [
                                   [
                                        [ValueError(50), ValueError(61)],
                                        [ValueError(72), ValueError(83)],
                                        ValueError(83),
                                   ],
                                   ValueError(61)
                               ]

        typeErrors_template = [[[TypeError(int)],[TypeError(int)]]]


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
        self.assertMatchesTemplate(match, valueErrors_template)
        self.assertMatchesTemplate(rest, typeErrors_template)

        # Match TypeErrors
        match, rest = self._split_exception_group(eg, (TypeError, SyntaxError))
        self.assertMatchesTemplate(match, typeErrors_template)
        self.assertMatchesTemplate(rest, valueErrors_template)


class ExceptionGroupCatchTests(ExceptionGroupTestUtils):
    def setUp(self):
        super().setUp()

       # create a nested exception group
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
            self.eg = e

        fnames = ['setUp', 'create_EG']
        self.assertEqual(self.funcnames(self.eg.__traceback__), fnames)

        # templates
        self.eg_template = [
                        [
                            [ValueError(45), TypeError(int), ValueError(55)],
                            [ValueError(65), TypeError(int), ValueError(75)],
                            ValueError(75),
                        ],
                        ValueError(55)
                      ]

        self.valueErrors_template = [
                                        [
                                            [ValueError(45), ValueError(55)],
                                            [ValueError(65), ValueError(75)],
                                            ValueError(75),
                                        ],
                                        ValueError(55)
                                   ]

        self.typeErrors_template = [[[TypeError(int)],[TypeError(int)]]]


    def checkMatch(self, exc, template):
        self.assertMatchesTemplate(exc, template)
        for e in exc:
            result = [self.funcname(f) for f in exc.extract_traceback(e)]


    def test_catch_handler_raises_subsets_of_caught(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        def handler(e):
            nonlocal caught
            caught = e

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, eg_template)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                raise eg
        finally:
            self.checkMatch(caught, eg_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, valueErrors_template)
        self.checkMatch(caught, typeErrors_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                raise eg
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, typeErrors_template)
        self.checkMatch(caught, valueErrors_template)

    def test_catch_handler_adds_new_exceptions(self):
        # create a nested exception group
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        def handler(eg):
            nonlocal caught
            caught = eg
            return ExceptionGroup(
                       [ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])

        newErrors_template = [
            ValueError('foo'), [SyntaxError('bar'), ValueError('baz')]]

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        # handler is never called
        self.checkMatch(raised, eg_template)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, newErrors_template)
        self.checkMatch(caught, eg_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, [valueErrors_template, newErrors_template])
        self.checkMatch(caught, typeErrors_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                raise eg
        except ExceptionGroup as eg:
            raised = eg
        self.checkMatch(raised, [typeErrors_template, newErrors_template])
        self.checkMatch(caught, valueErrors_template)


    def test_catch_handler_reraise_all_matched(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        def handler(eg):
            nonlocal caught
            caught = eg
            return eg

        try: ######### Catch nothing:
            caught = raised = None
            with ExceptionGroup.catch(SyntaxError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        # handler is never called
        self.checkMatch(raised, eg_template)
        self.assertIsNone(caught)

        try: ######### Catch everything:
            caught = None
            with ExceptionGroup.catch((ValueError, TypeError), handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, eg_template)
        self.checkMatch(caught, eg_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch(TypeError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, eg_template)
        self.checkMatch(caught, typeErrors_template)

        try: ######### Catch something:
            caught = raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, eg_template)
        self.checkMatch(caught, valueErrors_template)

    def test_catch_handler_reraise_new_and_all_old(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        def handler(eg):
            return ExceptionGroup(
                       [eg,
                        ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])

        newErrors_template = [
            ValueError('foo'), [SyntaxError('bar'), ValueError('baz')]]

        try: ######### Catch TypeErrors:
            raised = None
            with ExceptionGroup.catch(TypeError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, [eg_template, newErrors_template])

        try: ######### Catch ValueErrors:
            raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        self.checkMatch(raised, [eg_template, newErrors_template])

    def test_catch_handler_reraise_new_and_some_old(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        def handler(eg):
            ret = ExceptionGroup(
                       [eg.excs[0],
                        ValueError('foo'),
                        ExceptionGroup(
                            [SyntaxError('bar'), ValueError('baz')])])
            return ret

        newErrors_template = [
            ValueError('foo'), [SyntaxError('bar'), ValueError('baz')]]

        try: ######### Catch TypeErrors:
            raised = None
            with ExceptionGroup.catch(TypeError, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        # all TypeError are in eg.excs[0] so everything was reraised
        self.checkMatch(raised, [eg_template, newErrors_template])

        try: ######### Catch ValueErrors:
            raised = None
            with ExceptionGroup.catch((ValueError, SyntaxError), handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        # eg.excs[0] is reraised and eg.excs[1] is consumed
        self.checkMatch(raised, [[eg_template[0]], newErrors_template])

if __name__ == '__main__':
    unittest.main()
