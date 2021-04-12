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
static inline PyValue_Tag(PyValue v) { return v.bits & 7; }

// Tag values
#define PyValue_TagInt 1
#define PyValue_TagObject 0

// Range of taggable ints (inclusive range)
#define PyValue_MinInt ((1LL << 60) - (1LL << 61))
#define PyValue_MaxInt ((1LL << 60) - 1)
// TODO: Change MIN <= x <= MAX into ((unsigned)((signed)x - MIN) <= (MAX - MIN)
#define PyValue_InIntRange(i) (PyValue_MinInt <= (i) && (i) <= PyValue_MaxInt)

// Macros to check what we have
#define PyValue_IsInt(v) (PyValue_Tag(v) == PyValue_TagInt)
#define PyValue_IsFloat(v) 0  // XXX TODO
#define PyValue_IsObject(v) (PyValue_Tag(v) == PyValue_TagObject)
#define PyValue_IsNULL(v) (v.bits == 0)

// Decoding macros
#ifdef Py_DEBUG
#define PyValue_AsInt(v) (PyValue_IsInt(v) ? (int64_t)((v).bits) >> 3 : (abort(), 0))
#define PyValue_AsFloat(v) (0.0)  // XXX TODO
#define PyValue_AsObject(v) ((PyObject *)((v).bits))
#else /* Py_DEBUG */
#define PyValue_AsInt(v) ((int64_t)((v).bits) >> 3)
#define PyValue_AsFloat(v) (0.0)  // XXX TODO
#define PyValue_AsObject(v) ((PyObject *)((v).bits))
#endif /* Py_DEBUG */

// Inline functions for encoding

typedef union convert {
     uint64_t bits;
     int64_t i;
     // double d;
     PyObject *p;
     PyValue v;
} _PyConvert;

static inline PyValue
PyValue_FromInt(int64_t i)
{
    assert(PyValue_InIntRange(i));
    _PyConvert u;
    u.i = i << 3;
    u.bits |= PyValue_TagInt;
    return u.v;
}

static inline PyValue
PyValue_FromObject(PyObject *p)
{
    _PyConvert u;
    u.p = p;
    u.bits |= PyValue_TagObject;
    return u.v;
}

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
     object may require allocating new memory, this operation may fail.
     Since it would be a pain to check for such failures in the caller,
     and running out of memory is not really a recoverable condition,
     for now the function just calls Py_FatalError().

     **NOTE:** Boxing cannot fail, but it still creates an object, and the
     caller must take ownership of that object and eventually DECREF it.
     A more convenient helper function is PyValue_BoxInPlace().
*/

PyValue PyValue_Unbox(PyObject *);  // Unboxes smaller int objects
PyObject *PyValue_Box(PyValue);  // Boxes non-pointer values
PyObject *PyValue_BoxInPlace(PyValue *);  // Boxes in-place

#define PyValue_CLEAR(v)                \
    do {                                \
        PyValue _py_tcl = (v);          \
        if (!PyValue_IsNULL(_py_tcl)) { \
            (v) = PyValue_NULL;         \
            PyValue_DECREF(_py_tcl);    \
        }                               \
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
    if (PyValue_IsObject(v) && !PyValue_IsNULL(v)) {  \
        PyObject *_py_txd = PyValue_AsObject(v);      \
        Py_DECREF(_py_txd);                           \
    }

#define PyValue_XINCREF(v)                            \
    if (PyValue_IsObject(v) && !PyValue_IsNULL(v)) {  \
        PyObject *_py_dxi = PyValue_AsObject(v);      \
        Py_INCREF(_py_dxi);                           \
    }
