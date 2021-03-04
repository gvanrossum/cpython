import dis
import sys


class Spam:
    __slots__ = ('a', 'b', 'c')

    def __init__(self):
        self.a = 1
        self.b = 2
        self.c = 3

    def inc_slots(self):
        self.a = self.a + 1
        self.b = self.b + 1
        self.c = self.c + 1


obj = Spam()
co = obj.inc_slots.__code__

import zipfile
obj = zipfile.ZipInfo()
cls = type(obj)
co = obj._decodeExtra.__code__

#print(dir(getattr(cls, cls.__slots__[0])))
#print(f'obj size: {sys.getsizeof(obj)}')
#print('slots:')
#for i, name in enumerate(dis._get_slots(cls)):
#    descr = getattr(cls, name, None)
#    if descr is not None:
#        print(f'  {i:>2} {name:20} ({descr})')

print()
dis.dis(co)

print()
print('=====')
sys.eric(co, obj)
print()
dis.dis(co)
