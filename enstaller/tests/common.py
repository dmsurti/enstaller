import contextlib
import time

from cStringIO import StringIO

import mock

from okonomiyaki.repositories.enpkg import EnpkgS3IndexEntry

import enstaller.config

from enstaller.eggcollect import AbstractEggCollection
from enstaller.egg_meta import split_eggname
from enstaller.utils import PY_VER

def patched_read(**kw):
    config = {}
    config.update(enstaller.config.Configuration()._dict)
    config.update(**kw)
    return config

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
    def __init__(self, entries):
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
