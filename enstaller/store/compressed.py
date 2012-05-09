from cStringIO import StringIO
import bz2
import gzip
import urllib2


class CompressedHandler(urllib2.BaseHandler):
    compression_types = [
        ('bzip2', bz2.decompress),
        ('gzip', lambda data: gzip.GzipFile(fileobj=StringIO(data)).read()),
        ('*', lambda data: data)
    ]

    def http_request(self, req):
        if not req.headers.get('Accept-Encoding'):
            req.headers['Accept-Encoding'] = ','.join(
                [enc for enc, _ in self.compression_types])
        return req

    https_request = http_request

    def http_response(self, req, response):
        content_encoding = response.headers.get('Content-Encoding')
        if not content_encoding:
            return response

        for encoding, decompress in self.compression_types:
            if encoding in content_encoding:
                decompressed = decompress(response.read())
                response.read = lambda: decompressed

        return response

    https_response = http_response
