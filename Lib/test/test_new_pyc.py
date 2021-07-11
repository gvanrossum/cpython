"""Test for new PYC format"""

import dis
import gc
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


class TestNewPycSpeed(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        print(f"{' ':25}{'load+exec':>15}{'steady state':>15}")
        for t, r in sorted(cls.results.items(), key=lambda kv: -kv[1][0]):
            print(f"{t:25}{r[0]:15.3f}{r[1]:15.3f}")
        print()
        cls.results = {}

    def setUp(self):
        while gc.collect():
            pass

    def do_test_speed(self, body, call=False):
        NUM_FUNCS = 100
        functions = [
            f"def f{num}(a, b):\n{body}"
            for num in range(NUM_FUNCS)
        ]
        if call:
            functions.extend([
                f"\nf{num}(0, 0)\n"
                for num in range(NUM_FUNCS)]
            )
        source = "\n\n".join(functions)
        self.do_test_speed_for_source(source)

    def do_test_speed_for_source(self, source):
        print()
        print(f"Starting speed test: {self._testMethodName}")
        def helper(data, label):
            timings = {}
            t0 = time.perf_counter()
            codes = []
            for _ in range(1000):
                code = marshal.loads(data)
                codes.append(code)
            t1 = time.perf_counter()
            print(f"{label} load: {t1-t0:.3f}")
            timings['load'] = t1-t0
            timings['execs'] = []
            for i in range(4):
                t3 = time.perf_counter()
                for code in codes:
                    exec(code, {})
                t4 = time.perf_counter()
                print(f"{label} exec #{i+1}: {t4-t3:.3f}")
                timings['execs'].append(t4-t3)
            print(f"       {label} total: {t4-t0:.3f}")
            return timings

        code = compile(source, "<old>", "exec")
        data = marshal.dumps(code)
        classic_timings = helper(data, "Classic")

        t0 = time.perf_counter()
        data = pyco.serialize_source(source, "<new>")
        t1 = time.perf_counter()
        print(f"PYCO: {t1-t0:.3f}")
        assert data.startswith(b"PYC.")
        new_timings = helper(data, "New PYC")

        if classic_timings and new_timings:
            def comparison(title, f):
                tc = f(classic_timings)
                tn = f(new_timings)
                print(f">> {title} ratio: {tc/tn:.2f} "
                      f"(new is {100*(tc/tn-1):.0f}% faster)")
                return tc/tn

            print("Classic-to-new comparison:")
            self.results[self._testMethodName.lstrip('test_speed_')] = [
                comparison('load+exec', lambda t: t['load'] + t['execs'][0]),
                comparison('steady state', lambda t: t['execs'][-1])
            ]
            print()

    def test_speed_few_locals(self):
        body = "    a, b = b, a\n"*100
        self.do_test_speed(body)

    def test_speed_few_locals_with_call(self):
        body = "    a, b = b, a\n"*100
        self.do_test_speed(body, call=True)

    def test_speed_many_locals(self):
        body = ["    a0, b0 = 1, 1"]
        for i in range(300):
            body.append(f"    a{i+1}, b{i+1} = b{i}, a{i}")
        self.do_test_speed('\n'.join(body))

    def test_speed_many_locals_with_call(self):
        body = ["    a0, b0 = 1, 1"]
        for i in range(100):
            body.append(f"    a{i+1}, b{i+1} = b{i}, a{i}")
        self.do_test_speed('\n'.join(body), call=True)

    def test_speed_many_constants(self):
        body = ["    a0, b0 = 1, 1"]
        for i in range(300):
            body.append(f"    a{i+1}, b{i+1} = b{i}+{i}, a{i}+{float(i)}")
        self.do_test_speed('\n'.join(body))

    def test_speed_many_globals(self):
        NUM_FUNCS = 100
        GLOBALS_PER_FUNC = 100
        source = []
        for f_index in range(NUM_FUNCS):
            for g_index in range(GLOBALS_PER_FUNC):
                source.append(f"a_{f_index}_{g_index} = 1")
            source.append(f"def f{f_index}():")
            source.append(f"    return 0+\\")
            for g_index in range(GLOBALS_PER_FUNC):
                source.append(f"        a_{f_index}_{g_index}+\\")
            source.append(f"        0")
        self.do_test_speed_for_source('\n'.join(source))


if __name__ == "__main__":
    unittest.main()
