


class TracebackGroup:
    def __init__(self, excs):
        # TODO: Oy, this needs to be a weak key dict, but exceptions
        # are not weakreffable.
        self.tb_next_map = {}
        for e in excs:
            if isinstance(e, ExceptionGroup):
                for e_ in e.excs:
                    self.tb_next_map[e_] = e_.__traceback__
            else:
                self.tb_next_map[e] = e.__traceback__.tb_next

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

    def __repr__(self):
        return f"ExceptionGroup({self.excs})"