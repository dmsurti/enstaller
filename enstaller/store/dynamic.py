#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import json
import urlparse
import urllib
import urllib2

from enstaller import config

from .base import AbstractStore
from .cached import CachedHandler
from .compressed import CompressedHandler


class DynamicHTTPStore(AbstractStore):
    """ A dynamic store relies purely on queries redirected to a remote store
    
    The implementation in enstaller is intended to be a minimal, read-only
    implementation.  A more complete read-write version will be included in
    Encore, using the requests library for more robust handling.
    
    """
    def __init__(self, url, spaces=['enthought']):
        self.root = url.rstrip('/')
        self.authenticate_url = self.root + '/authenticate'

        # Use handlers from urllib2's default opener, since we already
        # added our proxy handler to it.
        opener = urllib2._opener
        http_handlers = [urllib2.HTTPHandler, urllib2.HTTPSHandler]
        handlers = opener.handlers if opener is not None else http_handlers

        # Add our handlers to the default handlers.
        handlers_ = [CompressedHandler, CachedHandler(config.get('local'))] + \
                    handlers

        self.opener = urllib2.build_opener(*handlers_)
        
    def _normalize_url(self, url):
        parsed_url = urlparse.urlparse(url)
        if parsed_url.netloc == '':
            url = urlparse.urljoin(self.root, url)
        url = url.rstrip('/') # ensure doesn't ends with '/'
        return url
    
    def _get_url(self, url, reauthenticate=True):
        try:
            return self.opener.open(url)
        except urllib2.HTTPError as err:
            if err.code == 401 and reauthenticate:
                # not authenticated, re-authenticate and try again
                self.authenticate()
                return self._get_url(url, False)
            else:
                raise
        
    
    def connect(self, credentials=None):
        self._credentials = credentials
        self.authenticate()
        self._stores = self._directory['stores']
        self._store_urls = [self._normalize_url(store['location']) for store in self._stores]
        
    
    def authenticate(self):
        """ Authenticate with form-based auth, getting a cookie back
        
        """
        data = urllib.urlencode(zip(('username', 'password'), self._credentials))
        response = self.opener.open(self.authenticate_url, data)
        self._directory = json.load(response)
    
    def query_keys(self, **kwargs):
        args = urllib.urlencode(kwargs)
        for url in self._store_urls:
            for space in self.spaces:
                full_url = url + '/' + space + '?' + args
                response = self._get_url(full_url)
                for line in response:
                    key = line.rstrip('\r\n')
                    if key:
                        yield key
    
    def get_data(self, key):
        for url in self._store_urls:
            key_url = url + '/' + urllib.quote(key, safe="/~!$&'()*+,;=:@") + '/data'
            try:
                response = self._get_url(key_url)
                return response
            except urllib2.HTTPError as err:
                if err.code == 404:
                    # not found, try next url
                    continue
        # no match
        raise KeyError(key)
    
    def get_metadata(self, key):
        for url in self._store_urls:
            key_url = url + '/' + urllib.quote(key, safe="/~!$&'()*+,;=:@") + '/metadata'
            try:
                response = self._get_url(key_url)
                return response
            except urllib2.HTTPError as err:
                if err.code == 404:
                    # not found, try next url
                    continue
        # no match
        raise KeyError(key)

