#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

class AbstractBundle(object):
    """ An abstract bundle represents a collection of files
    
    Files are referred to by paths, which are tuples of strings, and contain a
    sequence of bytes.  A Bundle is dumb in the sense that it is just a
    collection of files and only concerns itself with the existence and
    content of the files, not what the files contain or what they represent.
    
    Prototypically a Bundle wraps a directory of files or a zipfile, but
    there is nothing stopping it being something more complex, like a view on
    a website or an encore.storage key-value store.
    
    Informally, you should think of a package being the "transport layer" and
    the metadata as the "protocol".
    
    """
    
    def __iter__(self):
        raise NotImplementedError
    
    def __contains__(self, path):
        raise NotImplementedError
    
    def open(self, path):
        raise NotImplementedError
    
    def get_bytes(self, path):
        with self.open(path) as data:
            return data.read()

