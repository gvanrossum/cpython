"""Test for new PYC format"""

import dis
import marshal
import time
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
        source = "def f(a, b):\n    return a + b"
        builder = pyco.build_source(source)
        pyco.report(builder)
        data = pyco.serialize_source(source)
        code = marshal.loads(data)
        ns = {}
        exec(code, ns)
        f = ns["f"]
        print("Disassembly of", f)
        dis.dis(f, depth=0)
        # breakpoint()
        assert f(1, 10) == 11
        assert f(a=1, b=10) == 11

    def test_speed(self):
        body = "    a, b = b, a\n"*100
        functions = [
            f"def f{num}(a, b):\n{body}"
            for num in range(100)
        ]
        source = "\n\n".join(functions)
        print("Starting speed test")

        def helper(data, label):
            t0 = time.time()
            codes = []
            for _ in range(5000):
                code = marshal.loads(data)
                codes.append(code)
            t1 = time.time()
            print(f"{label} load: {t1-t0:.3f}")
            t2 = time.time()
            for code in codes:
                exec(code, {})
            t3 = time.time()
            print(f"{label} exec: {t3-t2:.3f}")
            print(f"       {label} total: {t3-t0:.3f}")
            return t3 - t0

        code = compile(source, "<old>", "exec")
        data = marshal.dumps(code)
        tc = helper(data, "Classic")

        data = pyco.serialize_source(source, "<new>")
        assert data.startswith(b"PYC.")
        tn = helper(data, "New PYC")
        if tc and tn:
            print(f"Classic-to-new ratio: {tc/tn:.2f} (new is {100*(tc/tn-1):.0f}% faster)")


if __name__ == "__main__":
    unittest.main()
