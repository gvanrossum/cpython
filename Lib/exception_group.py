
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

    def split(self, E):
        """Split an ExceptionGroup to extract exceptions matching E
        
        returns two new ExceptionGroups: match, rest of the exceptions of 
        self that match E and those that don't.
        match and rest have the same nested structure as self.
        E can be a type or tuple of types.
        """
        match, rest = [], []
        for e in self.excs:
            if isinstance(e, ExceptionGroup): # recurse
                e_match, e_rest = e.split(E)
                match.append(e_match)
                rest.append(e_rest)
            else:
                if isinstance(e, E):
                    match.append(e)
                    e_match, e_rest = e, None
                else:
                    rest.append(e)
        return (ExceptionGroup(match, tb=self.__traceback__),
                ExceptionGroup(rest, tb=self.__traceback__))

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
            match, rest = exc.split(self.types)

            if not match:
                # Let the interpreter reraise the exception
                return False

            new_exception_group = self.handler(match)
            if not new_exception_group and not rest:
                # handled and swallowed all exceptions
                return True

            if not new_exception_group:
                to_raise = rest
            elif not rest:
                to_raise = new_exception_group
            else:
                # merge rest and new_exceptions
                # keep the traceback from rest
                to_raise = ExceptionGroup([rest, new_exception_group])

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

