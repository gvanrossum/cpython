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

    def do_test_speed(self, body, test_name, call=False):
        functions = [
            f"def f{num}(a, b):\n{body}"
            for num in range(100)
        ]
        if call:
            functions.extend([
                f"\nf{num}({num}, {num+1})\n"
                for num in range(100)]
            )
        source = "\n\n".join(functions)
        print(f"Starting {test_name} speed test")

        def helper(data, label):
            t0 = time.perf_counter()
            codes = []
            for _ in range(20000):
                code = marshal.loads(data)
                codes.append(code)
            t1 = time.perf_counter()
            print(f"{label} load: {t1-t0:.3f}")
            t2 = time.perf_counter()
            for code in codes:
                exec(code, {})
            t3 = time.perf_counter()
            print(f"{label} first exec: {t3-t2:.3f}")
            for code in codes:
                exec(code, {})
            t4 = time.perf_counter()
            print(f"{label} second exec: {t4-t3:.3f}")
            print(f"       {label} total: {t4-t0:.3f}")
            return t3 - t0

        code = compile(source, "<old>", "exec")
        data = marshal.dumps(code)
        tc = helper(data, "Classic")

        data = pyco.serialize_source(source, "<new>")
        assert data.startswith(b"PYC.")
        tn = helper(data, "New PYC")
        if tc and tn:
            print(f"Classic-to-new ratio: {tc/tn:.2f} (new is {100*(tc/tn-1):.0f}% faster)")

    def test_speed_few_locals(self):
        body = "    a, b = b, a\n"*100
        self.do_test_speed(body, "few_locals")

    def test_speed_many_locals(self):
        body = ["    a0, b0 = 1, 1"]
        for i in range(100):
            body.append(f"    a{i+1}, b{i+1} = b{i}, a{i}")
        self.do_test_speed('\n'.join(body), "many_locals")

    def test_speed_many_locals_with_call(self):
        body = ["    a0, b0 = 1, 1"]
        for i in range(100):
            body.append(f"    a{i+1}, b{i+1} = b{i}, a{i}")
        self.do_test_speed('\n'.join(body), "many_locals_with_call", call=True)

if __name__ == "__main__":
    unittest.main()
