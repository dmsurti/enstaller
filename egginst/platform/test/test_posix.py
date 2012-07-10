#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import egginst.platform.posix as posix

from .test_platform import PlatformTestCase

class PosixPlatformTestCase(PlatformTestCase):
    
    platform = posix
    
    def test_is_win(self):
        self.assertFalse(self.platform.is_win)

    def test_script_extras(self):
        self.assertEqual(self.platform.script_extras(self.path, 'test',
            'console_scripts'), [])

    def test_script_extras_gui(self):
        self.assertEqual(self.platform.script_extras(self.path, 'test',
            'gui_scripts'), [])

