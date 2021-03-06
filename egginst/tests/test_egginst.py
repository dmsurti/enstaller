import os
import os.path
import shutil
import subprocess
import sys
import tempfile

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import mock

from egginst.main import EggInst, get_installed, main
from egginst.testing_utils import slow, assert_same_fs
from egginst.utils import makedirs, zip_write_symlink, ZipFile

from egginst import eggmeta

from .common import DUMMY_EGG, DUMMY_EGG_WITH_APPINST, \
        DUMMY_EGG_WITH_ENTRY_POINTS, DUMMY_EGG_METADATA_FILES, \
        LEGACY_EGG_INFO_EGG, LEGACY_EGG_INFO_EGG_METADATA_FILES, \
        NOSE_1_3_0, PYTHON_VERSION, STANDARD_EGG, \
        STANDARD_EGG_METADATA_FILES, SUPPORT_SYMLINK, mkdtemp

def _create_egg_with_symlink(filename, name):
    with ZipFile(filename, "w") as fp:
        fp.writestr("EGG-INFO/usr/include/foo.h", "/* header */")
        zip_write_symlink(fp, "EGG-INFO/usr/HEADERS", "include")

class TestEggInst(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        makedirs(self.base_dir)
        self.prefix = os.path.join(self.base_dir, "prefix")

    def tearDown(self):
        shutil.rmtree(self.base_dir)

    @slow
    @unittest.skipIf(not SUPPORT_SYMLINK, "this platform does not support symlink")
    def test_symlink(self):
        """Test installing an egg with softlink in it."""
        egg_filename = os.path.join(self.base_dir, "foo-1.0.egg")
        _create_egg_with_symlink(egg_filename, "foo")

        installer = EggInst(egg_filename, prefix=self.prefix)
        installer.install()

        incdir = os.path.join(self.prefix, "include")
        header = os.path.join(incdir, "foo.h")
        link = os.path.join(self.prefix, "HEADERS")

        self.assertTrue(os.path.exists(header))
        self.assertTrue(os.path.exists(link))
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), "include")
        self.assertTrue(os.path.exists(os.path.join(link, "foo.h")))

class TestEggInstMain(unittest.TestCase):
    def test_print_version(self):
        # XXX: this is lousy test: we'd like to at least ensure we're printing
        # the correct version, but capturing the stdout is a bit tricky. Once
        # we replace print by proper logging, we should be able to do better.
        main(["--version"])

    def test_list(self):
        # XXX: this is lousy test: we'd like to at least ensure we're printing
        # the correct packages, but capturing the stdout is a bit tricky. Once
        # we replace print by proper logging, we should be able to do better.
        main(["--list"])

    def test_install_simple(self):
        with mkdtemp() as d:
            main([DUMMY_EGG, "--prefix={0}".format(d)])

            self.assertTrue(os.path.basename(DUMMY_EGG) in list(get_installed(d)))

            main(["-r", DUMMY_EGG, "--prefix={0}".format(d)])

            self.assertFalse(os.path.basename(DUMMY_EGG) in list(get_installed(d)))

    def test_get_installed(self):
        r_installed_eggs = sorted([
            os.path.basename(DUMMY_EGG),
            os.path.basename(DUMMY_EGG_WITH_ENTRY_POINTS),
        ])

        with mkdtemp() as d:
            egginst = EggInst(DUMMY_EGG, d)
            egginst.install()

            egginst = EggInst(DUMMY_EGG_WITH_ENTRY_POINTS, d)
            egginst.install()

            installed_eggs = list(get_installed(d))
            self.assertEqual(installed_eggs, r_installed_eggs)

class TestEggInstInstall(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        if os.environ.get("ENSTALLER_TEST_USE_VENV", None):
            cmd = ["venv", "-s", self.base_dir]
        else:
            cmd = ["virtualenv", "-p", sys.executable, self.base_dir]
        subprocess.check_call(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        if sys.platform == "win32":
            self.bindir = os.path.join(self.base_dir, "Scripts")
            self.executable = os.path.join(self.base_dir, "python")
            self.site_packages = os.path.join(self.base_dir, "lib", "site-packages")
        else:
            self.bindir = os.path.join(self.base_dir, "bin")
            self.executable = os.path.join(self.base_dir, "bin", "python")
            self.site_packages = os.path.join(self.base_dir, "lib", "python" + PYTHON_VERSION, "site-packages")

        self.meta_dir = os.path.join(self.base_dir, "EGG-INFO")

    def tearDown(self):
        shutil.rmtree(self.base_dir)

    @slow
    def test_simple(self):
        egginst = EggInst(DUMMY_EGG, self.base_dir)

        egginst.install()
        self.assertTrue(os.path.exists(os.path.join(self.site_packages, "dummy.py")))

        egginst.remove()
        self.assertFalse(os.path.exists(os.path.join(self.site_packages, "dummy.py")))

    @slow
    def test_entry_points(self):
        """
        Test we install console entry points correctly.
        """
        py_script = os.path.join(self.site_packages, "dummy.py")
        if sys.platform == "win32":
            wrapper_script = os.path.join(self.bindir, "dummy.exe")
        else:
            wrapper_script = os.path.join(self.bindir, "dummy")

        egginst = EggInst(DUMMY_EGG_WITH_ENTRY_POINTS, self.base_dir)

        egginst.install()
        self.assertTrue(os.path.exists(py_script))
        self.assertTrue(os.path.exists(wrapper_script))

        egginst.remove()
        self.assertFalse(os.path.exists(py_script))
        self.assertFalse(os.path.exists(wrapper_script))

    @slow
    def test_appinst(self):
        """
        Test we install appinst bits correctly.
        """
        egg_path = DUMMY_EGG_WITH_APPINST
        appinst_path = os.path.join(self.meta_dir, "dummy_with_appinst", eggmeta.APPINST_PATH)

        egginst = EggInst(egg_path, self.base_dir)

        with mock.patch("appinst.install_from_dat", autospec=True) as m:
            egginst.install()
            m.assert_called_with(appinst_path, self.base_dir)

        with mock.patch("appinst.uninstall_from_dat", autospec=True) as m:
            egginst.remove()
            m.assert_called_with(appinst_path, self.base_dir)

    @slow
    def test_old_appinst(self):
        """
        Test that we still work with old (<= 2.1.1) appinst, where
        [un]install_from_dat only takes one argument (no prefix).
        """
        egg_path = DUMMY_EGG_WITH_APPINST
        appinst_path = os.path.join(self.meta_dir, "dummy_with_appinst", eggmeta.APPINST_PATH)

        egginst = EggInst(egg_path, self.base_dir)

        def mocked_old_install_from_dat(x):
            pass
        def mocked_old_uninstall_from_dat(x):
            pass

        # XXX: we use autospec to enforce function taking exactly one argument,
        # otherwise the proper TypeError exception is not raised when calling
        # it with two arguments, which is how old vs new appinst is detected.
        with mock.patch("appinst.install_from_dat", autospec=mocked_old_install_from_dat) as m:
            egginst.install()
            m.assert_called_with(appinst_path)

        with mock.patch("appinst.uninstall_from_dat", autospec=mocked_old_uninstall_from_dat) as m:
            egginst.remove()
            m.assert_called_with(appinst_path)

class TestEggInfoInstall(unittest.TestCase):
    def setUp(self):
        self.base_dir = tempfile.mkdtemp()

        if sys.platform == "win32":
            self.bindir = os.path.join(self.base_dir, "Scripts")
            self.executable = os.path.join(self.base_dir, "python")
            self.site_packages = os.path.join(self.base_dir, "lib", "site-packages")
        else:
            self.bindir = os.path.join(self.base_dir, "bin")
            self.executable = os.path.join(self.base_dir, "bin", "python")
            self.site_packages = os.path.join(self.base_dir, "lib", "python" + PYTHON_VERSION, "site-packages")

        self.meta_dir = os.path.join(self.base_dir, "EGG-INFO")

    def tearDown(self):
        shutil.rmtree(self.base_dir)

    def test_is_custom_egg(self):
        r_output = [
            (STANDARD_EGG, False),
            (DUMMY_EGG_WITH_APPINST, True),
            (DUMMY_EGG, True),
        ]

        for egg, expected in r_output:
            self.assertEqual(eggmeta.is_custom_egg(egg), expected)

    def test_standard_egg(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "jinja2")
        egg_info_base = os.path.join(self.site_packages,
                                     "Jinja2-2.6-py2.7.egg-info")

        egg = STANDARD_EGG

        egginst = EggInst(egg, self.base_dir)
        egginst.install()

        # Check for files installed in $prefix/EGG-INFO
        for f in STANDARD_EGG_METADATA_FILES:
            path = os.path.join(custom_egg_info_base, f)
            self.assertTrue(os.path.exists(path))

        # Check for files installed in $site-packages/$package_egg_info-INFO
        for f in STANDARD_EGG_METADATA_FILES:
            path = os.path.join(egg_info_base, f)
            self.assertTrue(os.path.exists(path))

    def test_standard_egg_remove(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "jinja2")
        egg_info_base = os.path.join(self.site_packages,
                                     "Jinja2-2.6-py2.7.egg-info")
        egg = STANDARD_EGG

        with assert_same_fs(self, self.base_dir):
            egginst = EggInst(egg, self.base_dir)
            egginst.install()

            egginst.remove()


    def test_simple_custom_egg(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "dummy")
        egg_info_base = os.path.join(self.site_packages,
                                     "dummy-{0}.egg-info". \
                                     format("1.0.1-1"))
        egg = DUMMY_EGG

        egginst = EggInst(egg, self.base_dir)
        egginst.install()

        # Check for files installed in $prefix/EGG-INFO
        for f in DUMMY_EGG_METADATA_FILES:
            path = os.path.join(custom_egg_info_base, f)
            self.assertTrue(os.path.exists(path))

        # Check for files installed in $site-packages/$package_egg_info-INFO
        path = os.path.join(egg_info_base, "PKG-INFO")
        self.assertTrue(os.path.exists(path))

        path = os.path.join(egg_info_base, "spec/depend")
        self.assertFalse(os.path.exists(path))

        path = os.path.join(egg_info_base, "spec/summary")
        self.assertFalse(os.path.exists(path))

    def test_simple_custom_egg_remove(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "dummy")
        egg_info_base = os.path.join(self.site_packages,
                                     "dummy-{0}.egg-info". \
                                     format("1.0.1-1"))
        egg = DUMMY_EGG

        with assert_same_fs(self, self.base_dir):
            egginst = EggInst(egg, self.base_dir)
            egginst.install()
            egginst.remove()

    def test_custom_egg_with_usr_files(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "nose")
        egg_info_base = os.path.join(self.site_packages,
                                     "nose-{0}.egg-info". \
                                     format("1.3.0-1"))
        egg = NOSE_1_3_0

        egginst = EggInst(egg, self.base_dir)
        egginst.install()

        # Check for files installed in $prefix/EGG-INFO
        for f in DUMMY_EGG_METADATA_FILES:
            path = os.path.join(custom_egg_info_base, f)
            self.assertTrue(os.path.exists(path))

        # Check for files installed in $site-packages/$package_egg_info-INFO
        path = os.path.join(egg_info_base, "PKG-INFO")
        self.assertTrue(os.path.exists(path))

        path = os.path.join(egg_info_base, "spec/depend")
        self.assertFalse(os.path.exists(path))

        path = os.path.join(egg_info_base, "spec/summary")
        self.assertFalse(os.path.exists(path))

        path = os.path.join(egg_info_base, "usr/share/man/man1/nosetests.1")
        self.assertFalse(os.path.exists(path))

    def test_custom_egg_with_usr_files_remove(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "nose")
        egg_info_base = os.path.join(self.site_packages,
                                     "nose-{0}.egg-info". \
                                     format("1.3.0-1"))
        egg = NOSE_1_3_0

        with assert_same_fs(self, self.base_dir):
            egginst = EggInst(egg, self.base_dir)
            egginst.install()
            egginst.remove()

    def test_custom_egg_legacy_egg_info(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "flake8")
        egg_info_base = os.path.join(self.site_packages,
                                     "flake8-2.0.0-2.egg-info")
        legacy_egg_info_base = os.path.join(self.site_packages, "flake8.egg-info")

        custom_metadata = ("PKG-INFO.bak", "requires.txt", "spec/depend",
                "spec/summary")

        egg = LEGACY_EGG_INFO_EGG

        egginst = EggInst(egg, self.base_dir)
        egginst.install()

        # Check for files installed in $prefix/EGG-INFO
        for f in custom_metadata:
            path = os.path.join(custom_egg_info_base, f)
            self.assertTrue(os.path.exists(path))

        # Check for files installed in $site-packages/$package_egg_info-INFO
        for f in LEGACY_EGG_INFO_EGG_METADATA_FILES:
            path = os.path.join(egg_info_base, f)
            self.assertTrue(os.path.exists(path))

        for f in LEGACY_EGG_INFO_EGG_METADATA_FILES:
            path = os.path.join(legacy_egg_info_base, f)
            self.assertFalse(os.path.exists(path))

    def test_custom_egg_legacy_egg_info_remove(self):
        custom_egg_info_base = os.path.join(self.base_dir, "EGG-INFO", "flake9")
        egg_info_base = os.path.join(self.site_packages,
                                     "flake8-2.0.0-2.egg-info")
        legacy_egg_info_base = os.path.join(self.site_packages, "flake8.egg-info")
        egg = LEGACY_EGG_INFO_EGG

        with assert_same_fs(self, self.base_dir):
            egginst = EggInst(egg, self.base_dir)
            egginst.install()
            egginst.remove()
