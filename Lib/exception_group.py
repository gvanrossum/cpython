
import sys


class TracebackGroup:
    def __init__(self, excs):
        # TODO: Oy, this needs to be a weak key dict, but exceptions
        # are not weakreffable.
        # TODO: what if e is unhashable?
        self.tb_next_map = {}
        for e in excs:
            if isinstance(e, ExceptionGroup):
                for e_ in e.excs:
                    self.tb_next_map[e_] = e_.__traceback__
            else:
                if e.__traceback__:
                    self.tb_next_map[e] = e.__traceback__.tb_next
                else:
                    self.tb_next_map[e] = None

class ExceptionGroup(BaseException):

    def __init__(self, excs, tb=None):
        self.excs = excs
        # self.__traceback__ is updated as usual, but self.__traceback_group__
        # is set when the exception group is created.
        # __traceback_group__ and __traceback__ combine to give the full path.
        self.__traceback__ = tb
        self.__traceback_group__ = TracebackGroup(self.excs)

    def _split_on_condition(self, condition):
        match, rest = [], []
        for e in self.excs:
            if isinstance(e, ExceptionGroup): # recurse
                e_match, e_rest = e._split_on_condition(condition)
                match.append(e_match)
                rest.append(e_rest)
            else:
                if condition(e):
                    match.append(e)
                    e_match, e_rest = e, None
                else:
                    rest.append(e)
        return (ExceptionGroup(match, tb=self.__traceback__),
                ExceptionGroup(rest, tb=self.__traceback__))

    def split(self, E):
        """ Split an ExceptionGroup to extract exceptions matching E

        returns two new ExceptionGroups: match, rest of the exceptions of
        self that match E and those that don't.
        match and rest have the same nested structure as self.
        E can be a type or tuple of types.
        """
        return self._split_on_condition(lambda e: isinstance(e, E))

    def subgroup(self, keep):
        """ Return a subgroup of self including only the exception in keep

        returns a new ExceptionGroups that contains only the exception in
        the sequence keep and preserves the internal structure of self.
        """
        match, _ = self._split_on_condition(lambda e: e in keep)
        return match

    def push_frame(self, frame):
        import types
        self.__traceback__ = types.TracebackType(
            self.__traceback__, frame, 0, 0)

    def extract_traceback(self, exc):
        """ returns the traceback of a single exception

        If exc is in this exception group, return its
        traceback as a list of frames. Otherwise, return None.

        Note: The frame where an exception was caught and
        rereaised as part of an exception group appreas twice.
        """
        if exc not in self:
            return None
        result = []
        tb = self.__traceback__
        while tb:
            result.append(tb.tb_frame)
            tb = tb.tb_next
        next_e = None
        for e in self.excs:
            if exc == e or (isinstance(e, ExceptionGroup) and exc in e):
                assert next_e is None
                next_e = e
        assert next_e is not None
        if isinstance(next_e, ExceptionGroup):
            result.extend(next_e.extract_traceback(exc))
        else:
            tb = next_e.__traceback__
            while tb:
                result.append(tb.tb_frame)
                tb = tb.tb_next
        return result

    @staticmethod
    def render(exc, tb=None, indent=0):
        print(exc)
        tb = tb or exc.__traceback__
        while tb and not isinstance(tb, TracebackGroup):
            print(' '*indent, tb.tb_frame)
            tb = tb.tb_next
        if isinstance(exc, ExceptionGroup):
            tbg = exc.__traceback_group__
            assert isinstance(tbg, TracebackGroup)
            indent += 4
            for e, t in tbg.tb_next_map.items():
                print('---------------------------------------')
                ExceptionGroup.render(e, t, indent)

    def __iter__(self):
        ''' iterate over the individual exceptions (flattens the tree) '''
        for e in self.excs:
            if isinstance(e, ExceptionGroup):
                for e_ in e:
                    yield e_
            else:
                yield e

    def __len__(self):
        l = 0
        for e in self.excs:
            if isinstance(e, ExceptionGroup):
                l += len(e)
            else:
                l += 1
        return l

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

        Any unmatched exceptions are raised at the end as another
        exception group
        """
        self.types = types
        self.handler = handler

    def __enter__(self):
        pass

    def __exit__(self, etype, exc, tb):
        if exc is not None and isinstance(exc, ExceptionGroup):
            match, unmatched = exc.split(self.types)

            if not match:
                # Let the interpreter reraise the exception
                return False

            handler_excs = self.handler(match)
            if handler_excs == match:
                # handler reraised all of the matched exceptions.
                # reraise exc as is.
                return False

            if not handler_excs and not unmatched:
                # handled and swallowed all exceptions
                # do not raise anything.
                return True

            if not unmatched:
                to_raise = handler_excs  # raise what handler returned
            elif not handler_excs:
                to_raise = unmatched       # raise the unmatched exceptions
            else:
                # to_keep: EG subgroup of exc with only those to reraise
                # (either not matched or reraised by handler)
                to_keep = exc.subgroup(
                    list(unmatched) + [e for e in handler_excs if e in match])
                # to_add: new exceptions raised by handler
                to_add = handler_excs.subgroup(
                    [e for e in handler_excs if e not in match])

                to_raise = ExceptionGroup([to_keep, to_add])

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

