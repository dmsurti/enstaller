import contextlib
import tempfile
import time

from cStringIO import StringIO

import mock

from okonomiyaki.repositories.enpkg import EnpkgS3IndexEntry

from enstaller.eggcollect import AbstractEggCollection
from enstaller.egg_meta import split_eggname
from enstaller.errors import AuthFailedError
from enstaller.utils import PY_VER

def dummy_enpkg_entry_factory(name, version, build):
    data = {"egg_basename": name, "packages": [], "python": PY_VER,
            "size": 1024, "version": version, "build": build,
            "available": True}
    return EnpkgS3IndexEntry.from_data(data)

def dummy_installed_egg_factory(name, version, build, meta_dir=None):
    data = {"name": name.lower(), "platform": "linux2", "python": PY_VER,
            "type": "egg", "osdist": "RedHat_5",
            "installed": True, "hook": False, "version": version, "build": build,
            "key": "{0}-{1}-{2}.egg".format(name, version, build),
            "packages": [], "arch": "x86", "ctime": time.ctime()}
    return data

class MockedPrint(object):
    def __init__(self):
        self.s = StringIO()

    def __call__(self, *a):
        self.s.write(" ".join(str(_) for _ in a) + "\n")

    @property
    def value(self):
        return self.s.getvalue()

@contextlib.contextmanager
def mock_print():
    m = MockedPrint()

    with mock.patch("__builtin__.print", m):
        yield m

class MetaOnlyEggCollection(AbstractEggCollection):
    def __init__(self, prefix, entries):
        self.prefix = prefix
        self.entries = entries
        self._egg_name_to_entry = dict((entry["key"], entry) for entry in entries)

    def find(self, egg):
        return self._egg_name_to_entry.get(egg, None)

    def query(self, **kwargs):
        name = kwargs.get("name")
        for key in sorted(self._egg_name_to_entry.iterkeys()):
            info = self._egg_name_to_entry[key]
            if info and all(info.get(k) == v for k, v in kwargs.iteritems()):
                yield key, info

    def install(self, egg, dir_path, extra_info=None):
        name, version, build = split_eggname(egg)
        entry = dummy_installed_egg_factory(name, version, build, meta_dir=None)
        self._egg_name_to_entry[entry["key"]] = entry

    def remove(self, egg):
        popped = self._egg_name_to_entry.pop(egg, None)
        if popped is None:
            raise KeyError("Egg {} not found".format(egg))

# Decorators to force a certain configuration
def is_authenticated(f):
    return mock.patch("enstaller.main.authenticate",
                      lambda ignored: {"is_authenticated": True})(f)

def is_not_authenticated(f):
    return mock.patch("enstaller.main.authenticate",
                      lambda ignored: {"is_authenticated": False})(f)

def make_keyring_unavailable(f):
    return mock.patch("enstaller.config.keyring", None)(f)

def without_default_configuration(f):
    return mock.patch("enstaller.config.get_path", lambda: None)(f)

def with_default_configuration(f):
    from enstaller.config import Configuration
    class MyConfiguration(Configuration):
        @classmethod
        def _get_default_config(cls, create_if_not_exists=False):
            return cls()
    return mock.patch("enstaller.main.Configuration", MyConfiguration)(f)

def use_temporary_config_location(f):
    fp = tempfile.NamedTemporaryFile(delete=False)
    filename = fp.name
    return mock.patch("enstaller.config.Configuration._default_filename", lambda self: filename)(f)

def fail_authenticate(f):
    m = mock.Mock(side_effect=AuthFailedError())
    main = mock.patch("enstaller.main.authenticate", m)
    config = mock.patch("enstaller.config.authenticate", m)
    return main(config(f))

# Context managers to force certain configuration
@contextlib.contextmanager
def make_keyring_unavailable_context():
    with mock.patch("enstaller.config.keyring", None) as context:
        yield context

# Context managers to force certain configuration
@contextlib.contextmanager
def make_keyring_available_context():
    m = mock.Mock(["get_password", "set_password"])
    with mock.patch("enstaller.config.keyring", m) as context:
        yield context

@contextlib.contextmanager
def make_default_configuration_path(path):
    with mock.patch("enstaller.config.Configuration._default_filename",
                    lambda self: path):
        with mock.patch("enstaller.config.get_path",
                        lambda: path) as context:
            yield context

@contextlib.contextmanager
def mock_input_auth(username, password):
    with mock.patch("enstaller.main.input_auth",
                    return_value=(username, password)) as context:
        yield context
