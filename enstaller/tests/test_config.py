import json
import os.path
import sys
import tempfile
import textwrap
import urllib2

from cStringIO import StringIO

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import mock

import enstaller.config

from enstaller.config import AuthFailedError, authenticate, change_auth, \
    clear_cache, get, get_auth, get_default_url, get_path, input_auth, \
    is_auth_configured, subscription_level, web_auth, write
from enstaller.config import PythonConfigurationParser

from .common import patched_read

def compute_creds(username, password):
    return "{0}:{1}".format(username, password).encode("base64").rstrip()

FAKE_USER = "john.doe"
FAKE_PASSWORD = "fake_password"
FAKE_CREDS = compute_creds(FAKE_USER, FAKE_PASSWORD)

class TestGetPath(unittest.TestCase):
    def test_home_config_exists(self):
        def mocked_isfile(p):
            if p == enstaller.config.home_config_path:
                return True
            else:
                return os.path.isfile(p)

        with mock.patch("enstaller.config.isfile", mocked_isfile):
            self.assertEqual(get_path(), enstaller.config.home_config_path)

    def test_home_config_doesnt_exist(self):
        def mocked_isfile(p):
            if p == enstaller.config.home_config_path:
                return False
            elif p == enstaller.config.system_config_path:
                return True
            else:
                return os.path.isfile(p)

        with mock.patch("enstaller.config.isfile", mocked_isfile):
            self.assertEqual(get_path(), enstaller.config.system_config_path)

    def test_no_config(self):
        def mocked_isfile(p):
            if p in (enstaller.config.home_config_path,
                     enstaller.config.system_config_path):
                return False
            else:
                return os.path.isfile(p)

        with mock.patch("enstaller.config.isfile", mocked_isfile):
            self.assertEqual(get_path(), None)

class TestInputAuth(unittest.TestCase):
    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    def test_simple(self):
        with mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER):
            self.assertEqual(input_auth(), (FAKE_USER, FAKE_PASSWORD))

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    def test_empty(self):
        with mock.patch("__builtin__.raw_input", lambda ignored: ""):
            self.assertEqual(input_auth(), (None, None))

class TestWriteConfig(unittest.TestCase):
    def tearDown(self):
        clear_cache()

    def _mocked_open_factory(self):
        f = tempfile.NamedTemporaryFile(delete=False)
        def mocked_open(ignored, ignored2):
            return f

        return mocked_open, f

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    @mock.patch("enstaller.config.keyring", None)
    @mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER)
    def test_cleared_cache(self):
        mocked_open, f = self._mocked_open_factory()
        with mock.patch("__builtin__.open", mocked_open):
            m = mock.MagicMock()
            with mock.patch("enstaller.config.clear_cache", m):
                write()
            self.assertTrue(m.called)

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    @mock.patch("enstaller.config.keyring", None)
    @mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER)
    def test_simple(self):
        mocked_open, f = self._mocked_open_factory()
        with mock.patch("__builtin__.open", mocked_open):
            write()

        with mock.patch("enstaller.config.get_path", lambda: f.name):
            self.assertEqual(get("EPD_auth"), FAKE_CREDS)
            self.assertEqual(get("autoupdate"), True)
            self.assertEqual(get("proxy"), None)
            self.assertEqual(get("use_webservice"), True)
            self.assertEqual(get("webservice_entry_point"), get_default_url())

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    @mock.patch("enstaller.config.keyring", None)
    @mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER)
    def test_simple_with_proxy(self):
        mocked_open, f = self._mocked_open_factory()
        with mock.patch("__builtin__.open", mocked_open):
            write(proxy="http://acme.com:3128")

        with mock.patch("enstaller.config.get_path", lambda: f.name):
            self.assertEqual(get("proxy"), "http://acme.com:3128")

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    @mock.patch("enstaller.config.keyring", None)
    @mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER)
    def test_simple_with_username_password(self):
        user, password = "dummy", "dummy"
        creds = "{0}:{1}".format(user, password).encode("base64").rstrip()

        mocked_open, f = self._mocked_open_factory()
        with mock.patch("__builtin__.open", mocked_open):
            write(username=user, password=password)

        with mock.patch("enstaller.config.get_path", lambda: f.name):
            self.assertEqual(get("EPD_auth"), creds)

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    @mock.patch("enstaller.config.keyring", None)
    @mock.patch("enstaller.config.sys.platform", "linux2")
    @mock.patch("enstaller.config.os.getuid", lambda: 0)
    @mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER)
    def test_use_system_path_under_root(self):
        with mock.patch("__builtin__.open") as m:
            write()
            self.assertEqual(m.call_args[0][0], enstaller.config.system_config_path)

    @mock.patch("enstaller.config.getpass", lambda ignored: FAKE_PASSWORD)
    @mock.patch("__builtin__.raw_input", lambda ignored: FAKE_USER)
    def test_keyring_call(self):
        with mock.patch("__builtin__.open"):
            mocked_keyring = mock.MagicMock()
            mocked_keyring.set_password = mock.MagicMock()
            with mock.patch("enstaller.config.keyring", mocked_keyring):
                write()
                self.assertEqual(mocked_keyring.set_password.call_args[0],
                                 ("Enthought.com", FAKE_USER, FAKE_PASSWORD))


AUTH_API_URL = 'https://api.enthought.com/accounts/user/info/'

R_JSON_AUTH_RESP = {'first_name': u'David',
        'has_subscription': True,
        'is_active': True,
        'is_authenticated': True,
        'last_name': u'Cournapeau',
        'subscription_level': u'basic'}

R_JSON_NOAUTH_RESP = {'is_authenticated': False,
        'last_name': u'Cournapeau',
        'subscription_level': u'basic'}

class TestWebAuth(unittest.TestCase):
    def test_invalid_auth_args(self):
        with self.assertRaises(AuthFailedError):
            web_auth((None, None))

    def test_simple(self):
        with mock.patch("enstaller.config.urllib2") as murllib2:
            attrs = {'urlopen.return_value': StringIO(json.dumps(R_JSON_AUTH_RESP))}
            murllib2.configure_mock(**attrs)
            self.assertEqual(web_auth((FAKE_USER, FAKE_PASSWORD)),
                             R_JSON_AUTH_RESP)

    def test_auth_encoding(self):
        r_headers = {"Authorization": "Basic " + FAKE_CREDS}
        with mock.patch("enstaller.config.urllib2") as murllib2:
            attrs = {'urlopen.return_value': StringIO(json.dumps(R_JSON_AUTH_RESP))}
            murllib2.configure_mock(**attrs)

            web_auth((FAKE_USER, FAKE_PASSWORD))
            murllib2.Request.assert_called_with(AUTH_API_URL, headers=r_headers)

    def test_urllib_failures(self):
        with mock.patch("enstaller.config.urllib2") as murllib2:
            # XXX: we can't rely on mock for exceptions, but there has to be a
            # better way ?
            murllib2.URLError = urllib2.URLError

            attrs = {'urlopen.side_effect': urllib2.URLError("dummy")}
            murllib2.configure_mock(**attrs)

            with self.assertRaises(AuthFailedError):
                web_auth((FAKE_USER, FAKE_PASSWORD))

        with mock.patch("enstaller.config.urllib2") as murllib2:
            murllib2.HTTPError = urllib2.URLError

            mocked_fp = mock.MagicMock()
            mocked_fp.read.side_effect = murllib2.HTTPError("dummy")
            attrs = {'urlopen.return_value': mocked_fp}
            murllib2.configure_mock(**attrs)

            with self.assertRaises(AuthFailedError):
                web_auth((FAKE_USER, FAKE_PASSWORD))

    def test_unauthenticated_user(self):
        with mock.patch("enstaller.config.urllib2") as murllib2:
            attrs = {'urlopen.return_value': StringIO(json.dumps(R_JSON_NOAUTH_RESP))}
            murllib2.configure_mock(**attrs)

            with self.assertRaises(AuthFailedError):
                web_auth((FAKE_USER, FAKE_PASSWORD))

class TestGetAuth(unittest.TestCase):
    def test_with_keyring(self):
        def mocked_get(arg):
            if arg == "EPD_auth":
                return None
            elif arg == "EPD_username":
                return FAKE_USER
            else:
                return get(arg)

        with mock.patch("enstaller.config.get", mocked_get):
            with mock.patch("enstaller.config.keyring") as mocked_keyring:
                attrs = {"get_password.return_value": FAKE_PASSWORD}
                mocked_keyring.configure_mock(**attrs)
                self.assertEqual(get_auth(), (FAKE_USER, FAKE_PASSWORD))
                mocked_keyring.get_password.assert_called_with("Enthought.com",
                                                               FAKE_USER)

    @mock.patch("enstaller.config.keyring", None)
    def test_with_auth(self):
        def mocked_get(arg):
            if arg == "EPD_auth":
                return FAKE_CREDS
            else:
                return get(arg)

        with mock.patch("enstaller.config.get", mocked_get):
            self.assertEqual(get_auth(), (FAKE_USER, FAKE_PASSWORD))

    def test_with_auth_and_keyring(self):
        def mocked_get(arg):
            if arg == "EPD_auth":
                return FAKE_CREDS
            else:
                return get(arg)

        with mock.patch("enstaller.config.get", mocked_get):
            mocked_keyring = mock.Mock(["get_password"])
            with mock.patch("enstaller.config.keyring", mocked_keyring):
                self.assertFalse(mocked_keyring.get_password.called)
                self.assertEqual(get_auth(), (FAKE_USER, FAKE_PASSWORD))

    @mock.patch("enstaller.config.keyring", None)
    def test_without_auth_or_keyring(self):
        def mocked_get(arg):
            if arg in ("EPD_auth", "EPD_username"):
                return None
            else:
                return get(arg)

        with mock.patch("enstaller.config.get", mocked_get):
            self.assertEqual(get_auth(), (None, None))

class TestChangeAuth(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    @mock.patch("enstaller.config.keyring", None)
    def test_change_existing_config_file(self):
        r_new_password = "ouioui_dans_sa_petite_voiture"
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write("EPD_auth = '{0}'".format(FAKE_CREDS))

        with mock.patch("enstaller.config.get_path", lambda: fp.name):
            self.assertEqual(get_auth(), (FAKE_USER, FAKE_PASSWORD))
            change_auth(FAKE_USER, r_new_password)
            self.assertEqual(get_auth(), (FAKE_USER, r_new_password))

    @mock.patch("enstaller.config.keyring", None)
    def test_change_existing_config_file_empty_username(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write("EPD_auth = '{0}'".format(FAKE_CREDS))

        with mock.patch("enstaller.config.get_path", lambda: fp.name):
            self.assertEqual(get_auth(), (FAKE_USER, FAKE_PASSWORD))
            change_auth("", "dummy")
            self.assertEqual(get_auth(), (None, None))

    def test_change_existing_config_file_with_keyring(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write("EPD_auth = '{0}'".format(FAKE_CREDS))

        with mock.patch("enstaller.config.keyring") as mocked_keyring:
            with mock.patch("enstaller.config.get_path", lambda: fp.name):
                change_auth("user", "dummy")
                mocked_keyring.set_password.assert_called_with("Enthought.com", "user", "dummy")

        with open(fp.name, "rt") as f:
            self.assertRegexpMatches(f.read(), "EPD_username")
            self.assertNotRegexpMatches(f.read(), "EPD_auth")


    @mock.patch("enstaller.config.keyring", None)
    def test_change_empty_config_file_empty_username(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write("")

        with mock.patch("enstaller.config.get_path", lambda: fp.name):
            self.assertEqual(get_auth(), (None, None))
            change_auth(FAKE_USER, FAKE_PASSWORD)
            self.assertEqual(get_auth(), (FAKE_USER, FAKE_PASSWORD))

    @mock.patch("enstaller.config.keyring", None)
    def test_no_config_file(self):
        with mock.patch("enstaller.config.get_path", lambda: None):
            with mock.patch("enstaller.config.write") as m:
                self.assertEqual(get_auth(), (None, None))
                change_auth(FAKE_USER, FAKE_PASSWORD)
                m.assert_called_with(FAKE_USER, FAKE_PASSWORD)

    @mock.patch("enstaller.config.keyring", None)
    def test_change_config_file_empty_auth(self):
        config_data = "EPD_auth = '{0}'".format(FAKE_CREDS)
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write(config_data)

        with mock.patch("enstaller.config.get_path", lambda: fp.name):
            with mock.patch("enstaller.config.write") as m:
                change_auth(None, None)
                self.assertFalse(m.called)

                with open(fp.name, "rt") as fp:
                    self.assertEqual(fp.read(), config_data)

class TestAuthenticate(unittest.TestCase):
    @mock.patch("enstaller.config.read",
                lambda: patched_read(use_webservice=True))
    def test_use_webservice_valid_user(self):
        with mock.patch("enstaller.config.web_auth") as mocked_auth:
            authenticate((FAKE_USER, FAKE_PASSWORD))
            self.assertTrue(mocked_auth.called)

    @mock.patch("enstaller.config.read",
                lambda: patched_read(use_webservice=True))
    def test_use_webservice_invalid_user(self):
        with mock.patch("enstaller.config.web_auth") as mocked_auth:
            mocked_auth.return_value = {"is_authenticated": False}

            with self.assertRaises(AuthFailedError):
                authenticate((FAKE_USER, FAKE_PASSWORD))

    @mock.patch("enstaller.config.read",
                lambda: patched_read(use_webservice=False))
    def test_use_remote(self):
        remote = mock.Mock()
        user = authenticate((FAKE_USER, FAKE_PASSWORD), remote)
        self.assertEqual(user, {"is_authenticated": True})

    @mock.patch("enstaller.config.read",
                lambda: patched_read(use_webservice=False))
    def test_use_remote_invalid(self):
        remote = mock.Mock()

        for klass in KeyError, Exception:
            attrs = {"connect.side_effect": klass()}
            remote.configure_mock(**attrs)

            with self.assertRaises(AuthFailedError):
                authenticate((FAKE_USER, FAKE_PASSWORD), remote)

class TestSubscriptionLevel(unittest.TestCase):
    def test_unsubscribed_user(self):
        user_info = {"is_authenticated": True}
        self.assertEqual(subscription_level(user_info), "EPD")

        user_info = {"is_authenticated": False}
        self.assertIsNone(subscription_level(user_info))

    def test_subscribed_user(self):
        user_info = {"has_subscription": True, "is_authenticated": True}
        self.assertEqual(subscription_level(user_info), "EPD Basic or above")

        user_info = {"has_subscription": False, "is_authenticated": True}
        self.assertEqual(subscription_level(user_info), "EPD Free")

        user_info = {"has_subscription": False, "is_authenticated": False}
        self.assertIsNone(subscription_level(user_info))

class TestAuthenticationConfiguration(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    @mock.patch("enstaller.config.keyring", None)
    def test_without_configuration_no_keyring(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write("")

        with mock.patch("enstaller.config.get_path", lambda: fp.name):
            self.assertFalse(is_auth_configured())

    def test_without_configuration_with_keyring(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            fp.write("")

        with mock.patch("enstaller.config.keyring"):
            with mock.patch("enstaller.config.get_path", lambda: fp.name):
                self.assertFalse(is_auth_configured())

    @mock.patch("enstaller.config.keyring", None)
    def test_with_configuration_no_keyring(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            auth_line = "EPD_auth = '{0}'".format(FAKE_CREDS)
            fp.write(auth_line)

        with mock.patch("enstaller.config.get_path", lambda: fp.name):
            self.assertTrue(is_auth_configured())

    def test_with_configuration_with_keyring(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            auth_line = "EPD_username = '{0}'".format(FAKE_USER)
            fp.write(auth_line)

        mocked_keyring = mock.Mock(["get_password"])
        with mock.patch("enstaller.config.keyring", mocked_keyring):
            with mock.patch("enstaller.config.get_path", lambda: fp.name):
                self.assertTrue(is_auth_configured())

class TestConfigurationParsing(unittest.TestCase):
    def test_parse_simple(self):
        r_data = {"IndexedRepos": ["http://acme.com/{SUBDIR}"],
                  "webservice_entry_point": "http://acme.com/eggs/{PLATFORM}/"}

        s = textwrap.dedent("""\
        IndexedRepos = [
            "http://acme.com/{SUBDIR}",
        ]
        webservice_entry_point = "http://acme.com/eggs/{PLATFORM}/"
        """)

        data = PythonConfigurationParser().parse(s)
        self.assertEqual(data, r_data)
