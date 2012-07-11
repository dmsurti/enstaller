#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

# standard library imports
import zipfile

# local imports
from .abstract_bundle import AbstractBundle

class ZipBundle(AbstractBundle):
    """ Class that represents a zipfile
    
    Attributes
    ----------
    
    path : string
        The path to the location of the zipfile
    
    """
    
    def __init__(self, path):
        self.path = path
        
        self._archive = zipfile.ZipFile(self.path)
        # ignore directories (ie. paths that end with '/')
        self._info = [info for info in self._archive.infolist()
            if not info.filename.endswith('/')]
        self._paths = set(tuple(info.filename.split('/'))
            for info in self._info)
        
        self.installed_size = sum(info.file_size for info in self._info)
    
    def __iter__(self):
        # regenerate the paths in the hope that iterator will run through
        # file in a sane order without skipping around on disk
        return (tuple(info.filename.split('/')) for info in self._info)
        
    def __contains__(self, path):
        return tuple(path) in self._paths
    
    def open(self, path):
        return self._archive.open('/'.join(path))
    
    def get_bytes(self, path):
        return self._archive.read('/'.join(path))

    def get_size(self, path):
        return self._archive.getinfo('/'.join(path)).file_size
