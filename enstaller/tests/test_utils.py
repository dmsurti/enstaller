import os.path
import random
import sys
import tempfile

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import mock

from egginst.main import name_version_fn
from egginst.tests.common import DUMMY_EGG_SIZE, DUMMY_EGG, \
    DUMMY_EGG_MTIME, DUMMY_EGG_MD5

from enstaller.utils import canonical, comparable_version, path_to_uri, \
    uri_to_path, info_file, cleanup_url, exit_if_sudo_on_venv

class TestUtils(unittest.TestCase):

    def test_canonical(self):
        for name, cname in [
            ('NumPy', 'numpy'),
            ('MySql-python', 'mysql_python'),
            ('Python-dateutil', 'python_dateutil'),
            ]:
            self.assertEqual(canonical(name), cname)

    def test_naming(self):
        for fn, name, ver, cname in [
            ('NumPy-1.5-py2.6-win32.egg', 'NumPy', '1.5-py2.6-win32', 'numpy'),
            ('NumPy-1.5-2.egg', 'NumPy', '1.5-2', 'numpy'),
            ('NumPy-1.5.egg', 'NumPy', '1.5', 'numpy'),
            ]:
            self.assertEqual(name_version_fn(fn), (name, ver))
            self.assertEqual(name.lower(), cname)
            self.assertEqual(canonical(name), cname)

    def test_comparable_version(self):
        for versions in (
            ['1.0.4', '1.2.1', '1.3.0b1', '1.3.0', '1.3.10',
             '1.3.11.dev7', '1.3.11.dev12', '1.3.11.dev111',
             '1.3.11', '1.3.143',
             '1.4.0.dev7749', '1.4.0rc1', '1.4.0rc2', '1.4.0'],
            ['2008j', '2008k', '2009b', '2009h', '2010b'],
            ['0.99', '1.0a2', '1.0b1', '1.0rc1', '1.0', '1.0.1'],
            ['2.0.8', '2.0.10', '2.0.10.1', '2.0.11'],
            ['0.10.1', '0.10.2', '0.11.dev1324', '0.11'],
            ):
            org = list(versions)
            random.shuffle(versions)
            versions.sort(key=comparable_version)
            self.assertEqual(versions, org)

    def test_info_file(self):
        r_info = {
                "size": DUMMY_EGG_SIZE,
                "mtime": DUMMY_EGG_MTIME,
                "md5": DUMMY_EGG_MD5
        }

        info = info_file(DUMMY_EGG)
        self.assertEqual(info, r_info)

    def test_cleanup_url(self):
        r_data = [
            ("http://www.acme.com/", "http://www.acme.com/"),
            ("http://www.acme.com", "http://www.acme.com/"),
            ("file:///foo/bar", "file:///foo/bar/"),
        ]

        for url, r_url in r_data:
            self.assertEqual(cleanup_url(url), r_url)

    @unittest.skipIf(sys.platform=="win32", "cleanup_url is utterly broken on windows.")
    def test_cleanup_url_dir(self):
        r_url = "file://{0}/".format(os.path.abspath(os.path.expanduser("~")))

        url = "~"

        self.assertEqual(cleanup_url(url), r_url)
        self.assertRaises(Exception, lambda: cleanup_url("/fofo/nar/does_not_exist"))

    @unittest.expectedFailure
    def test_cleanup_url_relative_path(self):
        url, r_url = "file://foo/bar", "file://foo/bar/"

        self.assertEqual(cleanup_url(url), r_url)

    def test_cleanup_url_wrong_behavior(self):
        """This behavior is a consequence of the buggy behavior in
        cleanup_url."""
        url, r_url = "file://foo/bar", "file://foo/bar\\"

        self.assertEqual(cleanup_url(url), r_url)

class TestExitIfSudoOnVenv(unittest.TestCase):
    @mock.patch("enstaller.utils.sys.platform", "win32")
    def test_windows(self):
        exit_if_sudo_on_venv("some_prefix")

    @unittest.skipIf(sys.platform=="win32", "no getuid on windows")
    @mock.patch("enstaller.utils.sys.platform", "linux")
    @mock.patch("os.getuid", lambda: 0)
    def test_no_venv(self):
        exit_if_sudo_on_venv("some_prefix")

    @unittest.skipIf(sys.platform=="win32", "no getuid on windows")
    @mock.patch("enstaller.utils.sys.platform", "linux")
    @mock.patch("os.getuid", lambda: 0)
    def test_venv_sudo(self):
        d = tempfile.mkdtemp()
        pyvenv = os.path.join(d, "pyvenv.cfg")
        with open(pyvenv, "w") as fp:
            fp.write("")

        self.assertRaises(SystemExit, lambda: exit_if_sudo_on_venv(d))

    @unittest.skipIf(sys.platform=="win32", "no getuid on windows")
    @mock.patch("enstaller.utils.sys.platform", "linux")
    @mock.patch("os.getuid", lambda: 1)
    def test_venv_no_sudo(self):
        d = tempfile.mkdtemp()
        pyvenv = os.path.join(d, "pyvenv.cfg")
        with open(pyvenv, "w") as fp:
            fp.write("")

        exit_if_sudo_on_venv(d)

class TestUri(unittest.TestCase):
    def test_path_to_uri_simple(self):
        """Ensure path to uri conversion works."""
        # XXX: this is a bit ugly, but urllib does not allow to select which OS
        # we want (there is no 'nturllib' or 'posixurllib' as there is for path.
        if sys.platform == "win32":
            r_uri = "file:///C:/Users/vagrant/yo"
            uri = path_to_uri("C:\\Users\\vagrant\\yo")
        else:
            r_uri = "file:///home/vagrant/yo"
            uri = path_to_uri("/home/vagrant/yo")
        self.assertEqual(r_uri, uri)

    def test_uri_to_path_simple(self):
        if sys.platform == "win32":
            r_path = "C:\\Users\\vagrant\\yo"
            uri = "file:///C:/Users/vagrant/yo"
        else:
            r_path = "/home/vagrant/yo"
            uri = "file:///home/vagrant/yo"

        path = uri_to_path(uri)
        self.assertEqual(r_path, path)


if __name__ == '__main__':
    unittest.main()
