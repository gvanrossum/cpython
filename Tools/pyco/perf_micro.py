
import csv
import gc
import itertools
from collections import namedtuple

from test.test_new_pyc import speed_comparison

SpeedTestParams = namedtuple(
    'SpeedTestParams',
    ['num_funcs', 'func_length', 'num_vars',
     'is_locals', 'is_unique_names', 'is_vary_constants', 'is_call'])

class SpeedTestBuilder:
    def __init__(self, params: SpeedTestParams):
        self.params = params

    def get_test_name(self):
        p = self.params
        nfuncs = p.num_funcs
        nvars = p.num_vars
        scope = "locals" if p.is_locals else "globals"
        shared = "unique" if p.is_unique_names else "shared"
        is_call = " is_call" if p.is_call else ""
        consts = " consts" if p.is_vary_constants else ""
        return f" {shared}{is_call} {scope}{consts} {nfuncs} funcs, {nvars} vars"

    def function_template(self):
        p = self.params
        FUNC_INDEX = "FUNC_INDEX" if p.is_unique_names else ""
        # variables used in the function:
        vars = [f"v_{FUNC_INDEX}_{i}" for i in range(p.num_vars)]
        init_vars = [f"{var} = {i if p.is_vary_constants else 1}"
                     for (i, var) in enumerate(vars)]

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
        body = body[:p.func_length-1]
        body.append(f"        0")

        source.extend(body)
        if p.is_call:
            source.append("f_FUNC_INDEX()")
        return '\n'.join(source)

    def get_source(self):
        template = self.function_template()
        source = [f"# {self.get_test_name()}"]
        for i in range(self.params.num_funcs):
            source.append(template.replace("FUNC_INDEX", str(i)))
        return '\n'.join(source)

if __name__ == '__main__':
    results = {}
    for params in itertools.product(
        [100],          # num_funcs
        [100],          # func_length
        [10, 50],       # num_vars
        [True, False],  # is_locals
        [True, False],  # is_unique_names
        [True, False],  # is_vary_constants
        [False],  # is_call
    ):
        p = SpeedTestParams(*params)
        while gc.collect():
            pass
        builder = SpeedTestBuilder(p)
        results[p] = speed_comparison(builder.get_source(), builder.get_test_name())

    with open('perf_micro.csv', 'w', newline='') as f:
        writer = None
        for p, r in results.items():
            if writer is None:
                fieldnames = list(p._asdict().keys())+list(r.keys())
                csv.writer(f).writerow(fieldnames)
                writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(p._asdict()|r)
