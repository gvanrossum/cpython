
import collections.abc
import functools
import traceback
import unittest
from exception_group import ExceptionGroup, TracebackGroup, StackGroupSummary
from io import StringIO

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

    def newEG(self, raisers, message=None):
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

    def newVE(self, v):
        raise ValueError(v)

    def newTE(self, t):
        raise TypeError(t)

    def extract_traceback(self, exc, eg):
        """ returns the traceback of a single exception

        If exc is in the exception group, return its
        traceback as the concatenation of the outputs
        of traceback.extract_tb() on each segment of
        it traceback (one per each ExceptionGroup that
        it belongs to).
        """
        if exc not in eg:
            return None
        e = eg.subgroup([exc])
        result = None
        while e is not None:
            if isinstance(e, ExceptionGroup):
               assert len(e.excs) == 1 and exc in e
            r = traceback.extract_tb(e.__traceback__)
            if result is not None:
                result.extend(r)
            else:
                result = r
            e = e.excs[0] if isinstance(e, ExceptionGroup) else None
        return result

class ExceptionGroupConstructionTests(ExceptionGroupTestUtils):

    def test_construction_simple(self):
        # create a simple exception group and check that
        # it is constructed as expected
        bind = functools.partial
        eg = self.newEG(
            [bind(self.newVE, 1),
             bind(self.newTE, int),
             bind(self.newVE, 2),
            ], message='simple EG')

        self.assertEqual(len(eg.excs), 3)
        self.assertMatchesTemplate(eg,
            [ValueError(1), TypeError(int), ValueError(2)])

        # check iteration
        self.assertEqual(list(eg), list(eg.excs))

        # check message
        self.assertEqual(eg.message, 'simple EG')
        self.assertEqual(eg.args, ('simple EG',))

        # check tracebacks
        for e in eg:
            expected = [
                'newEG',
                'newEG',
                'new'+ ''.join(filter(str.isupper, type(e).__name__)),
            ]
            etb = self.extract_traceback(e, eg)
            self.assertEqual(expected, [f.name for f in etb])

    def test_construction_nested(self):
        # create a nested exception group and check that
        # it is constructed as expected
        bind = functools.partial
        level1 = lambda i: self.newEG([
                bind(self.newVE, i),
                bind(self.newTE, int),
                bind(self.newVE, i+1),
            ])

        def raiseExc(e): raise e
        level2 = lambda i : self.newEG([
                bind(raiseExc, level1(i)),
                bind(raiseExc, level1(i+1)),
                bind(self.newVE, i+2),
            ])

        level3 = lambda i : self.newEG([
                bind(raiseExc, level2(i+1)),
                bind(self.newVE, i+2),
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
                'newEG',
                'newEG',
                'raiseExc',
                'newEG',
                'newEG',
                'raiseExc',
                'newEG',
                'newEG',
                'new' + ''.join(filter(str.isupper, type(e).__name__)),
            ]
            etb = self.extract_traceback(e, eg)
            self.assertEqual(expected, [f.name for f in etb])
        self.assertEqual([
            'newEG', 'newEG', 'raiseExc', 'newEG', 'newEG', 'newVE'],
            [f.name  for f in self.extract_traceback(all_excs[6], eg)])
        self.assertEqual(['newEG', 'newEG', 'newVE'],
            [f.name  for f in self.extract_traceback(all_excs[7], eg)])


class ExceptionGroupRenderTests(ExceptionGroupTestUtils):
    def test_simple(self):
        bind = functools.partial
        eg = self.newEG(
            [bind(self.newVE, 1),
             bind(self.newTE, int),
             bind(self.newVE, 2),
            ], message='hello world')

        expected = [  # (indent, exception) pairs
            (0, eg),
            (4, eg.excs[0]),
            (4, eg.excs[1]),
            (4, eg.excs[2]),
        ]

        self.check_summary_format_and_render(eg, expected)

    def check_summary_format_and_render(self, eg, expected):
        makeTE = traceback.TracebackException.from_exception

        # StackGroupSummary.extract
        summary = StackGroupSummary.extract(eg)
        self.assertEqual(len(expected), len(summary))
        self.assertEqual([e[0] for e in summary],
                         [e[0] for e in expected])
        self.assertEqual([e[1] for e in summary],
                         [makeTE(e) for e in [e[1] for e in expected]])

        # ExceptionGroup.format
        format_output = ExceptionGroup.format(eg)
        render_output = StringIO()
        ExceptionGroup.render(eg, file=render_output)

        self.assertIsInstance(format_output, list)
        self.assertIsInstance(render_output.getvalue(), str)
        self.assertEqual("".join(format_output).replace('\n',''),
                         render_output.getvalue().replace('\n',''))

    def test_stack_summary_nested(self):
        bind = functools.partial
        level1 = lambda i: self.newEG([
                bind(self.newVE, i),
                bind(self.newTE, int),
                bind(self.newVE, i+1),
            ])

        def raiseExc(e): raise e
        level2 = lambda i : self.newEG([
                bind(raiseExc, level1(i)),
                bind(raiseExc, level1(i+1)),
                bind(self.newVE, i+2),
            ])

        level3 = lambda i : self.newEG([
                bind(raiseExc, level2(i+1)),
                bind(self.newVE, i+2),
            ])
        eg = level3(5)

        expected = [  # (indent, exception) pairs
            (0, eg),
            (4, eg.excs[0]),
            (8, eg.excs[0].excs[0]),
            (12, eg.excs[0].excs[0].excs[0]),
            (12, eg.excs[0].excs[0].excs[1]),
            (12, eg.excs[0].excs[0].excs[2]),
            (8, eg.excs[0].excs[1]),
            (12, eg.excs[0].excs[1].excs[0]),
            (12, eg.excs[0].excs[1].excs[1]),
            (12, eg.excs[0].excs[1].excs[2]),
            (8, eg.excs[0].excs[2]),
            (4, eg.excs[1]),
        ]
        self.check_summary_format_and_render(eg, expected)

class ExceptionGroupSplitTests(ExceptionGroupTestUtils):

    def _split_exception_group(self, eg, types):
        """ Split an EG and do some sanity checks on the result """
        self.assertIsInstance(eg, ExceptionGroup)
        fnames = [t.name for t in traceback.extract_tb(eg.__traceback__)]
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

        for part in [match, rest]:
            self.assertEqual(eg.message, part.message)
            # check tracebacks
            for e in part:
                self.assertEqual(
                    self.extract_traceback(e, eg),
                    self.extract_traceback(e, part))

        return match, rest

    def test_split_nested(self):
        # create a nested exception group
        bind = functools.partial
        level1 = lambda i: self.newEG([
                bind(self.newVE, i),
                bind(self.newTE, int),
                bind(self.newVE, i+11),
            ], message='level1')

        def raiseExc(e): raise e
        level2 = lambda i : self.newEG([
                bind(raiseExc, level1(i)),
                bind(raiseExc, level1(i+22)),
                bind(self.newVE, i+33),
            ], message='level2')

        level3 = lambda i : self.newEG([
                bind(raiseExc, level2(i+44)),
                bind(self.newVE, i+55),
            ], message='split me')
        try:
            raise level3(6)
        except ExceptionGroup as e:
            eg = e

        fnames = ['test_split_nested', 'newEG']
        self.assertEqual(fnames,
            [t.name for t in traceback.extract_tb(eg.__traceback__)])

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
        level1 = lambda i: self.newEG([
                bind(self.newVE, i),
                bind(self.newTE, int),
                bind(self.newVE, i+10),
            ])

        def raiseExc(e): raise e
        level2 = lambda i : self.newEG([
                bind(raiseExc, level1(i)),
                bind(raiseExc, level1(i+20)),
                bind(self.newVE, i+30),
            ])

        level3 = lambda i : self.newEG([
                bind(raiseExc, level2(i+40)),
                bind(self.newVE, i+50),
            ], message='nested EG')
        try:
            raise level3(5)
        except ExceptionGroup as e:
            self.eg = e

        fnames = ['setUp', 'newEG']
        self.assertEqual(fnames,
            [t.name for t in traceback.extract_tb(self.eg.__traceback__)])

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


    def checkMatch(self, exc, template, orig_eg):
        self.assertMatchesTemplate(exc, template)
        for e in exc:
            f_data = lambda f: [f.name, f.lineno]
            new = list(map(f_data, self.extract_traceback(e, exc)))
            if e in orig_eg:
                old = list(map(f_data, self.extract_traceback(e, orig_eg)))
                self.assertSequenceEqual(old, new[-len(old):])

    class BaseHandler:
        def __init__(self):
            self.caught = None

        def __call__(self, eg):
            self.caught = eg
            return self.handle(eg)

    def apply_catcher(self, catch, handler_cls, eg):
        try:
            raised = None
            handler = handler_cls()
            with ExceptionGroup.catch(catch, handler):
                raise eg
        except ExceptionGroup as e:
            raised = e
        return handler.caught, raised

    def test_catch_handler_raises_nothing(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        class Handler(self.BaseHandler):
            def handle(self, eg):
                pass

         ######### Catch nothing:
        caught, raised = self.apply_catcher(SyntaxError, Handler, eg)
        self.checkMatch(raised, eg_template, eg)
        self.assertIsNone(caught)

        ######### Catch everything:
        error_types = (ValueError, TypeError)
        caught, raised = self.apply_catcher(error_types, Handler, eg)
        self.assertIsNone(raised)
        self.checkMatch(caught, eg_template, eg)

        ######### Catch TypeErrors:
        caught, raised = self.apply_catcher(TypeError, Handler, eg)
        self.checkMatch(raised, valueErrors_template, eg)
        self.checkMatch(caught, typeErrors_template, eg)

        ######### Catch ValueErrors:
        error_types = (ValueError, SyntaxError)
        caught, raised = self.apply_catcher(error_types, Handler, eg)
        self.checkMatch(raised, typeErrors_template, eg)
        self.checkMatch(caught, valueErrors_template, eg)

    def test_catch_handler_adds_new_exceptions(self):
        # create a nested exception group
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        class Handler(self.BaseHandler):
            def handle(self, eg):
                raise ExceptionGroup(
                      [ValueError('foo'),
                       ExceptionGroup(
                           [SyntaxError('bar'), ValueError('baz')])])

        newErrors_template = [
            ValueError('foo'), [SyntaxError('bar'), ValueError('baz')]]

        ######### Catch nothing:
        caught, raised = self.apply_catcher(SyntaxError, Handler, eg)
        self.checkMatch(raised, eg_template, eg)
        self.assertIsNone(caught)

        ######### Catch everything:
        error_types = (ValueError, TypeError)
        caught, raised = self.apply_catcher(error_types, Handler, eg)
        self.checkMatch(raised, newErrors_template, eg)
        self.checkMatch(caught, eg_template, eg)

        ######### Catch TypeErrors:
        caught, raised = self.apply_catcher(TypeError, Handler, eg)
        self.checkMatch(raised, [valueErrors_template, newErrors_template], eg)
        self.checkMatch(caught, typeErrors_template, eg)

        ######### Catch ValueErrors:
        caught, raised = self.apply_catcher((ValueError, OSError), Handler, eg)
        self.checkMatch(raised, [typeErrors_template, newErrors_template], eg)
        self.checkMatch(caught, valueErrors_template, eg)


    def test_catch_handler_reraise_all_matched(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        # There are two ways to do this
        class Handler1(self.BaseHandler):
            def handle(self, eg):
                return True

        class Handler2(self.BaseHandler):
            def handle(self, eg):
                raise eg

        for handler in [Handler1, Handler2]:
             ######### Catch nothing:
            caught, raised = self.apply_catcher(SyntaxError, handler, eg)
            # handler is never called
            self.checkMatch(raised, eg_template, eg)
            self.assertIsNone(caught)

            ######### Catch everything:
            error_types = (ValueError, TypeError)
            caught, raised = self.apply_catcher(error_types, handler, eg)
            self.checkMatch(raised, eg_template, eg)
            self.checkMatch(caught, eg_template, eg)

            ######### Catch TypeErrors:
            caught, raised = self.apply_catcher(TypeError, handler, eg)
            self.checkMatch(raised, eg_template, eg)
            self.checkMatch(caught, typeErrors_template, eg)

            ######### Catch ValueErrors:
            catch = (ValueError, SyntaxError)
            caught, raised = self.apply_catcher(catch, handler, eg)
            self.checkMatch(raised, eg_template, eg)
            self.checkMatch(caught, valueErrors_template, eg)

    def test_catch_handler_reraise_new_and_all_old(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        class Handler(self.BaseHandler):
            def handle(self, eg):
                raise ExceptionGroup(
                      [eg,
                       ValueError('foo'),
                       ExceptionGroup(
                           [SyntaxError('bar'), ValueError('baz')])])

        newErrors_template = [
            ValueError('foo'), [SyntaxError('bar'), ValueError('baz')]]

        ######### Catch TypeErrors:
        caught, raised = self.apply_catcher(TypeError, Handler, eg)
        self.checkMatch(raised, [eg_template, newErrors_template], eg)
        self.checkMatch(caught, typeErrors_template, eg)

        ######### Catch ValueErrors:
        caught, raised = self.apply_catcher(ValueError, Handler, eg)
        self.checkMatch(raised, [eg_template, newErrors_template], eg)
        self.checkMatch(caught, valueErrors_template, eg)

    def test_catch_handler_reraise_new_and_some_old(self):
        eg = self.eg
        eg_template = self.eg_template
        valueErrors_template = self.valueErrors_template
        typeErrors_template = self.typeErrors_template

        class Handler(self.BaseHandler):
            def handle(self, eg):
                raise ExceptionGroup(
                    [eg.excs[0],
                    ValueError('foo'),
                    ExceptionGroup(
                        [SyntaxError('bar'), ValueError('baz')])])

        newErrors_template = [
            ValueError('foo'), [SyntaxError('bar'), ValueError('baz')]]

        ######### Catch TypeErrors:
        caught, raised = self.apply_catcher(TypeError, Handler, eg)
        self.checkMatch(raised, [eg_template, newErrors_template], eg)
        self.checkMatch(caught, typeErrors_template, eg)

        ######### Catch ValueErrors:
        caught, raised = self.apply_catcher(ValueError, Handler, eg)
        # eg.excs[0] is reraised and eg.excs[1] is consumed
        self.checkMatch(raised, [[eg_template[0]], newErrors_template], eg)
        self.checkMatch(caught, valueErrors_template, eg)

if __name__ == '__main__':
    unittest.main()
