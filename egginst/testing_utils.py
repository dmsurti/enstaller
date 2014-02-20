from __future__ import print_function

import contextlib
import copy
import functools
import httplib
import os

_RAISE_NETWORK_ERROR_DEFAULT = False

def optional_args(decorator):
    """allows a decorator to take optional positional and keyword arguments.
    Assumes that taking a single, callable, positional argument means that
    it is decorating a function, i.e. something like this::

        @my_decorator
        def function(): pass

    Calls decorator with decorator(f, *args, **kwargs)"""

    @functools.wraps(decorator)
    def wrapper(*args, **kwargs):
        def dec(f):
            return decorator(f, *args, **kwargs)

        is_decorating = not kwargs and len(args) == 1 and callable(args[0])
        if is_decorating:
            f = args[0]
            args = []
            return dec(f)
        else:
            return dec

    return wrapper

_network_error_classes = IOError, httplib.HTTPException

@optional_args
def network(t, raise_on_error=_RAISE_NETWORK_ERROR_DEFAULT,
            error_classes=_network_error_classes, num_runs=2):
    """
    Label a test as requiring network connection and skip test if it encounters a ``URLError``.

    In some cases it is not possible to assume network presence (e.g. Debian
    build hosts).

    You can pass an optional ``raise_on_error`` argument to the decorator, in
    which case it will always raise an error even if it's not a subclass of
    ``error_classes``.

    Parameters
    ----------
    t : callable
        The test requiring network connectivity.
    raise_on_error : bool, optional
        If True, never catches errors.
    error_classes : tuple, optional
        error classes to ignore. If not in ``error_classes``, raises the error.
        defaults to URLError. Be careful about changing the error classes here,
        it may result in undefined behavior.
    num_runs : int, optional
        Number of times to run test. If fails on last try, will raise. Default
        is 2 runs.

    Returns
    -------
    t : callable
        The decorated test `t`.

    Examples
    --------
    A test can be decorated as requiring network like this::

      >>> from pandas.util.testing import network
      >>> from pandas.io.common import urlopen
      >>> import nose
      >>> @network
      ... def test_network():
      ...     with urlopen("rabbit://bonanza.com") as f:
      ...         pass
      ...
      >>> try:
      ...     test_network()
      ... except nose.SkipTest:
      ...     print("SKIPPING!")
      ...
      SKIPPING!

    Alternatively, you can use set ``raise_on_error`` in order to get
    the error to bubble up, e.g.::

      >>> @network(raise_on_error=True)
      ... def test_network():
      ...     with urlopen("complaint://deadparrot.com") as f:
      ...         pass
      ...
      >>> test_network()
      Traceback (most recent call last):
        ...
      URLError: <urlopen error unknown url type: complaint>

    And use ``nosetests -a '!network'`` to exclude running tests requiring
    network connectivity. ``_RAISE_NETWORK_ERROR_DEFAULT`` in
    ``pandas/util/testing.py`` sets the default behavior (currently False).
    """
    from nose import SkipTest

    if num_runs < 1:
        raise ValueError("Must set at least 1 run")
    t.network = True

    @functools.wraps(t)
    def network_wrapper(*args, **kwargs):
        if raise_on_error:
            return t(*args, **kwargs)
        else:
            runs = 0

            for _ in range(num_runs):
                try:
                    try:
                        return t(*args, **kwargs)
                    except error_classes as e:
                        raise SkipTest("Skipping test %s" % e)
                except SkipTest:
                    raise
                except Exception as e:
                    if runs < num_runs - 1:
                        print("Failed: %r" % e)
                    else:
                        raise

                runs += 1

    return network_wrapper

def slow(t):
    """
    Label a test as slow.

    Parameters
    ----------
    t : callable
        The test requiring network connectivity.

    Returns
    -------
    t : callable
        The decorated test `t`.
    """
    t.slow = True

    @functools.wraps(t)
    def slow_wrapper(*args, **kwargs):
        return t(*args, **kwargs)

    return slow_wrapper

class ControlledEnv(object):
    """
    A special os.environ that can be used for mocking os.environ.

    Beyond avoiding modifying os.environ directly, this class allows some keys
    to be ignored

    Parameters
    ----------
    ignored_keys: list
        If specified, list of keys that will be ignored.
    environ: dict
        If specified, the dictionary to use for underlying data. Default is to
        use os.environ. In both cases, the dict is copied.

    Examples
    --------
    >>> env = ControlledEnv(["USERNAME"])
    >>> "USERNAME" in env:
    False
    """

    def __init__(self, ignored_keys=None, environ=None):
        if ignored_keys is None:
            ignored_keys = {}
        self._ignored_keys = ignored_keys

        if environ is None:
            environ = os.environ
        self._data = copy.copy(environ)

    def __getitem__(self, name):
        if name in self._ignored_keys:
            raise KeyError("Cannot access key {0}".format(name))
        else:
            return self._data[name]

    def get(self, name, default=None):
        if name in self._data and not name in self._ignored_keys:
            return self._data[name]
        else:
            return default

    def keys(self):
        return [k for k in self._data if not k in self._ignored_keys]

    def __setitem__(self, name, value):
        self._data[name] = value

    def __delitem__(self, name):
        del self._data[name]

    def __iter__(self):
        return iter((k, v) for k, v in self._data.iteritems() if not k in self._ignored_keys)

@contextlib.contextmanager
def assert_same_fs(test_case, prefix):
    all_files = []
    for root, dirs, files in os.walk(prefix):
        for f in files:
            all_files.extend(os.path.join(root, f) for f in files)
    old_state = set(all_files)

    yield

    for root, dirs, files in os.walk(prefix):
        for f in files:
            path = os.path.join(root, f)
            if path not in old_state:
                test_case.fail("Unexpected file: {}".format(path))
