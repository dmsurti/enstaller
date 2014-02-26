from __future__ import print_function

import math
import os
import sys
import hashlib
from uuid import uuid4
from os.path import basename, isdir, isfile, join

from egginst.utils import human_bytes, rm_rf
from enstaller.compat import close_file_or_response
from utils import md5_file


class FetchAPI(object):

    def __init__(self, remote, local_dir, evt_mgr=None):
        self.remote = remote
        self.local_dir = local_dir
        self.evt_mgr = evt_mgr
        self.verbose = False

    def path(self, fn):
        return join(self.local_dir, fn)

    def fetch(self, key, execution_aborted=None):
        """ Fetch the given key.

        execution_aborted: a threading.Event object which signals when the execution
            needs to be aborted, or None, if we don't want to abort the fetching at all.
        """
        path = self.path(key)
        fi, info = self.remote.get(key)

        size = info['size']
        md5 = info.get('md5')

        if self.evt_mgr:
            from encore.events.api import ProgressManager
        else:
            from egginst.console import ProgressManager

        progress = ProgressManager(
                self.evt_mgr, source=self,
                operation_id=uuid4(),
                message="fetching",
                steps=size,
                # ---
                progress_type="fetching", filename=basename(path),
                disp_amount=human_bytes(size),
                super_id=getattr(self, 'super_id', None))

        n = 0
        h = hashlib.new('md5')
        if size < 256:
            buffsize = 1
        else:
            buffsize = 2 ** int(math.log(size / 256.0) / math.log(2.0) + 1)

        pp = path + '.part'
        if sys.platform == 'win32':
            rm_rf(pp)
        with progress:
            with open(pp, 'wb') as fo:
                while True:
                    if execution_aborted is not None and execution_aborted.is_set():
                        close_file_or_response(fi)
                        return
                    chunk = fi.read(buffsize)
                    if not chunk:
                        break
                    fo.write(chunk)
                    if md5:
                        h.update(chunk)
                    n += len(chunk)
                    progress(step=n)

        close_file_or_response(fi)

        if md5 and h.hexdigest() != md5:
            raise ValueError("received data MD5 sums mismatch")

        if sys.platform == 'win32':
            rm_rf(path)
        os.rename(pp, path)

    def fetch_egg(self, egg, force=False, execution_aborted=None):
        """
        fetch an egg, i.e. copy or download the distribution into local dir
        force: force download or copy if MD5 mismatches
        execution_aborted: a threading.Event object which signals when the execution
            needs to be aborted, or None, if we don't want to abort the fetching at all.
        """
        if not isdir(self.local_dir):
            os.makedirs(self.local_dir)
        info = self.remote.get_metadata(egg)
        path = self.path(egg)

        # if force is used, make sure the md5 is the expected, otherwise
        # merely see if the file exists
        if isfile(path):
            if force:
                if md5_file(path) == info.get('md5'):
                    if self.verbose:
                        print("Not refetching, %r MD5 match" % path)
                    return
            else:
                if self.verbose:
                    print("Not forcing refetch, %r exists" % path)
                return

        self.fetch(egg, execution_aborted)
