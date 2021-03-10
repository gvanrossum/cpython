#if SIZEOF_VOID_P == 4
#error "Don't know how to do this for 32-bit arch yet"
#elif SIZEOF_VOID_P == 8

// The type to use instead of PyObject *
typedef int64_t PyValue;  // TODO: Make it a struct for better type checking?

#else
#error "This only works for 32- and 64-bit pointers"
#endif


#ifndef Py_LIMITED_API
#  define Py_CPYTHON_PYVALUE_H
#  include  "cpython/pyvalue.h"
#  undef Py_CPYTHON_PYVALUE_H
#endif
