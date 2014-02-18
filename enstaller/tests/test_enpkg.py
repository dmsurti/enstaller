import contextlib
import ntpath
import os.path
import posixpath
import shutil
import sys
import tempfile
import warnings

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import mock

from okonomiyaki.repositories.enpkg import EnpkgS3IndexEntry

from egginst.main import EggInst
from egginst.tests.common import mkdtemp, DUMMY_EGG, NOSE_1_2_1, NOSE_1_3_0
from egginst.utils import makedirs

from enstaller.config import Configuration
from enstaller.egg_meta import split_eggname
from enstaller.eggcollect import EggCollection, JoinedEggCollection
from enstaller.enpkg import Enpkg, EnpkgError
from enstaller.enpkg import get_default_kvs, req_from_anything, \
        get_package_path, check_prefixes, get_writable_local_dir
from enstaller.main import _create_enstaller_update_enpkg, create_joined_store
from enstaller.resolve import Req
from enstaller.store.indexed import LocalIndexedStore, RemoteHTTPIndexedStore
from enstaller.store.tests.common import EggsStore, MetadataOnlyStore
from enstaller.utils import PY_VER

from .common import dummy_enpkg_entry_factory, patched_read

@contextlib.contextmanager
def catch_warning_for_tests():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        yield w

class TestMisc(unittest.TestCase):
    def test_get_default_kvs(self):
        config = Configuration()
        config.webservice_entry_point = "http://acme.com"
        store = get_default_kvs(config)
        self.assertEqual(store.root, "http://acme.com/")

    def test_req_from_anything_egg_string(self):
        req_string = "numpy-1.8.0-1.egg"

        req = req_from_anything(req_string)

        self.assertEqual(req.name, "numpy")
        self.assertEqual(req.version, "1.8.0")
        self.assertEqual(req.build, 1)

    def test_req_from_anything_req(self):
        req_arg = Req("numpy 1.8.0-1")

        req = req_from_anything(req_arg)

        self.assertEqual(req.name, "numpy")
        self.assertEqual(req.version, "1.8.0")
        self.assertEqual(req.build, 1)

    def test_req_from_anything_string(self):
        req = req_from_anything("numpy")

        self.assertEqual(req.name, "numpy")
        self.assertEqual(req.version, None)
        self.assertEqual(req.build, None)

    @mock.patch("sys.platform", "linux2")
    def test_get_package_path_unix(self):
        prefix = "/foo"
        r_site_packages = os.path.join(prefix, "lib", "python" + PY_VER, "site-packages")

        self.assertEqual(get_package_path(prefix), r_site_packages)

    @mock.patch("sys.platform", "win32")
    def test_get_package_path_windows(self):
        prefix = "c:\\foo"
        r_site_packages = ntpath.join(prefix, "lib", "site-packages")

        self.assertEqual(get_package_path(prefix), r_site_packages)

    @mock.patch("sys.platform", "linux2")
    def test_check_prefixes_unix(self):
        prefixes = ["/foo", "/bar"]
        site_packages = [posixpath.join(prefix,
                                        "lib/python{0}/site-packages". \
                                        format(PY_VER))
                         for prefix in prefixes]

        with mock.patch("sys.path", site_packages):
            with catch_warning_for_tests() as w:
                check_prefixes(prefixes)
                self.assertEqual(w, [])

        with mock.patch("sys.path", site_packages[::-1]):
            with catch_warning_for_tests() as w:
                check_prefixes(prefixes)
                self.assertEqual(len(w), 1)
                message = str(w[0].message)
                self.assertEqual(message, "Order of path prefixes doesn't match PYTHONPATH")

        with mock.patch("sys.path", []):
            with catch_warning_for_tests() as w:
                check_prefixes(prefixes)
                self.assertEqual(len(w), 1)
                message = str(w[0].message)
                self.assertEqual(message,
                                 "Expected to find {0} in PYTHONPATH". \
                                 format(site_packages[0]))

    @mock.patch("sys.platform", "win32")
    def test_check_prefixes_win32(self):
        prefixes = ["c:\\foo", "c:\\bar"]
        site_packages = [ntpath.join(prefix, "lib", "site-packages")
                         for prefix in prefixes]

        with mock.patch("sys.path", site_packages):
            with catch_warning_for_tests() as w:
                check_prefixes(prefixes)
                self.assertEqual(w, [])

        with mock.patch("sys.path", site_packages[::-1]):
            with catch_warning_for_tests() as w:
                check_prefixes(prefixes)
                self.assertEqual(len(w), 1)
                message = str(w[0].message)
                self.assertEqual(message, "Order of path prefixes doesn't match PYTHONPATH")

        with mock.patch("sys.path", []):
            with catch_warning_for_tests() as w:
                check_prefixes(prefixes)
                self.assertEqual(len(w), 1)
                message = str(w[0].message)
                self.assertEqual(message,
                                 "Expected to find {0} in PYTHONPATH". \
                                 format(site_packages[0]))

    def test_writable_local_dir_writable(self):
        config = Configuration()
        with mkdtemp() as d:
            config.repository_cache = d
            self.assertEqual(get_writable_local_dir(config), d)

    def test_writable_local_dir_non_writable(self):
        fake_dir = "/some/dummy_dir/hopefully/doesnt/exists"

        config = Configuration()
        config.repository_cache = fake_dir
        def mocked_makedirs(d):
            raise OSError("mocked makedirs")
        with mock.patch("os.makedirs", mocked_makedirs):
            self.assertNotEqual(get_writable_local_dir(config), "/foo")

class TestEnstallerUpdateHack(unittest.TestCase):
    def test_scenario1(self):
        """Test that we upgrade when remote is more recent than local."""
        remote_versions = [("4.6.1", 1)]
        local_version = "4.6.0"

        actions = self._compute_actions(remote_versions, local_version)
        self.assertNotEqual(actions, [])

    def test_scenario2(self):
        """Test that we don't upgrade when remote is less recent than local."""
        remote_versions = [("4.6.1", 1)]
        local_version = "4.6.2"

        actions = self._compute_actions(remote_versions, local_version)
        self.assertEqual(actions, [])

    def _compute_actions(self, remote_versions, local_version):
        prefixes = [sys.prefix]

        entries = [dummy_enpkg_entry_factory("enstaller", version, build) \
                   for version, build in remote_versions]
        repo = MetadataOnlyStore(entries)
        repo.connect()

        enpkg = Enpkg(repo, prefixes=prefixes, hook=None,
                      evt_mgr=None, verbose=False)
        new_enpkg = _create_enstaller_update_enpkg(enpkg, local_version)
        return new_enpkg._install_actions_enstaller(local_version)

class TestCreateJoinedStores(unittest.TestCase):
    def test_simple_dir(self):
        with mkdtemp() as d:
            urls = [d]
            store = create_joined_store(urls)
            self.assertEqual(len(store.repos), 1)

            store = store.repos[0]
            self.assertTrue(isinstance(store, LocalIndexedStore))
            self.assertEqual(store.root, d)

    def test_simple_file_scheme(self):
        urls = ["file:///foo"]
        store = create_joined_store(urls)
        self.assertEqual(len(store.repos), 1)

        store = store.repos[0]
        self.assertIsInstance(store, LocalIndexedStore)
        self.assertEqual(store.root, "/foo")

    def test_simple_http_scheme(self):
        urls = ["http://acme.com/repo"]
        store = create_joined_store(urls)
        self.assertEqual(len(store.repos), 1)

        store = store.repos[0]
        self.assertIsInstance(store, RemoteHTTPIndexedStore)
        self.assertEqual(store.root, urls[0])

    def test_invalid_scheme(self):
        urls = ["ftp://acme.com/repo"]
        with self.assertRaises(Exception):
            create_joined_store(urls)

class TestEnpkg(unittest.TestCase):
    def test_info_list_names(self):
        entries = [
            dummy_enpkg_entry_factory("numpy", "1.6.1", 1),
            dummy_enpkg_entry_factory("numpy", "1.8.0", 2),
            dummy_enpkg_entry_factory("numpy", "1.7.1", 1),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            queried_entries = enpkg.info_list_name("numpy")

            self.assertEqual(len(queried_entries), 3)
            self.assertEqual([q["version"] for q in queried_entries],
                             ["1.6.1", "1.7.1", "1.8.0"])

    def test_info_list_names_invalid_version(self):
        entries = [
            dummy_enpkg_entry_factory("numpy", "1.6.1", 1),
            dummy_enpkg_entry_factory("numpy", "1.8k", 2),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            queried_entries = enpkg.info_list_name("numpy")

            self.assertEqual(len(queried_entries), 2)
            self.assertEqual([q["version"] for q in queried_entries],
                             ["1.6.1", "1.8k"])

    def test_query_simple(self):
        entries = [
            dummy_enpkg_entry_factory("numpy", "1.6.1", 1),
            dummy_enpkg_entry_factory("numpy", "1.8k", 2),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            r = dict(enpkg.query(name="numpy"))
            self.assertEqual(set(r.keys()),
                             set(entry.s3index_key for entry in entries))

    def test_query_simple_with_local(self):
        """
        Ensure enpkg.query finds both local and remote eggs.
        """
        local_egg = DUMMY_EGG

        entries = [
            dummy_enpkg_entry_factory("dummy", "1.6.1", 1),
            dummy_enpkg_entry_factory("dummy", "1.8k", 2),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        local_entry = EnpkgS3IndexEntry.from_egg(DUMMY_EGG)

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            enpkg.ec.install(os.path.basename(local_egg),
                             os.path.dirname(local_egg))

            r = dict(enpkg.query(name="dummy"))
            self.assertEqual(set(r.keys()),
                             set(entry.s3index_key for entry in entries + [local_entry]))

class TestEnpkgActions(unittest.TestCase):
    def test_install_simple(self):
        entries = [
            dummy_enpkg_entry_factory("numpy", "1.6.1", 1),
            dummy_enpkg_entry_factory("numpy", "1.8.0", 2),
            dummy_enpkg_entry_factory("numpy", "1.7.1", 2),
        ]

        r_actions = [
            ('fetch_0', 'numpy-1.8.0-2.egg'),
            ('install', 'numpy-1.8.0-2.egg')
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            actions = enpkg.install_actions("numpy")

            self.assertEqual(actions, r_actions)

    def test_install_no_egg_entry(self):
        entries = [
            dummy_enpkg_entry_factory("numpy", "1.6.1", 1),
            dummy_enpkg_entry_factory("numpy", "1.8.0", 2),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            with self.assertRaises(EnpkgError):
                enpkg.install_actions("scipy")

    def test_remove(self):
        repo = MetadataOnlyStore([])
        repo.connect()

        with mkdtemp() as d:
            makedirs(d)

            for egg in [DUMMY_EGG]:
                egginst = EggInst(egg, d)
                egginst.install()

            local_repo = JoinedEggCollection([EggCollection(d, False, None)])
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            enpkg.ec = local_repo

            self.assertTrue(local_repo.find(os.path.basename(DUMMY_EGG)))
            actions = enpkg.remove_actions("dummy")
            self.assertEqual(actions, [("remove", os.path.basename(DUMMY_EGG))])

    def test_remove_non_existing(self):
        entries = [
            dummy_enpkg_entry_factory("numpy", "1.6.1", 1),
           dummy_enpkg_entry_factory("numpy", "1.8.0", 2),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            enpkg = Enpkg(repo, prefixes=[d], hook=None,
                          evt_mgr=None, verbose=False)
            with self.assertRaises(EnpkgError):
                enpkg.remove_actions("numpy")

    def test_chained_override_update(self):
        """ Test update to package with latest version in lower prefix
        but an older version in primary prefix.
        """
        l0_egg = NOSE_1_3_0
        l1_egg = NOSE_1_2_1

        expected_actions = [
            ('fetch_0', os.path.basename(l0_egg)),
            ('remove', os.path.basename(l1_egg)),
            ('install', os.path.basename(l0_egg)),
        ]

        entries = [
            dummy_enpkg_entry_factory(*split_eggname(os.path.basename(l0_egg))),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mkdtemp() as d:
            l0 = os.path.join(d, 'l0')
            l1 = os.path.join(d, 'l1')
            makedirs(l0)
            makedirs(l1)

            # Install latest version in l0
            EggInst(l0_egg, l0).install()
            # Install older version in l1
            EggInst(l1_egg, l1).install()

            local_repo = JoinedEggCollection([EggCollection(l1, False, None),
                                              EggCollection(l0, False, None)])
            enpkg = Enpkg(repo, prefixes=[l1, l0], hook=None,
                          evt_mgr=None, verbose=False)
            enpkg.ec = local_repo

            actions = enpkg.install_actions("nose")
            self.assertListEqual(actions, expected_actions)


class TestEnpkgExecute(unittest.TestCase):
    def setUp(self):
        self.prefixes = [tempfile.mkdtemp()]

    def tearDown(self):
        for prefix in self.prefixes:
            shutil.rmtree(prefix)

    def test_simple_fetch(self):
        egg = "yoyo.egg"
        fetch_opcode = 0

        repo = MetadataOnlyStore([])
        repo.connect()

        with mock.patch("enstaller.enpkg.Enpkg.fetch") as mocked_fetch:
            enpkg = Enpkg(repo, prefixes=self.prefixes, hook=None,
                          evt_mgr=None, verbose=False)
            enpkg.ec = mock.MagicMock()
            enpkg.execute([("fetch_{0}".format(fetch_opcode), egg)])

            self.assertTrue(mocked_fetch.called)
            mocked_fetch.assert_called_with(egg, force=fetch_opcode)

    def test_simple_install(self):
        egg = DUMMY_EGG
        base_egg = os.path.basename(egg)
        fetch_opcode = 0

        entries = [
            EnpkgS3IndexEntry(product="free", build=1,
                              egg_basename="dummy", version="1.0.1",
                              available=True),
        ]

        repo = MetadataOnlyStore(entries)
        repo.connect()

        with mock.patch("enstaller.enpkg.Enpkg.fetch") as mocked_fetch:
            enpkg = Enpkg(repo, prefixes=self.prefixes, hook=None,
                          evt_mgr=None, verbose=False)
            local_repo = JoinedEggCollection([
                EggCollection(prefix, False, None) for prefix in
                self.prefixes])
            local_repo.install = mock.MagicMock()
            enpkg.ec = local_repo

            actions = enpkg.install_actions("dummy")
            enpkg.execute(actions)

            mocked_fetch.assert_called_with(base_egg, force=fetch_opcode)
            local_repo.install.assert_called_with(base_egg, enpkg.local_dir,
                                                  None)

class TestEnpkgRevert(unittest.TestCase):
    def setUp(self):
        self.prefixes = [tempfile.mkdtemp()]

    def tearDown(self):
        for prefix in self.prefixes:
            shutil.rmtree(prefix)

    def test_empty_history(self):
        repo = EggsStore([])
        repo.connect()

        enpkg = Enpkg(repo, prefixes=self.prefixes, hook=None,
                      evt_mgr=None, verbose=False)
        enpkg.revert_actions(0)

        with self.assertRaises(EnpkgError):
            enpkg.revert_actions(1)

    def test_simple_scenario(self):
        egg = DUMMY_EGG
        r_actions = {1: [], 0: [("remove", os.path.basename(egg))]}

        repo = EggsStore([egg])
        repo.connect()

        enpkg = Enpkg(repo, prefixes=self.prefixes, hook=None,
                      evt_mgr=None, verbose=False)
        actions = enpkg.install_actions("dummy")
        enpkg.execute(actions)

        self.assertIsNotNone(enpkg.find(os.path.basename(egg)))

        for state in [0, 1]:
            actions = enpkg.revert_actions(state)
            self.assertEqual(actions, r_actions[state])
