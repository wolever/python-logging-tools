import os
import time
import random
import logging
import traceback
import contextlib
from threading import local


Undefined = object()


def to_base(number, alphabet):
    if not isinstance(number, int):
        raise TypeError("number must be an integer")
    if number < 0:
        raise ValueError("number must be nonnegative")

    # Special case for zero
    if number == 0:
        return "0"

    in_base = []
    while number != 0:
        number, i = divmod(number, len(alphabet))
        in_base.append(alphabet[i])
    return "".join(reversed(in_base))


def safe_to_str(obj):
    """Safely converts 'obj' to a string:

    >>> safe_to_str(None)
    '(None)'
    >>> safe_to_str(1)
    '1'
    >>> safe_to_str(b'foo')
    'foo'
    >>> safe_to_str(b'\\xff')
    '\\xff'
    """

    if obj is None:
        return "(None)"

    try:
        if isinstance(obj, bytes):
            return obj.decode("utf-8", "replace")
        return str(obj)
    except Exception:
        return repr(obj)


ALPHABET_36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def to36(number):
    return to_base(number, ALPHABET_36)


def mk_random_id(ensure_unique=None):
    """Returns a unique 64 bit ID which is based on a random number and
    the current time."""
    # Truncate the current unix time to 32 bits...
    curtime = int(time.time()) & ((1 << 32) - 1)
    # ... then slap some random bits on the end.
    # Do this to help the database maintain temporal locality.
    # (it's possible that these should be swapped - with the
    # random bits coming first and the time bits coming second)
    res = to36((curtime << 32) | random.getrandbits(32))
    if ensure_unique is not None and res in ensure_unique:
        return mk_random_id(ensure_unique=ensure_unique)
    return res


class RequestIdLogContextWsgiApp(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ["LOG_REQUEST_ID"] = mk_random_id()
        environ["wsgi.input"] = ReadTimingStreamWrapper(environ["wsgi.input"])
        return self.app(environ, start_response)


class ReadTimingStreamWrapper(object):
    def __init__(self, stream):
        self._stream = stream
        self.read_byte_count = 0
        self.first_read_time = None
        self.last_read_time = None

    def read(self, *args, **kwargs):
        if self.first_read_time is None:
            self.first_read_time = time.time()
        self.last_read_time = time.time()
        res = self._stream.read(*args, **kwargs)
        self.read_byte_count += len(res)
        return res

    def __getattr__(self, name):
        return getattr(self._stream, name)


class GlobalLogContext(local):
    def __init__(self):
        self.clear()

    def clear(self):
        self._items = {}

    @contextlib.contextmanager
    def with_log_context(self, **attrs):
        old_values = [(key, self.get(key, Undefined)) for key in attrs]
        self._items.update(attrs)
        yield
        for key, old_val in old_values:
            if old_val is Undefined:
                self._items.pop(key, None)
            else:
                self._items[key] = old_val

    __call__ = with_log_context

    def set(self, attr, val):
        self._items[attr] = val

    def get(self, attr, default=None):
        return self._items.get(attr, default)

    def get_log_context(self):
        return self._items



GLOBAL_LOG_CONTEXT = GlobalLogContext()