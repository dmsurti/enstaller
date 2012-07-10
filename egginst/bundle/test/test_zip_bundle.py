#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import os
import tempfile
import zipfile

from ..zip_bundle import ZipBundle

from .test_bundle import BundleTestCase

class ZipBundleTestCase(BundleTestCase):
    
    def setUp(self):
        fp, path = tempfile.mkstemp()
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('testfile', 'data')
            z.writestr('testdir/testfile', 'data')
        
        self.bundle = ZipBundle(path)
    
    def tearDown(self):
        os.unlink(self.bundle.path)
    
    def test_installed_size(self):
        self.assertEqual(self.bundle.installed_size, 8)
