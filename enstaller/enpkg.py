import sys
import warnings
import requests
from uuid import uuid4
from os.path import isdir, isfile, join
import os
import plat
import threading

import enstaller
import config

from store.indexed import LocalIndexedStore, RemoteHTTPIndexedStore
from store.joined import JoinedStore

from eggcollect import EggCollection, JoinedEggCollection

from resolve import Req, Resolve, comparable_info
from fetch import FetchAPI
from egg_meta import is_valid_eggname, split_eggname
from history import History

from grits_client.storage.client_store import GritsClientStore


# Included for backward compatibility
from enstaller.config import get_default_url

def create_joined_store(urls):
    stores = []
    for url in urls:
        if url.startswith('file://'):
            stores.append(LocalIndexedStore(url[7:]))
        elif url.startswith(('http://', 'https://')):
            stores.append(RemoteHTTPIndexedStore(url))
        elif isdir(url):
            stores.append(LocalIndexedStore(url))
        else:
            raise Exception("cannot create store: %r" % url)
    return JoinedStore(stores)


def get_default_kvs():
    url = enstaller.config.read()['webservice_entry_point']
    return RemoteHTTPIndexedStore(url)


def req_from_anything(arg):
    if isinstance(arg, Req):
        return arg
    if is_valid_eggname(arg):
        return Req('%s %s-%d' % split_eggname(arg))
    return Req(arg)


def get_package_path(prefix):
    """Return site-packages path for the given repo prefix.

    Note: on windows the path is lowercased and returned.
    """
    if sys.platform == 'win32':
        return join(prefix, 'Lib', 'site-packages').lower()
    else:
        postfix = 'lib/python{0}.{1}/site-packages'.format(*sys.version_info)
        return join(prefix, postfix)


def check_prefixes(prefixes):
    """
    Check that package prefixes lead to site-packages that are on the python
    path and that the order of the prefixes matches the python path.
    """
    index_order = []
    if sys.platform == 'win32':
        sys_path = [x.lower() for x in sys.path]
    else:
        sys_path = sys.path
    for prefix in prefixes:
        path = get_package_path(prefix)
        try:
            index_order.append(sys_path.index(path))
        except ValueError:
            warnings.warn("Expected to find %s in PYTHONPATH" % path)
            break
    else:
        if not index_order == sorted(index_order):
            warnings.warn("Order of path prefixes doesn't match PYTHONPATH")

def get_writable_local_dir(prefix):
    local_dir = join(prefix, 'LOCAL-REPO')
    if not os.access(local_dir, os.F_OK):
        try:
            os.makedirs(local_dir)
            return local_dir
        except (OSError, IOError) as e:
            pass
    elif os.access(local_dir, os.W_OK):
        return local_dir

    import tempfile
    print ('Warning: Python prefix directory is not writeable '
           'with current permissions:\n'
           '    %s\n'
           'Using a temporary cache for index and eggs.\n' %
           prefix)
    return tempfile.mkdtemp()


class EnpkgError(Exception):
    req = None


class GritsEggStore(GritsClientStore):
    def __init__(self, url):
        super(GritsEggStore, self).__init__(url)
        self.metadata_cache = {}

    def connect(self, creds):
        GritsClientStore.connect(self, creds)

    def query(self, **kwargs):
        kwargs['platform'] = plat.custom_plat
        ret = [(self.egg_name(k), self._default_metadata(v))
               for k, v in super(GritsEggStore, self).query(**kwargs)]
        self.metadata_cache.update(dict(ret))
        return ret

    def get(self, egg):
        return super(GritsEggStore, self).get(self.key_name(egg))

    def get_data(self, egg):
        return super(GritsEggStore, self).get_data(self.key_name(egg))

    def get_metadata(self, egg):
        if egg in self.metadata_cache:
            return self.metadata_cache[egg]
        else:
            metadata = self._default_metadata(super(GritsEggStore, self).
                                              get_metadata(self.key_name(egg)))
            self.metadata_cache[egg] = metadata
            return metadata

    @staticmethod
    def _default_metadata(metadata):
        metadata.setdefault('type', 'egg')
        metadata.setdefault('python', '2.7')
        metadata.setdefault('packages', [])
        return metadata

    @staticmethod
    def egg_name(key):
        return key.split('/')[-1]

    @staticmethod
    def key_name(egg):
        return 'enthought/eggs/{}/{}'.format(plat.custom_plat, egg)


def get_default_remote(prefixes):
    def _remote_store():
        web_url = enstaller.config.read()['webservice_entry_point']
        local_dir = get_writable_local_dir(prefixes[0])
        return RemoteHTTPIndexedStore(web_url, local_dir)

    grits_url = enstaller.config.read()['query_entry_point']
    try:
        if requests.get(grits_url + '/available').status_code == 200:
            return GritsEggStore(grits_url)
        else:
            return _remote_store()
    except:
        return _remote_store()


class Enpkg(object):
    """
    This is main interface for using enpkg, it is used by the CLI.
    Arguments for object creation:

    remote: key-value store (KVS) instance
        This is the KVS which enpkg will try to connect to for querying
        and fetching eggs.

    All remaining arguments are optional.

    userpass: tuple(username, password) -- default, see below
        these credentials are used when the remote KVS instance is being
        connected.
        By default the credentials are obtained from config.get_auth(),
        which might use the keyring package.

    prefixes: list of path -- default: [sys.prefix]
        Each path, is an install "prefix" (such as, e.g. /usr/local)
        in which things get installed.
        Eggs are installed or removed from the first prefix in the list.

    hook: boolean -- default: False
        Usually eggs are installed into the site-packages directory of the
        corresponding prefix (e.g. /usr/local/lib/python2.7/site-packages).
        When hook is set to True, eggs are installed into "versioned" egg
        directories, for special usage with import hooks (hence the name).

    evt_mgr: encore event manager instance -- default: None
        Various progress events (e.g. for download, install, ...) are being
        emitted to the event manager.  By default, a simple progress bar
        is displayed on the console (which does not use the event manager
        at all).
    """
    def __init__(self, remote=None, userpass='<config>', prefixes=[sys.prefix],
                 hook=False, evt_mgr=None, verbose=False):
        self.local_dir = get_writable_local_dir(prefixes[0])
        if remote is None:
            self.remote = get_default_remote(prefixes)
        else:
            self.remote = remote
        if userpass == '<config>':
            self.userpass = config.get_auth()
        else:
            self.userpass = userpass

        check_prefixes(prefixes)
        self.prefixes = prefixes
        self.hook = hook
        self.evt_mgr = evt_mgr
        self.verbose = verbose

        self.ec = JoinedEggCollection([
                EggCollection(prefix, self.hook, self.evt_mgr)
                for prefix in self.prefixes])
        self._connected = False
        self._execution_aborted = threading.Event()

    # ============= methods which relate to remove store =================

    def reconnect(self):
        """
        Normally it is not necessary to call this method, it is only there
        to offer a convenient way to (re)connect the key-value store.
        This is necessary to update to changes which have occured in the
        store, as the remove store might create a cache during connecting.
        """
        self._connected = False
        self._connect()

    def _connect(self):
        if self._connected:
            return
        self.remote.connect(self.userpass)
        self._connected = True

    def query_remote(self, **kwargs):
        """
        Query the (usually remote) KVS for egg packages.
        """
        self._connect()
        kwargs['type'] = 'egg'
        return self.remote.query(**kwargs)

    def info_list_name(self, name):
        """
        return (sorted by versions (when possible)), a list of metadata
        dictionaries which are available on the remote KVS for a given name
        """
        req = Req(name)
        info_list = []
        for key, info in self.query_remote(name=name):
            if req.matches(info):
                info_list.append(dict(info))
        try:
            return sorted(info_list, key=comparable_info)
        except TypeError:
            return info_list

    # ============= methods which relate to local installation ===========

    def query_installed(self, **kwargs):
        """
        Query installed packages.  In addition to the remote metadata the
        following attributes are added:

        ctime: creation (install) time (string representing local time)

        hook: boolean -- whether installed into "versioned" egg directory

        installed: True (always)

        meta_dir: the path to the egg metadata directory on the local system
        """
        return self.ec.query(**kwargs)

    def find(self, egg):
        """
        Return the local egg metadata (see ``query_installed``) for a given
        egg (key) or None is the egg is not installed
        """
        return self.ec.find(egg)

    def execute(self, actions):
        """
        Execute actions, which is an iterable over tuples(action, egg_name),
        where action is one of 'fetch', 'remote', or 'install' and egg_name
        is the filename of the egg.
        This method is only meant to be called with actions created by the
        *_actions methods below.
        """
        if self.verbose:
            print "Enpkg.execute:", len(actions)
            for item in actions:
                print '\t' + str(item)

        if len(actions) == 0:
            return

        if self.evt_mgr:
            from encore.events.api import ProgressManager
        else:
            from egginst.console import ProgressManager

        self.super_id = uuid4()
        for c in self.ec.collections:
            c.super_id = self.super_id

        progress = ProgressManager(
                self.evt_mgr, source=self,
                operation_id=self.super_id,
                message="super",
                steps=len(actions),
                # ---
                progress_type="super", filename=actions[-1][1],
                disp_amount=len(actions), super_id=None)

        with History(None if self.hook else self.prefixes[0]):
            with progress:
                for n, (opcode, egg) in enumerate(actions):
                    if self._execution_aborted.is_set():
                        self._execution_aborted.clear()
                        break
                    if opcode.startswith('fetch_'):
                        self.fetch(egg, force=int(opcode[-1]))
                    elif opcode == 'remove':
                        self.ec.remove(egg)
                    elif opcode == 'install':
                        if self._connected:
                            extra_info = self.remote.get_metadata(egg)
                        else:
                            extra_info = None
                        self.ec.install(egg, self.local_dir, extra_info)
                    else:
                        raise Exception("unknown opcode: %r" % opcode)
                    progress(step=n)

        self.super_id = None
        for c in self.ec.collections:
            c.super_id = self.super_id

    def abort_execution(self):
        self._execution_aborted.set()

    def _install_actions_enstaller(self, installed_version=None):
        # installed_version is only useful for testing
        if installed_version is None:
            installed_version = enstaller.__version__

        mode = 'recur'
        self._connect()
        req = req_from_anything("enstaller")
        eggs = Resolve(self.remote, self.verbose).install_sequence(req, mode)
        if eggs is None:
            raise EnpkgError("No egg found for requirement '%s'." % req)
        elif not len(eggs) == 1:
            raise EnpkgError("No egg found to update enstaller, aborting...")
        else:
            name, version, build = split_eggname(eggs[0])
            if version == installed_version:
                return []
            else:
                return self._install_actions(eggs, mode, False, False)

    def install_actions(self, arg, mode='recur', force=False, forceall=False):
        """
        Create a list of actions which are required for installing, which
        includes updating, a package (without actually doing anything).

        The first argument may be any of:
          * the KVS key, i.e. the egg filename
          * a requirement object (enstaller.resolve.Req)
          * the requirement as a string
        """
        req = req_from_anything(arg)
        # resolve the list of eggs that need to be installed
        self._connect()
        eggs = Resolve(self.remote, self.verbose).install_sequence(req, mode)
        if eggs is None:
             raise EnpkgError("No egg found for requirement '%s'." % req)
        return self._install_actions(eggs, mode, force, forceall)

    def _install_actions(self, eggs, mode, force, forceall):
        if not forceall:
            # remove already installed eggs from egg list
            rm = lambda eggs: [e for e in eggs if self.find(e) is None]
            if force:
                eggs = rm(eggs[:-1]) + [eggs[-1]]
            else:
                eggs = rm(eggs)

        res = []
        for egg in eggs:
            res.append(('fetch_%d' % bool(forceall or force), egg))

        if not self.hook:
            # remove packages with the same name (from first egg collection
            # only, in reverse install order)
            for egg in reversed(eggs):
                name = split_eggname(egg)[0].lower()
                index = dict(self.ec.collections[0].query(name=name))
                assert len(index) < 2
                if len(index) == 1:
                    res.append(('remove', index.keys()[0]))
        for egg in eggs:
            res.append(('install', egg))
        return res

    def remove_actions(self, arg):
        """
        Create the action necessary to remove an egg.  The argument, may be
        one of ..., see above.
        """
        req = req_from_anything(arg)
        assert req.name
        index = dict(self.ec.collections[0].query(**req.as_dict()))
        if len(index) == 0:
            raise EnpkgError("package %s not installed in: %r" %
                             (req, self.prefixes[0]))
        if len(index) > 1:
            assert self.hook
            versions = ['%(version)s-%(build)d' % d
                        for d in index.itervalues()]
            raise EnpkgError("package %s installed more than once: %s" %
                             (req.name, ', '.join(versions)))
        return [('remove', index.keys()[0])]

    def revert_actions(self, arg):
        """
        Calculate the actions necessary to revert to a given state, the
        argument may be one of:
          * complete set of eggs, i.e. a set of egg file names
          * revision number (negative numbers allowed)
        """
        if self.hook:
            raise NotImplementedError
        h = History(self.prefixes[0])
        h.update()
        if isinstance(arg, set):
            state = arg
        else:
            try:
                rev = int(arg)
            except ValueError:
                raise EnpkgError("Error: integer expected, got: %r" % arg)
            try:
                state = h.get_state(rev)
            except IndexError:
                raise EnpkgError("Error: no such revision: %r" % arg)

        curr = h.get_state()
        if state == curr:
            return []

        res = []
        for egg in curr - state:
            if egg.startswith('enstaller'):
                continue
            res.append(('remove', egg))

        for egg in state - curr:
            if egg.startswith('enstaller'):
                continue
            if not isfile(join(self.local_dir, egg)):
                self._connect()
                if self.remote.exists(egg):
                    res.append(('fetch_0', egg))
                else:
                    raise EnpkgError("cannot revert -- missing %r" % egg)
            res.append(('install', egg))
        return res

    def get_history(self):
        """
        return a history (h) object:

        h = Enpkg().get_history()
        h.parse() -> list of tuples(datetime strings, set of eggs/diffs)
        h.construct_states() -> list of tuples(datetime strings, set of eggs)
        """
        if self.hook:
            raise NotImplementedError
        return History(self.prefixes[0])

    # == methods which relate to both (remote store and local installation) ==

    def query(self, **kwargs):
        index = dict(self.query_remote(**kwargs))
        for key, info in self.query_installed(**kwargs):
            if key in index:
                index[key].update(info)
            else:
                index[key] = info
        return index.iteritems()

    def fetch(self, egg, force=False):
        self._connect()
        f = FetchAPI(self.remote, self.local_dir, self.evt_mgr)
        f.super_id = getattr(self, 'super_id', None)
        f.verbose = self.verbose
        f.fetch_egg(egg, force, self._execution_aborted)


if __name__ == '__main__':
    enpkg = Enpkg()
    for key, info in enpkg.query_remote(name='numpy'):
        print key
