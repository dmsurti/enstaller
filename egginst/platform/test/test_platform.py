#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import os
import sys
from unittest import TestCase
from tempfile import mkdtemp

class PlatformTestCase(TestCase):
    
    platform = None
    
    def setUp(self):
        self.actual_platform_name = 'windows' if sys.platform == 'win32' else 'posix'
        
        self.path = mkdtemp()
        
        # create some files and directories to test remove_file
        # used for basic ops
        self.file_basic = os.path.join(self.path, 'file_basic')
        with open(self.file_basic, 'w') as fp:
            fp.write('data')
        
        self.dir_basic_1 = os.path.join(self.path, 'dir_basic_1')
        os.mkdir(self.dir_basic_1)
    
        self.dir_basic_2 = os.path.join(self.path, 'dir_basic_2')
        os.mkdir(self.dir_basic_2)
        with open(os.path.join(self.dir_basic_2, 'file_1'), 'w') as fp:
            fp.write('data')

        # used for in-use tests
        self.file_in_use = os.path.join(self.path, 'file_in_use')
        with open(self.file_in_use, 'w') as fp:
            fp.write('data')
        
        self.dir_in_use = os.path.join(self.path, 'dir_in_use')
        os.mkdir(self.dir_in_use)
        with open(os.path.join(self.dir_in_use, 'file_1'), 'w') as fp:
            fp.write('data')
    
        self.dir_4 = os.path.join(self.path, 'dir_4')
        os.mkdir(self.dir_4)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.path)

    def _check_platform(self):
        if self.platform is None:
            self.skipTest('Abstract test case, skipping')
        elif self.platform.name != self.actual_platform_name:
            self.skipTest('Platform does not match test platform, skipping')
            
    def test_remove_file_basic(self):
        self._check_platform()
        self.platform.remove_file(self.file_basic)
        self.assertFalse(os.path.exists(self.file_basic))
            
    def test_remove_file_dir_basic_1(self):
        self._check_platform()
        self.platform.remove_file(self.dir_basic_1)
        self.assertFalse(os.path.exists(self.dir_basic_1))
            
    def test_remove_file_dir_basic_2(self):
        self._check_platform()
        self.platform.remove_file(self.dir_basic_2)
        self.assertFalse(os.path.exists(self.dir_basic_2))
            
    def test_remove_file_in_use(self):
        self._check_platform()
        with open(self.file_in_use) as fp:
            self.platform.remove_file(self.file_in_use)
            self.assertFalse(os.path.exists(self.file_in_use))
            self.assertEquals(fp.read(), 'data')
            
    def test_remove_dir_in_use(self):
        self._check_platform()
        with open(os.path.join(self.dir_in_use, 'file_1')) as fp:
            self.platform.remove_file(self.dir_in_use)
            self.assertFalse(os.path.exists(self.dir_in_use))
            self.assertEquals(fp.read(), 'data')
