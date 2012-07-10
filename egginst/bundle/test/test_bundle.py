#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

from unittest import TestCase

class BundleTestCase(TestCase):
    
    bundle = None
    
    def test_contains(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertTrue(('testfile',) in self.bundle)
    
    def test_contains_dir(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertTrue(('testdir', 'testfile') in self.bundle)
    
    def test_contains_false(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertFalse(('testfile_missing',) in self.bundle)
    
    def test_contains_dir_false(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertFalse(('test_dir', 'testfile_missing') in self.bundle)
        self.assertFalse(('test_dir_missing', 'testfile') in self.bundle)

    def test_iter(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertEquals(set(self.bundle), set([('testfile',),
            ('testdir', 'testfile')]))

    def test_get_bytes(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertEquals(self.bundle.get_bytes(('testfile',)), 'data')

    def test_get_bytes_dir(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        self.assertEquals(self.bundle.get_bytes(('testdir', 'testfile')), 'data')

    def test_read(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        with self.bundle.open(('testfile',)) as fp:
            content = fp.read()
        self.assertEquals(content, 'data')

    def test_read_nbytes(self):
        if self.bundle is None:
            self.skipTest('Abstract test case')
        with self.bundle.open(('testfile',)) as fp:
            content = []
            while True:
                data = fp.read(1)
                if data:
                    content.append(data)
                else:
                    break
        self.assertEquals(content, list('data'))
