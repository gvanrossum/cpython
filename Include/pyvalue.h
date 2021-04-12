#ifndef Py_PYVALUE_H
#define Py_PYVALUE_H

#ifdef __cplusplus
extern "C" {
#endif

#if SIZEOF_VOID_P == 4
#error "Don't know how to do this for 32-bit arch yet"
#elif SIZEOF_VOID_P == 8

// The type to use instead of PyObject *
typedef struct _pyc {
    uint64_t bits;
} PyValue;

#else
#error "This only works for 32- and 64-bit pointers"
#endif


#ifndef Py_LIMITED_API
#  define Py_CPYTHON_PYVALUE_H
#  include  "cpython/pyvalue.h"
#  undef Py_CPYTHON_PYVALUE_H
#endif

#ifdef __cplusplus
}
#endif
#endif /* !Py_PYVALUE_H */
