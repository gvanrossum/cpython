"""Test for new PYC format"""

import dis
import marshal
from test import test_tools

test_tools.skip_if_missing("pyco")
with test_tools.imports_under_tool("pyco"):
    import pyco
    import updis


# TODO: Turn this into a TestCase
def main():
    source = "a = None"
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
    assert a is None
    print("Done: a =", a)


if __name__ == "__main__":
    main()
