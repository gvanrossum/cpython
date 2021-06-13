"""Test for new PYC format"""

import dis
import marshal
import unittest

from test import test_tools

test_tools.skip_if_missing("pyco")
with test_tools.imports_under_tool("pyco"):
    import pyco
    import updis


class TestNewPyc(unittest.TestCase):
    def test_basic(self):
        value = (1, 2, 3, 3.14, 1+2j, "ab", b"cd", None, False, True, ...)
        source = f"a = {value!r}"
        builder = pyco.build_source(source)
        pyco.report(builder)
        data = pyco.serialize_source(source)
        print(repr(data))
        code = marshal.loads(data)
        # code = compile(source, "", "exec")
        print(code)
        print(code.co_code)
        dis.dis(code.co_code)
        ns = {}
        exec(code, ns)
        a = ns["a"]
        assert a == value, (a, value)
        for x, y in zip(a, value):
            assert type(x) is type(y), (x, y)
        print("Done: a =", a)


if __name__ == "__main__":
    unittest.main()
