#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import sys

def get_platform():
    if sys.platform == 'win32':
        import windows
        return windows
    else:
        import posix
        return posix
