#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import os

import egginst.platform.windows as windows

from .test_platform import PlatformTestCase

class PosixPlatformTestCase(PlatformTestCase):
    
    platform = windows
    
    def test_is_win(self):
        self.assertTrue(self.platform.is_win)

    def test_script_extras_console(self):
        self.assertEqual(self.platform.script_extras(self.path, 'test',
            'console_scripts'), [os.path.join(self.path, 'test.exe')])

    def test_script_extras_gui(self):
        self.assertEqual(self.platform.script_extras(self.path, 'test',
            'gui_scripts'), [os.path.join(self.path, 'test.exe')])

    def test_script_extras_exists(self):
        with open(os.path.join(self.path, 'test.exe'), 'wb') as fp:
            fp.write('data')
            
        self.assertEqual(self.platform.script_extras(self.path, 'test',
            'console_scripts'), [os.path.join(self.path, 'test.exe')])
            
        with open(os.path.join(self.path, 'test.exe'), 'rb') as fp:
            self.assertNotEqual(fp.read(), 'data')

    def test_script_extras_exists_in_use(self):
        with open(os.path.join(self.path, 'test.exe'), 'wb') as fp:
            fp.write('data')
     
        with open(os.path.join(self.path, 'test.exe'), 'rb') as fp:
            self.assertEqual(self.platform.script_extras(self.path, 'test',
                'console_scripts'), [os.path.join(self.path, 'test.exe')])
            self.assertEqual(fp.read(), 'data')
            with open(os.path.join(self.path, 'test.exe'), 'rb') as fp2:
                self.assertNotEqual(fp2.read(), 'data')
