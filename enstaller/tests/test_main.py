import errno
import functools
import os.path
import re
import shutil
import sys
import tempfile
import textwrap

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

from cStringIO import StringIO

import mock

from okonomiyaki.repositories.enpkg import EnpkgS3IndexEntry, Dependency

from egginst.tests.common import mkdtemp, DUMMY_EGG

from enstaller.enpkg import Enpkg
from enstaller.eggcollect import EggCollection, JoinedEggCollection
from enstaller.main import disp_store_info, epd_install_confirm, info_option, \
    install_req, install_time_string, main, name_egg, print_installed, search, \
    updates_check, update_enstaller, whats_new
from enstaller.store.tests.common import MetadataOnlyStore

from .common import MetaOnlyEggCollection, dummy_enpkg_entry_factory, \
    dummy_installed_egg_factory, mock_print, patched_read, \
    dont_use_webservice, is_not_authenticated, is_authenticated, use_webservice

class TestEnstallerMainActions(unittest.TestCase):
    def test_print_version(self):
        # XXX: this is lousy test: we'd like to at least ensure we're printing
        # the correct version, but capturing the stdout is a bit tricky. Once
        # we replace print by proper logging, we should be able to do better.
        try:
            main(["--version"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

    def test_help_runs_and_exits_correctly(self):
        try:
            main(["--help"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

    def test_print_env(self):
        try:
            main(["--env"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

class TestEnstallerUpdate(unittest.TestCase):
    @mock.patch("enstaller.config.read", lambda: patched_read(autoupdate=False))
    def test_no_update_enstaller(self):
        enpkg = Enpkg()
        self.assertFalse(update_enstaller(enpkg, {}))

    def _test_update_enstaller(self, low_version, high_version):
        enstaller_eggs = [
            EnpkgS3IndexEntry(product="free", build=1,
                              egg_basename="enstaller", version=low_version,
                              available=True),
            EnpkgS3IndexEntry(product="free", build=1,
                              egg_basename="enstaller", version=high_version,
                              available=True),
        ]
        store = MetadataOnlyStore(enstaller_eggs)
        with mock.patch("__builtin__.raw_input", lambda ignored: "y"):
            with mock.patch("enstaller.main.install_req", lambda *args: None):
                enpkg = Enpkg(remote=store)
                opts = mock.Mock()
                opts.no_deps = False
                return update_enstaller(enpkg, opts)

    @mock.patch("enstaller.config.read", lambda: patched_read(autoupdate=True))
    @mock.patch("enstaller.__version__", "4.6.3")
    @mock.patch("enstaller.main.__ENSTALLER_VERSION__", "4.6.3")
    @mock.patch("enstaller.main.IS_RELEASED", True)
    def test_update_enstaller_higher_available(self):
        # low/high versions are below/above any realistic enstaller version
        low_version, high_version = "1.0.0", "666.0.0"
        self.assertTrue(self._test_update_enstaller(low_version, high_version))

    @mock.patch("enstaller.config.read", lambda: patched_read(autoupdate=True))
    @mock.patch("enstaller.__version__", "4.6.3")
    @mock.patch("enstaller.main.__ENSTALLER_VERSION__", "4.6.3")
    @mock.patch("enstaller.main.IS_RELEASED", True)
    def test_update_enstaller_higher_unavailable(self):
        # both low/high versions are below current enstaller version
        low_version, high_version = "1.0.0", "2.0.0"
        self.assertFalse(self._test_update_enstaller(low_version, high_version))

class TestMisc(unittest.TestCase):
    def test_disp_store_info(self):
        info = {"store_location": "https://api.enthought.com/eggs/osx-64/"}
        self.assertEqual(disp_store_info(info), "api osx-64")

        info = {"store_location": "https://api.enthought.com/eggs/win-32/"}
        self.assertEqual(disp_store_info(info), "api win-32")

        info = {}
        self.assertEqual(disp_store_info(info), "-")

    def test_name_egg(self):
        name = "foo-1.0.0-1.egg"
        self.assertEqual(name_egg(name), "foo")

        name = "fu_bar-1.0.0-1.egg"
        self.assertEqual(name_egg(name), "fu_bar")

        with self.assertRaises(AssertionError):
            name = "some/dir/fu_bar-1.0.0-1.egg"
            name_egg(name)

    def test_epd_install_confirm(self):
        for allowed_yes in ("y", "Y", "yes", "YES", "YeS"):
            with mock.patch("__builtin__.raw_input", lambda ignored: allowed_yes):
                self.assertTrue(epd_install_confirm())

        for non_yes in ("n", "N", "no", "NO", "dummy"):
            with mock.patch("__builtin__.raw_input", lambda ignored: non_yes):
                self.assertFalse(epd_install_confirm())

def _create_prefix_with_eggs(prefix, installed_entries=None, remote_entries=None):
    if remote_entries is None:
        remote_entries = []
    if installed_entries is None:
        installed_entries = []

    repo = MetadataOnlyStore(remote_entries)
    repo.connect()

    enpkg = Enpkg(repo, prefixes=[prefix], hook=None,
                  evt_mgr=None, verbose=False)
    enpkg.ec = JoinedEggCollection([
        MetaOnlyEggCollection(installed_entries)])
    return enpkg

class TestInfoStrings(unittest.TestCase):
    def test_print_install_time(self):
        with mkdtemp() as d:
            installed_entries = [dummy_installed_egg_factory("dummy", "1.0.1", 1)]
            enpkg = _create_prefix_with_eggs(d, installed_entries)

            self.assertRegexpMatches(install_time_string(enpkg, "dummy"),
                                     "dummy-1.0.1-1.egg was installed on:")

            self.assertEqual(install_time_string(enpkg, "ddummy"), "")

    def test_info_option(self):
        with mkdtemp() as d:
            entries = [dummy_enpkg_entry_factory("enstaller", "4.6.2", 1),
                       dummy_enpkg_entry_factory("enstaller", "4.6.3", 1)]
            enpkg = _create_prefix_with_eggs(d, remote_entries=entries)

            info_option(enpkg, "enstaller")

    def test_print_installed(self):
        with mkdtemp() as d:
            r_out = """\
Name                 Version              Store
============================================================
dummy                1.0.1-1              -
"""
            installed_entries = [dummy_installed_egg_factory("dummy", "1.0.1", 1)]
            ec = EggCollection(d, False)
            ec.install(os.path.basename(DUMMY_EGG), os.path.dirname(DUMMY_EGG))

            with mock_print() as m:
                print_installed(d)
                self.assertEqual(m.value, r_out)

            r_out = """\
Name                 Version              Store
============================================================
"""

            with mock_print() as m:
                print_installed(d, pat=re.compile("no_dummy"))
                self.assertEqual(m.value, r_out)

class TestSearch(unittest.TestCase):
    @mock.patch("enstaller.config.read", lambda: patched_read(use_webservice=False))
    def test_no_installed(self):
        with mkdtemp() as d:
            # XXX: isn't there a better way to ensure ws at the end of a line
            # are not eaten away ?
            r_output = """\
Name                   Versions           Product              Note
================================================================================
another_dummy          2.0.0-1            commercial           DUMMY_ANCHOR
dummy                  0.9.8-1            commercial           DUMMY_ANCHOR
                       1.0.0-1            commercial           DUMMY_ANCHOR
""".replace("DUMMY_ANCHOR", "")
            entries = [dummy_enpkg_entry_factory("dummy", "1.0.0", 1),
                       dummy_enpkg_entry_factory("dummy", "0.9.8", 1),
                       dummy_enpkg_entry_factory("another_dummy", "2.0.0", 1)]
            enpkg = _create_prefix_with_eggs(d, remote_entries=entries)

            with mock_print() as m:
                search(enpkg)
                self.assertMultiLineEqual(m.value, r_output)

    @mock.patch("enstaller.config.read", lambda: patched_read(use_webservice=False))
    def test_installed(self):
        with mkdtemp() as d:
            r_output = """\
Name                   Versions           Product              Note
================================================================================
dummy                  0.9.8-1            commercial           DUMMY_ANCHOR
                     * 1.0.1-1            commercial           DUMMY_ANCHOR
""".replace("DUMMY_ANCHOR", "")
            entries = [dummy_enpkg_entry_factory("dummy", "1.0.1", 1),
                       dummy_enpkg_entry_factory("dummy", "0.9.8", 1)]
            installed_entries = [dummy_installed_egg_factory("dummy", "1.0.1", 1)]
            enpkg = _create_prefix_with_eggs(d, installed_entries, entries)

            with mock_print() as m:
                search(enpkg)
                self.assertMultiLineEqual(m.value, r_output)

    @mock.patch("enstaller.config.read", lambda: patched_read(use_webservice=False))
    def test_pattern(self):
        with mkdtemp() as d:
            r_output = """\
Name                   Versions           Product              Note
================================================================================
dummy                  0.9.8-1            commercial           DUMMY_ANCHOR
                     * 1.0.1-1            commercial           DUMMY_ANCHOR
""".replace("DUMMY_ANCHOR", "")
            entries = [dummy_enpkg_entry_factory("dummy", "1.0.1", 1),
                       dummy_enpkg_entry_factory("dummy", "0.9.8", 1),
                       dummy_enpkg_entry_factory("another_package", "2.0.0", 1)]
            installed_entries = [dummy_installed_egg_factory("dummy", "1.0.1", 1)]
            enpkg = _create_prefix_with_eggs(d, installed_entries, entries)

            with mock_print() as m:
                search(enpkg, pat=re.compile("dummy"))
                self.assertMultiLineEqual(m.value, r_output)

            r_output = """\
Name                   Versions           Product              Note
================================================================================
another_package        2.0.0-1            commercial           DUMMY_ANCHOR
dummy                  0.9.8-1            commercial           DUMMY_ANCHOR
                     * 1.0.1-1            commercial           DUMMY_ANCHOR
""".replace("DUMMY_ANCHOR", "")
            with mock_print() as m:
                search(enpkg, pat=re.compile(".*"))
                self.assertMultiLineEqual(m.value, r_output)

    @mock.patch("enstaller.config.read", lambda: patched_read(use_webservice=True))
    def test_not_available(self):
        r_output = """\
Name                   Versions           Product              Note
================================================================================
another_package        2.0.0-1            commercial           not subscribed to
dummy                  0.9.8-1            commercial           DUMMY_ANCHOR
                       1.0.1-1            commercial           DUMMY_ANCHOR

""".replace("DUMMY_ANCHOR", "")
        another_entry = dummy_enpkg_entry_factory("another_package", "2.0.0", 1)
        another_entry.available = False

        entries = [dummy_enpkg_entry_factory("dummy", "1.0.1", 1),
                   dummy_enpkg_entry_factory("dummy", "0.9.8", 1),
                   another_entry]

        with mock.patch("enstaller.main.config") as mocked_config:
            with mkdtemp() as d:
                with mock_print() as m:
                    attrs = {"subscription_message.return_value": ""}
                    mocked_config.configure_mock(**attrs)
                    enpkg = _create_prefix_with_eggs(d, remote_entries=entries)
                    search(enpkg)

                    self.assertMultiLineEqual(m.value, r_output)
                    self.assertTrue(mocked_config.subscription_message.called)

class TestUpdatesCheck(unittest.TestCase):
    def test_update_check_new_available(self):
        entries = [dummy_enpkg_entry_factory("dummy", "1.2.0", 1),
                   dummy_enpkg_entry_factory("dummy", "0.9.8", 1)]
        installed_entries = [
                dummy_installed_egg_factory("dummy", "1.0.1", 1)
        ]

        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries, entries)

            updates, EPD_update =  updates_check(enpkg)

            self.assertEqual(EPD_update, [])
            self.assertEqual(len(updates), 1)
            update0 = updates[0]
            self.assertEqual(update0.keys(), ["current", "update"])
            self.assertEqual(update0["current"]["version"], "1.0.1")
            self.assertEqual(update0["update"]["version"], "1.2.0")

    def test_update_check_no_new_available(self):
        entries = [dummy_enpkg_entry_factory("dummy", "1.0.0", 1),
                   dummy_enpkg_entry_factory("dummy", "0.9.8", 1)]
        installed_entries = [
                dummy_installed_egg_factory("dummy", "1.0.1", 1)
        ]

        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries, entries)

            updates, EPD_update =  updates_check(enpkg)

            self.assertEqual(EPD_update, [])
            self.assertEqual(updates, [])

    def test_update_check_no_available(self):
        installed_entries = [
                dummy_installed_egg_factory("dummy", "1.0.1", 1)
        ]
        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries)

            updates, EPD_update =  updates_check(enpkg)

            self.assertEqual(EPD_update, [])
            self.assertEqual(updates, [])

    def test_update_check_epd(self):
        installed_entries = [dummy_installed_egg_factory("EPD", "7.2", 1)]
        remote_entries = [dummy_enpkg_entry_factory("EPD", "7.3", 1)]

        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries, remote_entries)

            updates, EPD_update =  updates_check(enpkg)

            self.assertEqual(updates, [])
            self.assertEqual(len(EPD_update), 1)

            epd_update0 = EPD_update[0]
            self.assertEqual(epd_update0.keys(), ["current", "update"])
            self.assertEqual(epd_update0["current"]["version"], "7.2")
            self.assertEqual(epd_update0["update"]["version"], "7.3")

    def test_whats_new_no_new_epd(self):
        # XXX: fragile, as it depends on dict ordering from
        # EggCollection.query_installed. We should sort the output instead.
        r_output = """\
Name                 installed            available
============================================================
scipy                0.12.0-1             0.13.0-1
numpy                1.7.1-1              1.7.1-2
"""
        installed_entries = [
            dummy_installed_egg_factory("numpy", "1.7.1", 1),
            dummy_installed_egg_factory("scipy", "0.12.0", 1)
        ]
        remote_entries = [
            dummy_enpkg_entry_factory("numpy", "1.7.1", 2),
            dummy_enpkg_entry_factory("scipy", "0.13.0", 1)
        ]

        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries, remote_entries)

            with mock_print() as m:
                whats_new(enpkg)
                self.assertMultiLineEqual(m.value, r_output)

    def test_whats_new_new_epd(self):
        r_output = "EPD 7.3-2 is available. To update to it (with " \
                   "confirmation warning), run 'enpkg epd'.\n"
        installed_entries = [
            dummy_installed_egg_factory("EPD", "7.2", 1),
        ]
        remote_entries = [
            dummy_enpkg_entry_factory("EPD", "7.3", 2),
        ]

        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries, remote_entries)

            with mock_print() as m:
                whats_new(enpkg)
                self.assertMultiLineEqual(m.value, r_output)

    def test_whats_new_no_updates(self):
        r_output = "No new version of any installed package is available\n"

        installed_entries = [
            dummy_installed_egg_factory("numpy", "1.7.1", 2),
            dummy_installed_egg_factory("scipy", "0.13.0", 1)
        ]
        remote_entries = [
            dummy_enpkg_entry_factory("numpy", "1.7.1", 1),
            dummy_enpkg_entry_factory("scipy", "0.12.0", 1)
        ]

        with mkdtemp() as d:
            enpkg = _create_prefix_with_eggs(d, installed_entries, remote_entries)

            with mock_print() as m:
                whats_new(enpkg)
                self.assertMultiLineEqual(m.value, r_output)

class FakeOptions(object):
    def __init__(self):
        self.force = False
        self.forceall = False
        self.no_deps = False

class TestInstallReq(unittest.TestCase):
    def setUp(self):
        self.prefix = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.prefix)

    def test_simple_install(self):
        remote_entries = [
            dummy_enpkg_entry_factory("nose", "1.3.0", 1)
        ]

        with mock.patch("enstaller.main.Enpkg.execute") as m:
            enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)
            install_req(enpkg, "nose", FakeOptions())
            m.assert_called_with([('fetch_0', 'nose-1.3.0-1.egg'),
                                  ('install', 'nose-1.3.0-1.egg')])

    def test_simple_non_existing_requirement(self):
        r_error_string = "No egg found for requirement 'nono_le_petit_robot'.\n"
        non_existing_requirement = "nono_le_petit_robot"

        with mock.patch("enstaller.main.Enpkg.execute") as mocked_execute:
            enpkg = _create_prefix_with_eggs(self.prefix, [])
            with mock_print() as mocked_print:
                with self.assertRaises(SystemExit) as e:
                    install_req(enpkg, non_existing_requirement, FakeOptions())
                self.assertEqual(e.exception.code, 1)
                self.assertEqual(mocked_print.value, r_error_string)
            mocked_execute.assert_not_called()

    def test_simple_no_install_needed(self):
        installed_entries = [
            dummy_installed_egg_factory("nose", "1.3.0", 1)
        ]
        remote_entries = [
            dummy_enpkg_entry_factory("nose", "1.3.0", 1)
        ]

        with mock.patch("enstaller.main.Enpkg.execute") as m:
            enpkg = _create_prefix_with_eggs(self.prefix, installed_entries, remote_entries)
            install_req(enpkg, "nose", FakeOptions())
            m.assert_called_with([])

    @is_authenticated
    @use_webservice
    def test_install_not_available(self):
        nose = dummy_enpkg_entry_factory("nose", "1.3.0", 1)
        nose.available = False
        remote_entries = [nose]

        enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)

        with mock.patch("enstaller.main.Enpkg.execute"):
            with mock.patch("enstaller.config.subscription_message") as subscription_message:
                with self.assertRaises(SystemExit) as e:
                    install_req(enpkg, "nose", FakeOptions())
                subscription_message.assert_called()
                self.assertEqual(e.exception.code, 1)

    @is_not_authenticated
    @use_webservice
    @mock.patch("enstaller.config.input_auth", lambda: (None, None))
    def test_install_not_available_not_authenticated(self):
        nose = dummy_enpkg_entry_factory("nose", "1.3.0", 1)
        nose.available = False
        remote_entries = [nose]

        enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)

        with mock.patch("enstaller.main.Enpkg.execute"):
            with mock.patch("enstaller.config.checked_change_auth") as m:
                with self.assertRaises(SystemExit) as e:
                    install_req(enpkg, "nose", FakeOptions())
                m.assert_called_with(None, None)
                self.assertEqual(e.exception.code, 1)

    @is_authenticated
    @use_webservice
    def test_recursive_install_unavailable_dependency(self):
        r_output = textwrap.dedent("""\
        Error: could not resolve "numpy 1.7.1" required by "scipy-0.12.0-1.egg"
        You may be able to force an install of just this egg by using the
        --no-deps enpkg commandline argument after installing another version
        of the dependency.
        Available versions of the required package 'numpy' are:
            1.7.1 (no subscription)
        You are logged in as None.
        Subscription level: EPD
        """)

        self.maxDiff = None
        numpy = dummy_enpkg_entry_factory("numpy", "1.7.1", 1)
        numpy.available = False
        scipy = dummy_enpkg_entry_factory("scipy", "0.12.0", 1)
        scipy.packages = [Dependency.from_spec_string("numpy 1.7.1")]

        remote_entries = [numpy, scipy]

        with mock.patch("enstaller.main.Enpkg.execute"):
            enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)
            with mock_print() as m:
                with self.assertRaises(SystemExit):
                    install_req(enpkg, "scipy", FakeOptions())
                self.assertMultiLineEqual(m.value, r_output)

    @is_not_authenticated
    @dont_use_webservice
    def test_recursive_install_unavailable_dependency_non_authenticated(self):
        numpy = dummy_enpkg_entry_factory("numpy", "1.7.1", 1)
        numpy.available = False
        scipy = dummy_enpkg_entry_factory("scipy", "0.12.0", 1)
        scipy.packages = [Dependency.from_spec_string("numpy 1.7.1")]

        remote_entries = [numpy, scipy]

        with mock.patch("enstaller.main.Enpkg.execute"):
            with mock.patch("enstaller.config.subscription_message") as m:
                enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)
                with self.assertRaises(SystemExit):
                    install_req(enpkg, "scipy", FakeOptions())
                m.assert_not_called()

    @mock.patch("sys.platform", "darwin")
    def test_os_error_darwin(self):
        remote_entries = [
            dummy_enpkg_entry_factory("nose", "1.3.0", 1)
        ]

        with mock.patch("enstaller.main.Enpkg.execute") as m:
            error = OSError()
            error.errno = errno.EACCES
            m.side_effect = error
            enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)
            with self.assertRaises(SystemExit) as e:
                install_req(enpkg, "nose", FakeOptions())

    @mock.patch("sys.platform", "linux2")
    def test_os_error(self):
        remote_entries = [
            dummy_enpkg_entry_factory("nose", "1.3.0", 1)
        ]

        with mock.patch("enstaller.main.Enpkg.execute") as m:
            m.side_effect = OSError()
            enpkg = _create_prefix_with_eggs(self.prefix, [], remote_entries)
            with self.assertRaises(OSError) as e:
                install_req(enpkg, "nose", FakeOptions())
