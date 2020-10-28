import sys
import traceback
import exception_group


def f(i=0): raise ValueError(f'bad value: f{i}')
def f1(): f(1)

def g(i=0): raise ValueError(f'bad value: g{i}')
def g1(): g(1)

def h(i=0): raise TypeError(f'bad type: h{i}')
def h1(): h(1)

def aggregator():
    excs = set()
    for c in (f, g, h):
        try:
            c()
        except Exception as e:
            excs.add(e)
    raise exception_group.ExceptionGroup(excs)

def aggregator1():
    excs = set()
    for c in (f1, g1, h1, aggregator):
        try:
            c()
        except (Exception, exception_group.ExceptionGroup) as e:
            excs.add(e)
    eg = exception_group.ExceptionGroup(excs)
    raise eg

def propagator():
    aggregator1()

def get_exception_group():
    try:
        propagator()
    except exception_group.ExceptionGroup as e:
        return e

def handle_type_errors():
    try:
        propagator()
    except exception_group.ExceptionGroup as e:
        TEs, rest = e.split(TypeError)
        return TEs, rest

def handle_value_errors():
    try:
        propagator()
    except exception_group.ExceptionGroup as e:
        VEs, rest = e.split(ValueError)
        return VEs, rest


def main():
    print ("\n\n>>>>>>>>>>>>>>>>>> get_exception_group <<<<<<<<<<<<<<<<<<<<")
    e = get_exception_group()
    exception_group.ExceptionGroup.render(e)

    print ("\n\n>>>>>>>>>>>>>>>>>> handle_type_errors <<<<<<<<<<<<<<<<<<<<")

    TEs, rest = handle_type_errors()
    print ("\n ------------- The split-off Type Errors:")
    exception_group.ExceptionGroup.render(TEs)
    print ("\n\n\n ------------- The remaining unhandled:")
    exception_group.ExceptionGroup.render(rest)

    print ("\n\n>>>>>>>>>>>>>>>>>> handle_value_errors <<<<<<<<<<<<<<<<<<<<")
    VEs, rest = handle_value_errors()
    print ("\n ------------- The split-off Value Errors:")
    exception_group.ExceptionGroup.render(VEs)
    print ("\n ------------- The remaining unhandled:")
    exception_group.ExceptionGroup.render(rest)

if __name__ == '__main__':
    main()
