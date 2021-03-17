// XXX TODO include header infrastructure

/* Macros for tagged pointers.
 * See https://github.com/gvanrossum/speed/issues/7
 */

#if SIZEOF_VOID_P == 4
#error "Don't know how to do this for 32-bit arch yet"

/*
Tag  |  Meaning     | Encoding
-----|--------------|------------------
1    | int (31 bit) | (val<<1) | 1
0    | PyObject *   | val

- Large ints and all floats remain PyObject *
*/

#elif SIZEOF_VOID_P == 8

/*
Tag |  Meaning                  | Encoding
----|---------------------------|--------------------
1   | int (61 bit)              | (val<<3) | 1
2-7 | float (abs(val) < 2**512) | rotate_bits(val, 4)
0   | PyObject *                | val

- Large ints and floats with extreme exponents remain PyObject *
- Floats are currently not supported
*/

// Extract the tag
#define PyValue_Tag(x) ((x) & 7)

// Tag values
#define PyValue_TagInt 1
#define PyValue_TagObject 0

// Macros to check what we have
#define PyValue_IsInt(x) (PyValue_Tag(x) == PyValue_TagInt)
#define PyValue_IsFloat(x) 0  // XXX TODO
#define PyValue_IsObject(x) (PyValue_Tag(x) == PyValue_TagObject)

// Decoding macros
#ifdef Py_DEBUG
#define PyValue_AsInt(x) (PyValue_IsInt(x) ? (x) >> 3 : (abort(), 0))
#define PyValue_AsFloat(x) (0.0)  // XXX TODO
#define PyValue_AsObject(x) ((PyObject *)(x))
#else /* Py_DEBUG */
#define PyValue_AsInt(x) ((x) >> 3)
#define PyValue_AsFloat(x) (0.0)  // XXX TODO
#define PyValue_AsObject(x) ((PyObject *)(x))
#endif /* Py_DEBUG */

// Encoding macros
#define PyValue_FromInt(x) ((PyValue)((x) << 3) | PyValue_TagInt)
#define PyValue_FromObject(x) (((PyValue)(x)) | PyValue_TagObject)

#else
#error "This only works for 32- and 64-bit pointers"
#endif

// What NULL encodes to
#define PyValue_Error (PyValue_FromObject((PyObject *)NULL))
#define PyValue_NULL (PyValue_FromObject((PyObject *)NULL))

/* Boxing and unboxing API

   These operations are somewhat asymmetric.

   - Unboxing may convert int objects with in-range values to tagged values.
     This cannot fail, since no memory is allocated, and it is always okay
     to return the original object. It does not bump the refcount.
     Usage is meant to be in the context of moving ownership of a value
     from one variable to another (e.g. popping the stack into a variable).
     NULL is passed through.

   - Boxing converts tagged ints back to objects, and returns the original
     object in other cases (again, passing NULL through). It does not bump
     the reference count when passing through an object. However, when it
     has to convert a tagged integer to an int object, the recipient becomes
     the owner of the newly created int object. Since creating a new int
     object may require allocating new memory, this operation may fail,
     and in that case NULL is returned. The caller will have to use
     PyErr_Occurred() to distinguish a pass-through NULL from an error,
     unless the caller has already checked that the argument is not NULL.
*/

PyValue PyValue_Unbox(PyObject *);  // Unboxes smaller int objects
PyObject *PyValue_Box(PyValue);  // Boxes non-pointer values

#define PyValue_CLEAR(v)               \
    do {                               \
        PyValue _py_tcl = (v);         \
        if (_py_tcl != PyValue_NULL) { \
            (v) = PyValue_NULL;        \
            PyValue_DECREF(_py_tcl);   \
        }                              \
    } while (0)

#define PyValue_DECREF(v)                        \
    if (PyValue_IsObject(v)) {                   \
        PyObject *_py_tde = PyValue_AsObject(v); \
        Py_DECREF(_py_tde);                      \
    }

#define PyValue_INCREF(v)                        \
    if (PyValue_IsObject(v)) {                   \
        PyObject *_py_tin = PyValue_AsObject(v); \
        Py_INCREF(_py_tin);                      \
    }

#define PyValue_XDECREF(v)                            \
    if (PyValue_IsObject(v) && (v) != PyValue_NULL) { \
        PyObject *_py_txd = PyValue_AsObject(v);      \
        Py_DECREF(_py_txd);                           \
    }

#define PyValue_XINCREF(v)                            \
    if (PyValue_IsObject(v) && (v) != PyValue_NULL) { \
        PyObject *_py_dxi = PyValue_AsObject(v);      \
        Py_INCREF(_py_dxi);                           \
    }
