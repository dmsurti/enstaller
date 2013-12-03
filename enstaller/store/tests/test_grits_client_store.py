import re
import json
from unittest import TestCase

from ..grits_egg_store import GritsClientStore

class MockGritsResponse():
    def __init__(self, data):
        self.data = data

    def json(self):
        return json.loads(self.data)

    def raise_for_status(self):
        return None

class MockGritsServer():
    def __init__(self, url, index_data=None):
        if index_data is None:
            index_data = {}
        self.url = url
        self._index_data = index_data

    def get(self, url, *args, **kwargs):
        path = url[len(self.url):]
        if re.match('/store/([^/]+)$', path):
            return self._query_space("enthought", **kwargs)
        else:
            raise self._404(url)

    def post(self, url, *args, **kwargs):
        path = url[len(self.url):]
        if path == '/authenticate':
            return self._authenticate()
        elif path == '/action':
            return self._action()
        else:
            raise self._404(url)


    def _404(self, url):
        raise ValueError('URL Not Found: {}'.format(url))

    def _action(self):
        return MockGritsResponse('')

    def _authenticate(self):
        return MockGritsResponse(json.dumps({'stores': [{'user_spaces': ['enthought']}]}))

    def _query_space(self, space, select=None, since=None, **kwargs):
        params = {k: json.loads(v) for k, v in kwargs['params'].iteritems() \
                  if not k == "_with_metadata"}
        def _match_query_params(data, params):
            for name, value in params.iteritems():
                if data.get(name, None) != value:
                    return False
            return True

        def _naive_search(raw_data, params):
            for k, v in raw_data.iteritems():
                if _match_query_params(v, params):
                    yield k, v
        data = dict(_naive_search(self._index_data, params))
        return MockGritsResponse(json.dumps(data))


class GritsClientStoreTest(TestCase):
    def test_simple_query(self):
        url = 'testurl/api'

        index_data = {
            "zlib-1.2.6-1.egg": {
                "name": "zlib",
                "type": "egg",
            }
        }
        store = GritsClientStore(url, MockGritsServer(url, index_data))
        store.connect(('username', 'password'))
        store.add_action(1, 'action_type', 1234567890)

        self.assertEqual(store.query(name="pandasql"), [])
        self.assertEqual(len(store.query(name="zlib")), 1)
        self.assertEqual(store.query(name="zlib")[0][0], "zlib-1.2.6-1.egg")
