"""Compiler to create new-style PYC files

See https://github.com/faster-cpython/ideas/issues/32
and https://github.com/python/peps/compare/master...markshannon:pep-mappable-pyc-file

This uses match/case (PEP 634) and hence needs Python 3.10.

This doesn't follow the format proposed there exactly; in particular,
I had to add a Blob section so MAKE_LONG, MAKE_FLOAT and MAKE_BYTES (new!)
can use an index instead of having to encode an offset using EXTENDED_ARG.

Also, I gave up on the metadata section for now.
I'm assuming it won't make that much of a difference for a prototype.

BTW, the way I intend to use the prototype is as follows:

- Add the extra fields to PyCode_Object
- Implement the new bytecodes in ceval.c
- Add a hack to the unmarshal code (marshal.loads(), used by importlib)
  to recognize the new format as a new data type and then just stop,
  returning the entire blob.
- *Manually* generate pyc files (essentially using this module) and test.

We can then assess the performance and see where to go from there.
"""

from __future__ import annotations  # I have forward references

import builtins
import dis  # Where opname/opmap live, according to the docs
import io
import struct
import sys
import types

from collections import OrderedDict
from inspect import CO_OPTIMIZED, CO_NEWLOCALS
from typing import (
    Iterable,
    cast,
    Iterator,
    Protocol,
    TypeAlias,
    TypeVar,
    MutableMapping,
    runtime_checkable,
)

# VS Code (PyLance) doesn't find updis.py, even though it's adjacent
try:
    from updis import *  # type: ignore
except ImportError:
    from .updis import *

FUNCTION_FLAGS = CO_OPTIMIZED | CO_NEWLOCALS

UNARY_NEGATIVE = dis.opmap["UNARY_NEGATIVE"]
BUILD_TUPLE = dis.opmap["BUILD_TUPLE"]
BUILD_SET = dis.opmap["BUILD_SET"]
EXTENDED_ARG = dis.opmap["EXTENDED_ARG"]
LOAD_CONST = dis.opmap["LOAD_CONST"]


def encode_varint(i: int) -> bytes:
    """LEB128 encoding (https://en.wikipedia.org/wiki/LEB128)"""
    if i == 0:
        return b"\x00"
    assert i > 0
    b = bytearray()
    while i:
        bits = i & 127
        i = i >> 7
        if i:
            bits |= 128  # All but the final byte have the high bit set
        b.append(bits)
    return bytes(b)


def encode_signed_varint(i: int) -> bytes:
    """Not LEB128; instead we put the sign bit in the lowest bit"""
    sign_bit = i < 0
    return encode_varint(abs(i) << 1 | sign_bit)


def encode_float(x: float) -> bytes:
    return struct.pack("<d", x)


def decode_varint(data: bytes) -> tuple[int, int]:
    result = 0
    shift = 0
    pos = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
    return result, pos


S = TypeVar("S", covariant=True)


class HasValue(Protocol[S]):
    value: S


class Thing(HasValue[S]):
    def __eq__(self, other: Thing[S]) -> bool:
        return self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def key(self) -> object:
        this = self.value
        return (type(self), type(this), this)


class LongInt(Thing[int]):
    def __init__(self, value: int):
        self.value = value

    def get_bytes(self) -> bytes:
        return encode_signed_varint(self.value)


class Float(Thing[float]):
    def __init__(self, value: float):
        self.value = value

    def get_bytes(self) -> bytes:
        return encode_float(self.value)


class Bytes(Thing[bytes]):
    def __init__(self, value: bytes):
        self.value = value

    def get_bytes(self) -> bytes:
        return encode_varint(len(self.value)) + self.value


BlobConstant = LongInt | Float | Bytes


class Redirect(Thing[tuple[type, int]]):
    def __init__(self, target: int):
        self.value = (type(self), id(self))  # should not be equal to anything else
        self.target = target

    def get_bytes(self) -> bytes:
        raise ValueError("should not be called")


class String(Thing[str]):
    def __init__(self, value: str):
        assert value is not None
        self.value = value

    def get_bytes(self) -> bytes:
        b = self.value.encode("utf-8", errors="surrogatepass")
        # Encode number of bytes, not code points or characters
        return encode_varint(len(b)) + b


ConstantValue: TypeAlias = (
    None | complex | bytes | str | tuple[object, ...] | frozenset[object]
)


class ComplexConstant(Thing[ConstantValue]):
    """Constant represented by code."""

    def __init__(self, value: ConstantValue, builder: Builder):
        self.value = value
        self.builder = builder
        self.instructions: list[tuple[int, int]] = []
        self.stacksize = 0
        self.max_stacksize = 0
        self.index = -1
        self.data = None

    def set_index(self, index: int) -> None:
        # Needed because RETURN_CONSTANT needs to know its own index
        self.index = index
        self.generate(self.value)
        self.emit(RETURN_CONSTANT, self.index, 0)

    def emit(self, opcode: int, oparg: int, stackeffect: int):
        self.instructions.append((opcode, oparg))
        self.stacksize += stackeffect  # Maybe a decrease
        self.max_stacksize = max(self.max_stacksize, self.stacksize)

    def generate(self, value: ConstantValue):
        match value:
            case None:
                self.emit(LOAD_COMMON_CONSTANT, 0, 1)
            case False | True as x:
                self.emit(LOAD_COMMON_CONSTANT, int(x) + 1, 1)
            case builtins.Ellipsis:
                self.emit(LOAD_COMMON_CONSTANT, 3, 1)
            case int(i) if 0 <= i < 1<<16:
                self.emit(MAKE_INT, i, 1)
            case int(i) if -256 <= i < 0:
                self.emit(MAKE_INT, -i, 1)
                self.emit(UNARY_NEGATIVE, 0, 0)
            case int(i):
                self.emit(MAKE_LONG, self.builder.add_long(i), 1)
            case float(x):
                self.emit(MAKE_FLOAT, self.builder.add_float(x), 1)
            case complex(real=re, imag=im):
                self.emit(MAKE_FLOAT, self.builder.add_float(re), 1)
                self.emit(MAKE_FLOAT, self.builder.add_float(im), 1)
                self.emit(MAKE_COMPLEX, 0, -1)
            case bytes(b):
                self.emit(MAKE_BYTES, self.builder.add_bytes(b),1)
            case str(s):
                self.emit(MAKE_STRING, self.builder.add_string(s), 1)
            case tuple(t) | frozenset(t):
                # NOTE: frozenset() is used for 'x in <constant tuple>'
                # TODO: Avoid needing a really big stack for large tuples
                old_stacksize = self.stacksize
                for item in cast(Iterable[ConstantValue], t):
                    if self.builder.is_constant(item):
                        oparg = self.builder.index_of_constant(item)
                        self.emit(LAZY_LOAD_CONSTANT, oparg, 1)
                    else:
                        self.generate(cast(ConstantValue, item))
                opcode = BUILD_TUPLE if isinstance(t, tuple) else BUILD_SET
                self.emit(opcode, len(t), 1 - len(t))
                assert self.stacksize == old_stacksize + 1, \
                    (self.stacksize, old_stacksize)
            case types.CodeType() as code:
                self.emit(MAKE_CODE_OBJECT, self.builder.add_code(code), 1)
            case _:
                raise TypeError(
                    f"Cannot generate code for {type(value).__name__} -- {value!r}"
                )
                assert False, repr(value)

    def get_bytes(self):
        if self.data is not None:
            return self.data
        data = bytearray()
        for opcode, oparg in self.instructions:
            assert isinstance(oparg, int)
            if oparg >= 256:
                # Emit a sequence of EXTENDED_ARG prefix opcodes
                opargs: list[int] = []
                while oparg:
                    opargs.append(oparg & 0xFF)
                    oparg >>= 8
                opargs.reverse()
                for i in opargs[:-1]:
                    data.extend((EXTENDED_ARG, i))
                oparg = opargs[-1]
            data.extend((opcode, oparg))
        prefix = struct.pack("<LL", self.max_stacksize, len(data) // 2)
        self.data = prefix + bytes(data)
        return self.data


def rewritten_bytecode(code: types.CodeType, builder: Builder) -> bytes:
    """Rewrite some instructions.
    - Replace LOAD_CONST i with LAZY_LOAD_CONSTANT j.
    """
    instrs = code.co_code
    new = bytearray()
    for i in range(0, len(instrs), 2):
        opcode: int
        oparg: int
        opcode, oparg = instrs[i : i + 2]
        if opcode == LOAD_CONST:
            # TODO: Handle EXTENDED_ARG
            if i >= 2 and instrs[i - 2] == EXTENDED_ARG:
                raise RuntimeError(
                    f"More than 256 constants in original "
                    f"{code.co_name} at line {code.co_firstlineno}"
                )
                oparg = oparg | (instrs[i - 1] << 8)
            value = code.co_consts[oparg]
            if is_immediate(value):
                if type(value) == int:
                    opcode = MAKE_INT
                    oparg = value
                else:
                    opcode = LOAD_COMMON_CONSTANT
                    match value:
                        case None:
                            oparg = 0
                        case bool() as b:
                            oparg = 1 + b
                        case builtins.Ellipsis:
                            oparg = 3
                        case tuple(()):
                            opcode = BUILD_TUPLE
                            oparg = 0
                        case frozenset(()):
                            opcode = BUILD_SET
                            oparg = 0
                        case _:
                            # This code and is_immediate() are out of sync
                            assert False, \
                                f"{value} is not an immediately loadable constant"
            else:
                if is_function_code(code):
                    assert oparg > 0
                    oparg -= 1
                opcode = LAZY_LOAD_CONSTANT
                # oparg = builder.add_constant(code.co_consts[oparg])
        else:
            assert opcode not in dis.hasconst
        new.extend((opcode, oparg))
    return new


def is_immediate(value: object) -> bool:
    return False
    match value:
        case None | bool() | builtins.Ellipsis | tuple(()):
            return True
        case int(i) if 0 <= i < 256:
            return True
        case tuple(()):
            return True
        case frozenset(s) if not s:  # type: ignore  # Pyright doesn't like this
            return True
        case _:
            return False


COMPREHENSION_NAMES = {"<genexpr>", "<listcomp>", "<setcomp>", "<dictcomp>"}


def is_function_code(code: types.CodeType) -> bool:
    # Functions store their docstring as constant zero;
    # other code objects have explicit code to assign to __doc__.
    return (
        code.co_flags & FUNCTION_FLAGS == FUNCTION_FLAGS
        # NOTE: There's no direct way to tell a comprehension code object
        and code.co_name not in COMPREHENSION_NAMES
    )


class CodeObject(Thing[types.CodeType]):
    def __init__(self, code: types.CodeType, builder: Builder):
        self.value = code
        self.builder = builder
        self.co_strings_start = 0
        self.co_strings_size = 0
        self.co_consts_start = 0
        self.co_consts_size = 0

    def preload(self):
        """Compute indexes that need to be patched into existing code."""
        code = self.value
        if is_function_code(code):
            consts = code.co_consts[1:]
        else:
            consts = code.co_consts

        self.co_consts_start = len(self.builder.constants)
        self.builder.co_consts_start = self.co_consts_start
        for i, value in enumerate(consts):
            if not is_immediate(value):
                index = self.builder.add_constant(value)
            else:
                raise ValueError('no immediates for now')

            ## This check is wrong - we can add more constants when
            ## cc.set_index calls generate()
            if index != self.co_consts_start + i:
                raise RuntimeError(
                    f"Const index mismatch: "
                    f"{self.co_consts_start=} {i=} {value=} {index=}"
                )
        self.co_consts_size = len(self.builder.constants) - self.co_consts_start
        self.builder.co_consts_start = -1

        ## co_names
        self.co_strings_start = len(self.builder.strings)
        self.builder.co_strings_start = self.co_strings_start
        for i, name in enumerate(code.co_names):
            index = self.builder.add_string(name)
            if index != self.co_strings_start + i:
                raise RuntimeError(
                    f"Name index mismatch: "
                    f"{self.co_strings_start=} {i=} {name=} {index=}"
                )
        self.co_strings_size = len(code.co_names)
        self.builder.co_strings_start = -1
        assert len(self.builder.strings) - self.co_strings_start == self.co_strings_size

    def finish(self):
        """Compute indexes for additional values.

        These do not need to be patched into existing code so the index values

        - Compute constant indexes for toplevel non-immediate non-code constants
        - Compute string indexes for co_varnames, co_freevars, co_cellvars
        """
        code = self.value
        self.builder.add_string(code.co_name)
        # TODO: Typeshed stubs need to be updated to add these two fields
        self.builder.add_bytes(code.co_linetable)  # type: ignore
        self.builder.add_bytes(code.co_exceptiontable)  # type: ignore
        self.builder.add_string(code.co_filename)
        if is_function_code(code) and code.co_consts:
            docstring = code.co_consts[0]
            if docstring is not None:
                self.builder.add_string(docstring)
        for name in code.co_varnames + code.co_freevars + code.co_cellvars:
            self.builder.add_string(name)

    def get_bytes(self) -> bytes:
        assert self.builder.locked
        code = self.value
        # TODO: Typeshed stubs need to be updated to add these two fields
        ltindex = self.builder.add_bytes(code.co_linetable)  # type: ignore
        etindex = self.builder.add_bytes(code.co_exceptiontable)  # type: ignore
        docindex = 0
        if is_function_code(code) and code.co_consts:
            docstring = code.co_consts[0]
            if docstring is not None:
                docindex = self.builder.add_string(docstring)

        new_bytecode = rewritten_bytecode(code, self.builder)

        result = bytearray()
        prefix = struct.pack(
            "<15L",
            code.co_argcount,
            code.co_posonlyargcount,
            code.co_kwonlyargcount,
            code.co_stacksize,
            code.co_flags,
            self.builder.add_string(code.co_filename),
            self.builder.add_string(code.co_name),
            code.co_firstlineno,
            docindex,
            ltindex,
            etindex,
            self.co_strings_start,
            self.co_strings_size,
            self.co_consts_start,
            self.co_consts_size,
        )

        result += prefix

        n_instrs = len(new_bytecode) // 2
        if n_instrs & 1:  # Pad code to multiple of 4
            new_bytecode += b"\0\0"
        assert len(new_bytecode) & 3 == 0, len(result)
        codearray = bytearray()
        codearray += struct.pack("<L", n_instrs)
        codearray += new_bytecode
        result += codearray

        names = bytearray()
        names += struct.pack("<L", len(code.co_names))
        for name in code.co_names:
            names += struct.pack("<L", self.builder.add_string(name))
        result += names

        nargs = code.co_argcount + code.co_kwonlyargcount
        # TODO: Bump nargs if *args or **kwds present
        if set(code.co_varnames[:nargs]) & set(code.co_cellvars) != set():
            raise RuntimeError(
                f"a varname is a cell in {code.co_name} "
                f"in {code.co_filename}:{code.co_firstlineno}"
                f" -- {set(code.co_varnames[:nargs]) & set(code.co_cellvars)}"
            )
        localsplusnames = code.co_varnames + code.co_freevars + code.co_cellvars
        locals = bytearray()
        locals += struct.pack("<L", len(localsplusnames))
        for local in localsplusnames:
            locals += struct.pack("<L", self.builder.add_string(local))
        result += locals

        kinds: list[int] = []
        for name in code.co_varnames:
            kinds.append(CO_FAST_LOCAL)
        for name in code.co_freevars:
            kinds.append(CO_FAST_FREE)
        for name in code.co_cellvars:
            kinds.append(CO_FAST_CELL)
        assert len(kinds) == len(localsplusnames)
        localspluskinds = bytes(kinds)
        result += localspluskinds

        return bytes(result)


@runtime_checkable
class BytesProducer(Protocol):
    def get_bytes(self) -> bytes:
        ...


T = TypeVar("T")


Pair: TypeAlias = tuple[int, int]


class Builder:
    def __init__(self):
        self.codeobjs: MutableMapping[CodeObject | Redirect, Pair] = OrderedDict()
        self.strings: MutableMapping[String | Redirect, Pair] = OrderedDict()
        self.blobs: MutableMapping[BlobConstant | Redirect, Pair] = OrderedDict()
        self.constants: MutableMapping[ComplexConstant | Redirect, Pair] = OrderedDict()
        self.locked = False
        self.co_strings_start = -1
        self.co_consts_start = -1

    def lock(self):
        self.locked = True

    def add(
        self, where: MutableMapping[T | Redirect, Pair], thing: T | Redirect
    ) -> int:
        # Look for a match
        if thing in where:
            index, _ = where[thing]
            return index
        # Append a new one
        index = len(where)
        assert not self.locked
        where[thing] = (index, index)
        return index

    def add_redirect(
        self, where: MutableMapping[T | Redirect, Pair], start_index: int, thing: T, target: int
    ):
        thing_index, redirect_index = where[thing]
        assert thing_index == target
        if redirect_index >= start_index:
            # we already have a redirect for Thing in this co
            if self.co_strings_start >= 0:
                # Should not happen during the co_names construction stage
                assert False, "Multiple redirects for a thing in a CodeObject"
            return redirect_index
        index = self.add(where, Redirect(target))
        where[thing] = (where[thing][0], index)
        return index

    def add_bytes(self, value: bytes) -> int:
        return self.add(self.blobs, Bytes(value))

    def add_string(self, value: str) -> int:
        thing = String(value)
        index = self.add(self.strings, thing)
        if index < self.co_strings_start:
            return self.add_redirect(
                self.strings, self.co_strings_start, thing, index)
        return index

    def add_long(self, value: int) -> int:
        return self.add(self.blobs, LongInt(value))

    def add_float(self, value: float) -> int:
        return self.add(self.blobs, Float(value))

    def is_constant(self, value: ConstantValue) -> bool:
        return ComplexConstant(value, self) in self.constants

    def index_of_constant(self, value: ConstantValue) -> bool:
        cc = ComplexConstant(value, self)
        assert cc in self.constants
        return self.constants[cc][0]

    def add_constant(self, value: ConstantValue) -> int:
        cc = ComplexConstant(value, self)
        index = self.add(self.constants, cc)
        if index < self.co_consts_start:
            index = self.add_redirect(
                self.constants, self.co_consts_start, cc, index)
        cc.set_index(index)
        return index

    def add_code(self, code: types.CodeType) -> int:
        co = CodeObject(code, self)
        return self.add(self.codeobjs, co)

    def preload_code_objects(self):
        for co in self.codeobjs:
            if not isinstance(co, Redirect):
                co.preload()

    def finish_code_objects(self):
        for co in self.codeobjs:
            if not isinstance(co, Redirect):
                co.finish()

    def get_bytes(self) -> bytes:
        code_section_size = 4 + 4 * len(self.codeobjs)
        const_section_size = 4 + 4 * len(self.constants)
        string_section_size = 4 + 4 * len(self.strings)
        blob_section_size = 4 + 4 * len(self.blobs)
        binary_section_start = (
            16  # Header size
            + code_section_size
            + const_section_size
            + string_section_size
            + blob_section_size
        )
        binary_data = bytearray()

        def helper(what: Iterable[BytesProducer | Redirect], name: str) -> bytearray:
            nonlocal binary_data
            offsets = bytearray()
            for thing in what:
                if isinstance(thing, Redirect):
                    offset = (thing.target << 1) | 1
                else:
                    offset = binary_section_start + len(binary_data)
                    binary_data += thing.get_bytes()
                    # if len(binary_data) % 4 != 0:
                    #     print(f"Pad from {len(binary_data)} to {(len(binary_data)+4)//4 * 4} for {name}")
                    while len(binary_data) % 4 != 0:
                        binary_data.append(0)  # Pad
                offsets += struct.pack("<L", offset)
            return offsets

        code_offsets = helper(self.codeobjs, "code")
        const_offsets = helper(self.constants, "consts")
        string_offsets = helper(self.strings, "strings")
        blob_offsets = helper(self.blobs, "blobs")
        binary_section_size = len(binary_data)
        prefix_size = (
            16
            + 4
            + len(code_offsets)
            + 4
            + len(const_offsets)
            + 4
            + len(string_offsets)
            + 4
            + len(blob_offsets)
        )
        header = b"PYC." + struct.pack(
            "<HHLL", 0, 0, 0, prefix_size + binary_section_size
        )
        assert len(header) == 16
        prefix = (
            header
            + struct.pack("<L", len(code_offsets) // 4)
            + code_offsets
            + struct.pack("<L", len(const_offsets) // 4)
            + const_offsets
            + struct.pack("<L", len(string_offsets) // 4)
            + string_offsets
            + struct.pack("<L", len(blob_offsets) // 4)
            + blob_offsets
        )
        assert len(prefix) == binary_section_start
        return prefix + binary_data


def all_code_objects(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for x in code.co_consts:
        if isinstance(x, types.CodeType):
            yield from all_code_objects(x)


def add_everything(builder: Builder, code: types.CodeType):
    for c in all_code_objects(code):
        builder.add_code(c)
    builder.preload_code_objects()
    builder.finish_code_objects()


def build_source(source: str | bytes, filename: str = "<string>") -> Builder:
    builder = Builder()
    code = compile(source, filename, "exec", dont_inherit=True)
    add_everything(builder, code)
    builder.lock()
    return builder


def serialize_source(source: str | bytes, filename: str = "<string>") -> bytes:
    builder = build_source(source)
    data = builder.get_bytes()
    return data


def report(builder: Builder):
    print(f"Code table -- {len(builder.codeobjs)} items:")
    # TODO: Format long byte strings nicer, with ASCII on the side, etc.
    for i, co in enumerate(builder.codeobjs):
        try:
            b = co.get_bytes()
        except RuntimeError as err:
            print(f"  Code object {i} -- Error: {err}")
            continue
        header = struct.unpack("<16L", b[:64])
        n_instrs = header[-1]
        bytecode = b[64 : 64 + 2 * n_instrs]
        print(f"  Code object {i}")
        print(f"  Header {header}")
        stream = io.StringIO()
        dis.dis(bytecode, file=stream)
        lines = stream.getvalue().splitlines()
        if len(lines) > 20:
            lines = lines[:10] + ["        ..."] + lines[-10:]
        for line in lines:
            print(line)
    print(f"Constant table -- {len(builder.constants)} items:")
    for i, constant in enumerate(builder.constants):
        b = constant.get_bytes()
        stacksize, n_instrs = struct.unpack("<LL", b[:8])
        bytecode = b[8:]
        print(
            f"  Code for constant {i} (stack size {stacksize}, {n_instrs} instructions)"
        )
        dis.dis(b[8:])

    def helper(i: int, head: str, tail: str):
        if len(head) + len(tail) <= 72:
            print(f"{i:4d}: {head} {tail}")
        else:

            def inner(prefix: str, body: str):
                if len(body) <= 72:
                    print(f"{prefix} {body}")
                else:
                    print(f"{prefix} {body[:35]} .. {body[-32:]}")

            inner(f"{i:4d}:", head)
            inner("     ", tail)

    print(f"String table -- {len(builder.strings)} items:")
    for i, string in enumerate(builder.strings):
        if isinstance(string, Redirect):
            continue
        b = string.get_bytes()
        nb, pos = decode_varint(b)
        head = b.hex(" ")
        tail = f"({nb}, {repr(b[pos:])})"
        helper(i, head, tail)
    print(f"Blob table -- {len(builder.blobs)} items:")
    for i, blob in enumerate(builder.blobs):
        b = blob.get_bytes()
        head = b.hex(" ")
        tail = f"({len(b)}, {b!r})"
        helper(i, head, tail)


def main():
    if not sys.argv[1:]:
        builder = Builder()
        builder.add_constant(
            (0, 1000, -1, "Hello world", "你好", b"hello world", 3.14, 0.5j)
        )
    else:
        filename = sys.argv[1]
        with open(filename, "rb") as f:
            source = f.read()
            builder = build_source(source, filename)
    report(builder)
    try:
        pyc_data = builder.get_bytes()
    except RuntimeError as err:
        print("Cannot write example.pyc:", err)
    else:
        with open("example.pyc", "wb") as f:
            f.write(pyc_data)
        print(f"Wrote {len(pyc_data)} bytes to example.pyc")


if __name__ == "__main__":
    main()
