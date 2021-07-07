"""Companion to pyco, reads the new PYC format.

This exists mostly as a way to validate that the PYC format proposal
has enough imformation to roundtrip.
"""

import dis
import struct
import types

import updis  # Update dis with extra opcodes


class Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def seek(self, pos: int):
        assert 0 <= pos < len(self.data)
        self.pos = pos

    def read_raw_bytes(self, n: int) -> bytes:
        assert self.pos + n <= len(self.data)
        b = self.data[self.pos : self.pos + n]
        assert len(b) == n
        self.pos += n
        return b

    def read_bytes(self) -> bytes:
        n = self.read_varint()
        return self.read_raw_bytes(n)

    def read_short(self) -> int:
        part = self.read_raw_bytes(2)
        return struct.unpack("<H", part)[0]

    def read_long(self) -> int:
        part = self.read_raw_bytes(4)
        return struct.unpack("<L", part)[0]

    def read_offsets(self, n: int) -> list[int]:
        offsets = []
        for _ in range(n):
            offsets.append(self.read_long())
        return offsets

    def read_sized_offsets(self) -> list[int]:
        count = self.read_long()
        return self.read_offsets(count)

    def read_varint(self) -> int:
        result = 0
        shift = 0
        while True:
            byte = self.data[self.pos]
            self.pos += 1
            result |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        return result

    def read_varstring(self) -> str:
        n_bytes = self.read_varint()
        raw = self.read_raw_bytes(n_bytes)
        return raw.decode("utf-8")


def dummy_func():
    pass


dummy_code = dummy_func.__code__


class PycFile:
    def __init__(self, data: bytes):
        self.data = data
        self.code_objects: list[types.CodeType] = []
        self.constants: list[object] = []
        self.strings: list[str] = []

    def load(self):
        reader = Reader(self.data)
        assert reader.read_raw_bytes(4) == b"PYC.", self.data[:4]
        self.version = reader.read_short()
        assert self.version == 0
        self.flags = reader.read_short()
        assert self.flags == 0
        meta_start = reader.read_long()
        assert meta_start == 0
        total_size = reader.read_long()
        data_size = len(self.data)
        assert total_size == data_size, (total_size, data_size)
        self.n_code = reader.read_long()
        self.code_offsets = reader.read_offsets(self.n_code)
        self.n_constants = reader.read_long()
        self.const_offsets = reader.read_offsets(self.n_constants)
        self.n_strings = reader.read_long()
        self.string_offsets = reader.read_offsets(self.n_strings)
        self.n_blobs = reader.read_long()
        self.blob_offsets = reader.read_offsets(self.n_blobs)

        self.code_objects = [None] * self.n_code
        self.constants = [None] * self.n_constants
        self.strings = [None] * self.n_strings
        self.blobs = [None] * self.n_blobs

    def get_bytes(self, i: int) -> bytes:
        assert 0 <= i < len(self.blobs)
        b = self.blobs[i]
        if b is not None:
            return b
        reader = Reader(self.data, self.blob_offsets[i])
        b = reader.read_bytes()
        self.blobs[i] = b
        return b

    def read_string(self, offset: int) -> str:
        reader = Reader(self.data, offset)
        return reader.read_varstring()

    def get_string(self, i: int) -> str:
        assert 0 <= i < len(self.strings)
        s = self.strings[i]
        if s is not None:
            return s
        s = self.read_string(self.string_offsets[i])
        self.strings[i] = s
        return s

    def get_code(self, i: int) -> types.CodeType:
        assert 0 <= i < len(self.code_objects)
        code = self.code_objects[i]
        if code is not None:
            return code
        reader = Reader(self.data, self.code_offsets[i])

        kwargs = dict(
            co_argcount=reader.read_long(),
            co_posonlyargcount=reader.read_long(),
            co_kwonlyargcount=reader.read_long(),
            co_stacksize=reader.read_long(),
            co_flags=reader.read_long(),
            co_filename=self.get_string(reader.read_long()),
            co_name=self.get_string(reader.read_long()),
            co_firstlineno=reader.read_long(),
        )
        docindex = reader.read_long()
        ltindex = reader.read_long()
        etindex = reader.read_long()
        strings_start = reader.read_long()
        strings_size = reader.read_long()
        # TODO: Technically object 0 is also a string, not None
        docstring = self.get_string(docindex) if docindex else None
        kwargs.update(
            co_exceptiontable=self.get_bytes(etindex),
            co_linetable=self.get_bytes(ltindex),
        )
        print(kwargs)

        ninstrs = reader.read_long()
        kwargs.update(co_code=reader.read_raw_bytes(2 * ninstrs))
        if ninstrs & 1:
            reader.read_raw_bytes(2)  # Align to 4
        assert reader.pos & 3 == 0, reader.pos  # I'm terrible

        string_indexes = reader.read_sized_offsets()

        localsplusnames_indexes = reader.read_sized_offsets()
        localsplusnames = [self.get_string(index) for index in localsplusnames_indexes]
        localspluskinds = reader.read_raw_bytes(len(localsplusnames))
        varnames = [name for name, kind in zip(localsplusnames, localspluskinds)
                         if kind == updis.CO_FAST_LOCAL]
        freevars = [name for name, kind in zip(localsplusnames, localspluskinds)
                         if kind == updis.CO_FAST_FREE]
        cellvars = [name for name, kind in zip(localsplusnames, localspluskinds)
                         if kind == updis.CO_FAST_CELL]
        kwargs.update(
            co_varnames=tuple(varnames),
            co_freevars=tuple(freevars),
            co_cellvars=tuple(cellvars),
            co_nlocals=len(varnames),
        )

        code = dummy_code.replace(**kwargs)
        self.code_objects[i] = code
        return code

    def report(self):
        reader = Reader(self.data)
        # Print the strings table, as an example
        strings = []
        for i, offset in enumerate(self.string_offsets):
            if offset & 1:  # Redirect
                offset = self.string_offsets[offset >> 1]
            reader.seek(offset)
            s = reader.read_varstring()
            print(f"String {i} at {offset}: {s!r}")
            strings.append(s)
        # Print the constants, as another example
        for i, offset in enumerate(self.const_offsets):
            reader.seek(offset)
            max_stacksize = reader.read_long()
            n_instrs = reader.read_long()
            bytecode = reader.read_raw_bytes(2 * n_instrs)
            print(
                f"Constant {i} at {offset}, stack={max_stacksize}, {n_instrs} opcodes"
            )
            dis.dis(bytecode)
        # We're on a roll! Print the code objects
        for i, offset in enumerate(self.code_offsets):
            reader.seek(offset)
            values = struct.unpack("<14L", reader.read_raw_bytes(14 * 4))
            print(f"Code object {i} at {offset}")
            print(values)
            n_instrs = values[-1]
            bytecode = reader.read_raw_bytes(2 * n_instrs)
            dis.dis(bytecode)
            if n_instrs & 1:
                reader.read_raw_bytes(2)  # Skip padding
            n_varnames = reader.read_long()
            varname_offsets = reader.read_offsets(n_varnames)
            for j, idx in enumerate(varname_offsets):
                varname = strings[idx]
                print(f"Var {j} at index {idx}: {varname!r}")


def unpyc(data: bytes):
    pyc = PycFile(data)
    pyc.load()
    pyc.report()
    for i in range(len(pyc.code_offsets)):
        print("Code object", i)
        code = pyc.get_code(i)
        dis.dis(code)


def main():
    with open("example.pyc", "rb") as f:
        data = f.read()
        unpyc(data)


if __name__ == "__main__":
    main()
