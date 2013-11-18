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
    def __init__(self, url):
        self.url = url

    def get(self, url, *args, **kwargs):
        path = url[len(self.url):]
        if re.match('/store/([^/]+)$', path):
            return self._query_space()
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

    def _query_space(self):
        return MockGritsResponse('{}')


class GritsClientStoreTest(TestCase):
    def test(self):
        url = 'testurl/api'
        store = GritsClientStore(url, MockGritsServer(url))
        store.connect(('username', 'password'))
        store.add_action(1, 'action_type', 1234567890)
        store.query()
