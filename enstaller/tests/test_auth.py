import os.path
import shutil
import sys
import tempfile

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

from mock import patch

import enstaller.config

from enstaller.config import Configuration
from enstaller.errors import AuthFailedError, InvalidConfiguration


basic_user = dict(first_name="Jane", last_name="Doe", is_authenticated=True,
        has_subscription=True)
free_user = dict(first_name="John", last_name="Smith", is_authenticated=True,
        has_subscription=False)
anon_user = dict(is_authenticated=False)
old_auth_user = {}


class CheckedChangeAuthTestCase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "enstaller4rc")

    def tearDown(self):
        shutil.rmtree(self.d)

    @patch('enstaller.config.authenticate', return_value=basic_user)
    def test_simple(self, mock1):
        config = Configuration()
        config.set_auth('usr', 'password')
        config._checked_change_auth(self.f)

        new_config = Configuration.from_file(self.f)
        usr = enstaller.config.authenticate(new_config)

        self.assertTrue(usr.get('is_authenticated'))
        self.assertTrue(usr.get('has_subscription'))

    @patch('enstaller.config.authenticate',
            side_effect=AuthFailedError())
    def test_no_acct(self, mock1):
        config = Configuration()
        config.set_auth("usr", "password")

        usr = config._checked_change_auth(self.f)

        self.assertFalse(usr.get('is_authenticated', False))
        self.assertEqual(usr, {})

    @patch('enstaller.config.authenticate', return_value=old_auth_user)
    def test_remote_success(self, mock1):
        config = Configuration()
        config.set_auth("usr", "password")

        usr = config._checked_change_auth(self.f)
        self.assertEqual(usr, {})

    def test_nones(self):
        config = Configuration()

        with self.assertRaises(InvalidConfiguration):
            config.set_auth(None, None)

    @patch('enstaller.config.keyring')
    def test_empty_strings(self, mock1):
        config = Configuration()
        config.set_auth("", "")

        with self.assertRaises(InvalidConfiguration):
            config._checked_change_auth(self.f)


class SearchTestCase(unittest.TestCase):
    pass


class InstallTestCase(unittest.TestCase):
    pass


if __name__ == '__main__':
    unittest.main()
