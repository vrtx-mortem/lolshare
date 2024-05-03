#!/usr/bin/env python3
import pathlib
import cgi
import secrets
import string
import os
import magic

class ShareService:
    def __init__(self, environ, response):
        self.environ = environ
        self.response = response
        self.storage = pathlib.Path(os.getenv('STORAGE', '/tmp/'))
        self.default_mime = 'text/plain'
        self.default_encoding = 'utf-8'

    def _get_blob_path(self, blob_id: str) -> str:
        return self.storage.joinpath(blob_id)

    def read_blob(self, blob_id: str) -> bytes:
        try:
            with open(self._get_blob_path(blob_id), 'rb') as fd:
                return fd.read()
        except (FileNotFoundError, PermissionError, IsADirectoryError):
            return 

    def write_blob(self, blob_id: str, buffer: bytes) -> None:
        try:
            with open(self._get_blob_path(blob_id), 'wb') as fd:
                fd.write(buffer)
        except (PermissionError):
            return

    def generate_blob_id(self, length: int = 8) -> str:
        alphabet = string.digits + string.ascii_letters
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def generate_unique_blob_id(self, length: int = 8) -> str:
        while True:
            blob_id = self.generate_blob_id(length)
            if not self.storage.joinpath(blob_id).exists():
                break
        return blob_id

    def get_mime(self, buffer: bytes) -> str:
        mimes = magic.Magic(mime = True)
        mime = mimes.from_buffer(buffer)
        badies = ['octet-stream', 'text/']
        for bad in badies:
            if bad in mime:
                mime = 'text/plain'
                break
        return mime

    def get_user_blob(self) -> bytes:
        post_data = cgi.FieldStorage(
            fp = self.environ.get('wsgi.input'), 
            environ = self.environ,
            keep_blank_values = False,
        )
        if not post_data:
            return

        blob = post_data.getvalue(post_data.keys().pop())
        if type(blob) == str:
            return blob.encode(self.default_encoding)
        return blob

    def ok(self, buffer: bytes, mime: str = '') -> list:
        if not mime:
            mime = self.default_mime

        self.response('200 OK', [
            ('Content-Type', mime),
            ('Content-Length', str(len(buffer))),
        ])
        return [buffer]

    def fail(self) -> list:
        self.response('451 Unavailable for legal reasons', [
            ('Content-Type', self.default_mime),
        ])
        return [b'']

    def redirect(self, blob_id: str) -> list:
        self.response('301 Moved Permanently', [
            ('Content-Type', self.default_mime),
            ('Location', f'/{blob_id}'),
        ])
        return [blob_id.encode(self.default_encoding)]

    def serve_howto(self) -> list:
        manual = pathlib.Path(__file__).parent.joinpath('HOWTO')
        url = f'{self.environ.get("REQUEST_SCHEME", "https")}://{self.environ.get("HTTP_HOST","localhost")}/'
        with open(manual, 'r') as fd:
            buffer = fd.read()
            buffer = buffer.replace('__URL__', url)
            return self.ok(buffer.encode(self.default_encoding))

    def handle_GET(self) -> list:
        if self.environ.get('REQUEST_URI') == '/':
            return self.serve_howto()

        blob_id = self.environ.get('REQUEST_URI', '')
        blob_id = pathlib.Path(blob_id).name
        if buffer := self.read_blob(blob_id):
            mime = self.get_mime(buffer)
            return self.ok(buffer, mime)
        return self.fail()

    def handle_POST(self) -> list:
        buffer = self.get_user_blob()
        if not buffer:
            return self.fail()
        if type(buffer) == str:
            buffer = buffer.encode(self.default_encoding)

        blob_id = self.generate_unique_blob_id()
        self.write_blob(blob_id, buffer)
        return self.redirect(blob_id)

    def handle(self) -> list:
        match self.environ.get('REQUEST_METHOD'):
            case 'GET':
                return self.handle_GET()
            case 'POST':
                return self.handle_POST()
            case _:
                return self.fail()

def application(environ, response) -> list:
    service = ShareService(environ, response)
    return service.handle()
