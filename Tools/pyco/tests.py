import dis
import glob
import os
import sys


from pyco import Builder, add_everything
from unpyc import PycFile


def expand_args(filenames):
    for filename in filenames:
        filename = os.path.expanduser(filename)
        if "*" in filename and sys.platform == "win32":
            for fn in glob.glob(filename, recursive=True):
                yield fn
        elif os.path.isdir(filename):
            for root, _, files in os.walk(filename):
                for fn in files:
                    if fn.endswith(".py"):
                        yield os.path.join(root, fn)
        else:
            yield filename


def main():
    for filename in expand_args(sys.argv[1:]):
        ## print()
        print("=====", filename, "=====")
        with open(filename, "rb") as f:
            try:
                code = compile(f.read(), filename, "exec")
            except SyntaxError as err:
                print(err)
                continue
        builder = Builder()
        add_everything(builder, code)
        builder.lock()
        try:
            data = builder.get_bytes()
        except RuntimeError as err:
            print(f"{filename}: {err}")
            continue
        pyc = PycFile(data)
        pyc.load()
        pyc.report()
        for i in range(len(pyc.code_offsets)):
            print("Code object", i)
            code = pyc.get_code(i)
            dis.dis(code)


if __name__ == "__main__":
    main()
