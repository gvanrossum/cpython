
import sys


class TracebackGroup:
    def __init__(self, excs):
        self.tb_next_map = {} # exception id to tb
        for e in excs:
            if isinstance(e, ExceptionGroup):
                for e_ in e.excs:
                    # TODO: what if e_ is an EG? This looks wrong.
                    self.tb_next_map[id(e_)] = e_.__traceback__
            else:
                if e.__traceback__:
                    # TODO: is tb_next always correct? explain why.
                    self.tb_next_map[id(e)] = e.__traceback__.tb_next
                else:
                    self.tb_next_map[id(e)] = None

class ExceptionGroup(BaseException):

    def __init__(self, excs, *, msg=None, tb=None):
        """ Construct a new ExceptionGroup

        excs: sequence of exceptions
        tb [optional]: the __traceback__ of this exception group.
        Typically set when this ExceptionGroup is derived from another.
        """
        self.excs = excs
        self.msg = msg
        # self.__traceback__ is updated as usual, but self.__traceback_group__
        # is set when the exception group is created.
        # __traceback_group__ and __traceback__ combine to give the full path.
        self.__traceback__ = tb
        self.__traceback_group__ = TracebackGroup(self.excs)

    def project(self, condition, with_complement=False):
        """ Split an ExceptionGroup based on an exception predicate

        returns a new ExceptionGroup, match, of the exceptions of self
        for which condition returns True. If with_complement is True,
        returns another ExceptionGroup for the exception for which
        condition returns False.
        match and rest have the same nested structure as self, but empty
        sub-exceptions are not included. They have the same msg,
        __traceback__, __cause__ and __context__ fields as self.

        condition: BaseException --> Boolean
        with_complement: Bool  If True, construct also an EG of the non-matches
        """
        match = []
        rest = [] if with_complement else None
        for e in self.excs:
            if isinstance(e, ExceptionGroup): # recurse
                e_match, e_rest = e.project(
                    condition, with_complement=with_complement)
                if not e_match.is_empty():
                    match.append(e_match)
                if with_complement and not e_rest.is_empty():
                    rest.append(e_rest)
            else:
                if condition(e):
                    match.append(e)
                elif with_complement:
                    rest.append(e)

        match_exc = ExceptionGroup(match, tb=self.__traceback__)
        def copy_metadata(src, target):
            target.msg = src.msg
            target.__context__ = src.__context__
            target.__cause__ = src.__cause__
        copy_metadata(self, match_exc)
        if with_complement:
            rest_exc = ExceptionGroup(rest, tb=self.__traceback__)
            copy_metadata(self, rest_exc)
        else:
            rest_exc = None
        return match_exc, rest_exc

    def split(self, type):
        """ Split an ExceptionGroup to extract exceptions of type E

        type: An exception type
        """
        return self.project(
            lambda e: isinstance(e, type),
            with_complement=True)

    def subgroup(self, keep):
        """ Split an ExceptionGroup to extract only exceptions in keep

        keep: List[BaseException]
        """
        match, _ = self.project(lambda e: e in keep)
        return match

    def extract_traceback(self, exc):
        """ returns the traceback of a single exception

        If exc is in this exception group, return its
        traceback as a list of frames. Otherwise, return None.
        """
        # TODO: integrate into traceback.py style
        # TODO: return a traceback.StackSummary ?
        if exc not in self:
            return None
        result = []
        e = self.subgroup([exc])
        while e is not None and\
            (not isinstance(e, ExceptionGroup) or not e.is_empty()):

            tb = e.__traceback__
            while tb is not None:
                result.append(tb.tb_frame)
                tb = tb.tb_next
            if isinstance(e, ExceptionGroup):
                assert len(e.excs) == 1 and exc in e
                e = e.excs[0]
            else:
                assert e is exc
                e = None
        return result

    @staticmethod
    def render(exc, tb=None, indent=0):
        # TODO: integrate into traceback.py style
        output = []
        output.append(f"{exc}")
        tb = tb or exc.__traceback__
        while tb is not None and not isinstance(tb, TracebackGroup):
            output.append(f"{' '*indent} {tb.tb_frame}")
            tb = tb.tb_next
        if isinstance(exc, ExceptionGroup):
            tbg = exc.__traceback_group__
            assert isinstance(tbg, TracebackGroup)
            indent += 4
            for e in exc.excs:
                t = tbg.tb_next_map[id(e)]
                output.append('---------------------------------------')
                output.extend(ExceptionGroup.render(e, t, indent))
        for l in output:
            print(l)
        return output

    def __iter__(self):
        ''' iterate over the individual exceptions (flattens the tree) '''
        for e in self.excs:
            if isinstance(e, ExceptionGroup):
                for e_ in e:
                    yield e_
            else:
                yield e

    def is_empty(self):
        return not any(self)

    def __repr__(self):
        return f"ExceptionGroup({self.excs})"

    @staticmethod
    def catch(types, handler):
        return ExceptionGroupCatcher(types, handler)

class ExceptionGroupCatcher:
    """ Based on trio.MultiErrorCatcher """

    def __init__(self, types, handler):
        """ Context manager to catch and handle ExceptionGroups

        types: the exception types that this handler is interested in
        handler: a function that takes an ExceptionGroup of the
        matched type and does something with them

        Any rest exceptions are raised at the end as another
        exception group
        """
        self.types = types
        self.handler = handler

    def __enter__(self):
        pass

    def __exit__(self, etype, exc, tb):
        if exc is not None and isinstance(exc, ExceptionGroup):
            match, rest = exc.split(self.types)

            if match.is_empty():
                # Let the interpreter reraise the exception
                return False

            handler_excs = self.handler(match)
            if handler_excs is match:
                # handler reraised all of the matched exceptions.
                # reraise exc as is.
                return False

            if handler_excs is None or handler_excs.is_empty():
                if rest.is_empty():
                    # handled and swallowed all exceptions
                    # do not raise anything.
                    return True
                else:
                    # raise the rest exceptions
                    to_raise = rest
            elif rest.is_empty():
                to_raise = handler_excs  # raise what handler returned
            else:
                # Merge handler's exceptions with rest
                # to_keep: EG subgroup of exc with only those to reraise
                # (either not matched or reraised by handler)
                to_keep = exc.subgroup(
                    list(rest) + [e for e in handler_excs if e in match])
                # to_add: new exceptions raised by handler
                to_add = handler_excs.subgroup(
                    [e for e in handler_excs if e not in match])
                if not to_add.is_empty():
                    to_raise = ExceptionGroup([to_keep, to_add])
                    to_raise.msg = exc.msg
                else:
                    to_raise = to_keep

            # When we raise to_raise, Python will unconditionally blow
            # away its __context__ attribute and replace it with the original
            # exc we caught. So after we raise it, we have to pause it while
            # it's in flight to put the correct __context__ back.
            old_context = to_raise.__context__
            try:
                raise to_raise
            finally:
                _, value, _ = sys.exc_info()
                assert value is to_raise
                value.__context__ = old_context

