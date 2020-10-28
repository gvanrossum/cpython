import sys
import traceback
import types


def f(i=0): raise ValueError(f'bad value: f{i}')
def f1(): f(1)

def g(i=0): raise ValueError(f'bad value: g{i}')
def g1(): g(1)

def h(i=0): raise TypeError(f'bad type: h{i}')
def h1(): h(1)

def aggregator():
    excs = set()
    for c in (f, g):
        try:
            c()
        except Exception as e:
            excs.add(e)
    raise types.ExceptionGroup(excs)

def aggregator1():
    excs = set()
    for c in (f1, g1, aggregator):
        try:
            c()
        except (Exception, types.ExceptionGroup) as e:
            excs.add(e)
    eg = types.ExceptionGroup(excs)
    raise eg

def propagator():
    aggregator1()

def get_exception_group():
    try:
        propagator()
    except types.ExceptionGroup as e:
        return e

def handle_type_errors():
    try:
        propagator()
    except types.ExceptionGroup as e:
        TEs, rest = e.split(TypeError)
        return TEs, rest

def handle_value_errors():
    try:
        propagator()
    except types.ExceptionGroup as e:
        VEs, rest = e.split(ValueError)
        return VEs, rest


def main():
    print (">>>>>>>>>>>>>>>>>> get_exception_group <<<<<<<<<<<<<<<<<<<<")
    e = get_exception_group()
    types.ExceptionGroup.render(e)

    print (">>>>>>>>>>>>>>>>>> handle_type_errors <<<<<<<<<<<<<<<<<<<<")

    TEs, rest = handle_type_errors()
    print ("\n\n\n ------------- The split-off Type Errors:")
    types.ExceptionGroup.render(TEs)
    print ("\n\n\n ------------- The remaining unhandled:")
    types.ExceptionGroup.render(rest)

    print (">>>>>>>>>>>>>>>>>> handle_value_errors <<<<<<<<<<<<<<<<<<<<")
    VEs, rest = handle_value_errors()
    print ("\n\n\n ------------- The split-off Value Errors:")
    types.ExceptionGroup.render(VEs)
    print ("\n\n\n ------------- The remaining unhandled:")
    types.ExceptionGroup.render(rest)

if __name__ == '__main__':
    main()
