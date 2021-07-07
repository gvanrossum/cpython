"""Add extra opcodes directly to dis/opcode .

Opcodes that already exist must match the definitions here.
"""

import dis


def def_op(name: str, op: int) -> int:
    if name in dis.opmap:
        assert dis.opmap[name] == op, (name, op, dis.opmap[name])
        assert dis.opname[op] == name, (name, op, dis.opname[op])
        return op
    dis.opname[op] = name
    dis.opmap[name] = op
    return op


lastop = 169
LAZY_LOAD_CONSTANT = def_op("LAZY_LOAD_CONSTANT", lastop := lastop + 1)
MAKE_STRING = def_op("MAKE_STRING", lastop := lastop + 1)
MAKE_INT = def_op("MAKE_INT", lastop := lastop + 1)
MAKE_LONG = def_op("MAKE_LONG", lastop := lastop + 1)
MAKE_FLOAT = def_op("MAKE_FLOAT", lastop := lastop + 1)
MAKE_COMPLEX = def_op("MAKE_COMPLEX", lastop := lastop + 1)
MAKE_FROZEN_SET = def_op("MAKE_FROZEN_SET", lastop := lastop + 1)
MAKE_CODE_OBJECT = def_op("MAKE_CODE_OBJECT", lastop := lastop + 1)
MAKE_BYTES = def_op("MAKE_BYTES", lastop := lastop + 1)
LOAD_COMMON_CONSTANT = def_op(
    "LOAD_COMMON_CONSTANT", lastop := lastop + 1
)  # None, False, True
RETURN_CONSTANT = def_op("RETURN_CONSTANT", lastop := lastop + 1)

if LAZY_LOAD_CONSTANT in dis.hasconst:
    dis.hasconst.remove(LAZY_LOAD_CONSTANT)

del lastop, def_op

CO_FAST_LOCAL = 0x20
CO_FAST_FREE = 0x80
CO_FAST_CELL = 0x40
