import csv
import gc
import itertools
import marshal
import time

from argparse import ArgumentParser
from collections import namedtuple
from test import test_tools

test_tools.skip_if_missing("pyco")
with test_tools.imports_under_tool("pyco"):
    import pyco


_LOAD_EXEC = "load+exec"
_STEADY_STATE = "steady-state"


def speed_comparison(source: str, test_name: str):
    print()
    print(f"Starting speed test: {test_name}")

    def helper(data, label):
        timings = {}
        t0 = time.perf_counter()
        codes = []
        for _ in range(1000):
            code = marshal.loads(data)
            codes.append(code)
        t1 = time.perf_counter()
        print(f"{label} load: {t1-t0:.3f}")
        timings["load"] = t1 - t0
        timings["execs"] = []
        for i in range(4):
            t3 = time.perf_counter()
            for code in codes:
                exec(code, {})
            t4 = time.perf_counter()
            print(f"{label} exec #{i+1}: {t4-t3:.3f}")
            timings["execs"].append(t4 - t3)
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
            print(
                f">> {title} ratio: {tn/tc:.2f} "
                f"(new is {100*(tn/tc-1):.0f}% faster)"
            )
            return tn / tc

        print("Classic-to-new comparison:")

        def load_plus_exec_time(t):
            return t["load"] + t["execs"][0]

        def last_exec_time(t):
            return t["execs"][-1]

        result = {
            _LOAD_EXEC: comparison(_LOAD_EXEC, load_plus_exec_time),
            _STEADY_STATE: comparison(_STEADY_STATE, last_exec_time),
        }
        print()
        return result


SpeedTestParams = namedtuple(
    "SpeedTestParams",
    [
        "num_funcs",
        "func_length",
        "num_vars",
        "is_locals",
        "is_unique_names",
        "is_vary_constants",
        "is_call",
    ],
)


def test_name(p: SpeedTestParams):
    nfuncs = p.num_funcs
    nvars = p.num_vars
    scope = "locals " if p.is_locals else "globals"
    shared = "unique" if p.is_unique_names else "shared"
    is_call = "call" if p.is_call else ""
    consts = "consts" if p.is_vary_constants else ""
    return (
        f" {shared:>6}{is_call:>5}{scope:>7}{consts:>7}"
        f" {nfuncs:>4} funcs, {nvars:>4} vars"
    )


class SpeedTestBuilder:
    def __init__(self, params: SpeedTestParams):
        self.params = params

    def function_template(self):
        p = self.params
        FUNC_INDEX = "FUNC_INDEX" if p.is_unique_names else ""
        # variables used in the function:
        vars = [f"v_{FUNC_INDEX}_{i}" for i in range(p.num_vars)]
        if p.is_vary_constants:
            init_vars = [f"{var} = {i}" for (i, var) in enumerate(vars)]
        else:
            init_vars = [f"{var} = 1" for var in vars]

        source = []
        if not p.is_locals:
            # define globals in module scope:
            source.extend(init_vars)
        # define the function
        source.append(f"def f_FUNC_INDEX():")
        if p.is_locals:
            # define locals in the function:
            source.extend(f"    {l}" for l in init_vars)

        body = []
        assert p.func_length > 1
        body.append(f"    return 0+\\")
        while len(body) < p.func_length:
            body.extend(f"        {var}+ \\" for var in vars)
        body = body[: p.func_length - 1]
        body.append(f"        0")

        source.extend(body)
        if p.is_call:
            source.append("f_FUNC_INDEX()")
        return "\n".join(source)

    def get_source(self):
        template = self.function_template()
        source = [f"# {test_name(self.params)}"]
        for i in range(self.params.num_funcs):
            source.append(template.replace("FUNC_INDEX", str(i)))
        return "\n".join(source)


def run_tests():
    results = {}
    for params in itertools.product(
        [100],  # num_funcs
        [100],  # func_length
        [10, 100],  # num_vars
        [True, False],  # is_locals
        [True, False],  # is_unique_names
        [True, False],  # is_vary_constants
        [False],  # is_call (True chokes on a memory leak?)
    ):
        p = SpeedTestParams(*params)
        while gc.collect():
            pass
        builder = SpeedTestBuilder(p)
        results[p] = speed_comparison(builder.get_source(), test_name(p))
    return results


def write_csv(results: dict, filename: str):
    with open(filename, "w", newline="") as f:
        writer = None
        for p, r in results.items():
            if writer is None:
                fieldnames = list(p._asdict().keys()) + list(r.keys())
                csv.writer(f).writerow(fieldnames)
                writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(p._asdict() | r)
    print(f"Results were written to {filename}")


def print_summary(results: dict):
    print(f"{' ':50}{_LOAD_EXEC:>15}{'steady state':>15}")
    for p, r in sorted(results.items(), key=lambda kv: -kv[1][_LOAD_EXEC]):
        name = test_name(p)
        print(f"{name:50}{r[_LOAD_EXEC]:15.3f}{r[_STEADY_STATE]:15.3f}")
    print()


if __name__ == "__main__":
    parser = ArgumentParser(description="Run pyco perf micro-benchmarks.")
    parser.add_argument('-f', help='file for csv output')
    args = parser.parse_args()
    filename = getattr(args, 'f', None)

    results = run_tests()
    if filename is not None:
        write_csv(results, filename)
    print_summary(results)
