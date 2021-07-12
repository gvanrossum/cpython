"""Test for new PYC format"""

import dis
import marshal
import unittest

from test import test_tools

test_tools.skip_if_missing("pyco")
with test_tools.imports_under_tool("pyco"):
    import pyco
    import updis


def compare(a, b):
    if isinstance(a, tuple):
        for x, y in zip(a, b):
            compare(x, y)
    assert a == b, (a, b)
    assert type(a) == type(b), (a, b)


class TestNewPyc(unittest.TestCase):
    def test_basic(self):
        values = [
            0,
            2,
            300,
            99999,
            -99999,
            3.14,
            -2.7,
            1+2j,
            "abc",
            b"cde",
            None,
            False,
            True,
            ...,
            (),
            (0, 1, "aa", "bb"),
            (1, 2, (3, 4), 5, 6),
        ]
        for value in values:
            print("==========", value, "==========")
            source = f"a = {value!r}"
            builder = pyco.build_source(source)
            pyco.report(builder)
            data = pyco.serialize_source(source)
            # print(repr(data))
            code = marshal.loads(data)
            # print(code)
            # print(code.co_code)
            # dis.dis(code.co_code)
            ns = {}
            exec(code, ns)
            a = ns["a"]
            compare(a, value)
            print("Match:", source)
        print("Done")

    def test_function(self):
        source = "def f(a, b):\n    print(a, b)\n    return a + b\n"
        builder = pyco.build_source(source)
        pyco.report(builder)
        data = pyco.serialize_source(source)
        code = marshal.loads(data)
        ns = {}
        exec(code, ns)
        f = ns["f"]
        print("Disassembly of", f)
        dis.dis(f, depth=0)
        assert f(1, 10) == 11
        assert f(a=1, b=10) == 11

    def test_consts(self):
        NUM_FUNCS = 2
        srcs = ["hello = ('hello', 42)\n"]
        for num in range(NUM_FUNCS):
            srcs.append(f"def f{num}():\n    return ({num}, 'hello {num}')\n")
        source = "\n".join(srcs)
        builder = pyco.build_source(source)
        pyco.report(builder)
        data = pyco.serialize_source(source)
        code = marshal.loads(data)
        ns = {}
        exec(code, ns)
        for num in range(NUM_FUNCS):
            fco = ns[f"f{num}"]
            assert (num, f"hello {num}") in fco.__code__.co_consts


if __name__ == "__main__":
    unittest.main()
