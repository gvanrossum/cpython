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


spam = Spam()
co = spam.inc_slots.__code__

print()
dis.dis(co)

#disassembled = sys.guido(co)
#print()
#print('=====')
#print()
#dis.dis(disassembled)

print()
print('=====')

sys.eric(co, spam)
print()
dis.dis(co)
