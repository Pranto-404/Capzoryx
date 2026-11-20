"""Serve an explicitly provided model pack on loopback without contacting any registry."""
import argparse
import hashlib
import json
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import copyfileobj
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
MODEL = 'Qwen3-0.6B-q4f16_1-MLC'
KERNEL = 'Qwen3-0.6B-q4f16_1_cs1k-webgpu.wasm'
CSP = ("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; "
       "worker-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


def routes(pack, checksums):
    expected = json.loads(checksums.read_text())
    if not isinstance(expected, dict) or not expected:
        raise ValueError('Provide a SHA-256 manifest for the reviewed model pack.')
    config = json.loads((pack / 'mlc-chat-config.json').read_text())
    if config.get('model_type') != 'qwen3' or config.get('quantization') != 'q4f16_1':
        raise ValueError('This preview requires Qwen3 q4f16_1.')
    shard_index = json.loads((pack / 'ndarray-cache.json').read_text())
    assets = {'mlc-chat-config.json', 'ndarray-cache.json', KERNEL,
              *config['tokenizer_files'], *(shard['dataPath'] for shard in shard_index['records'])}
    digest = hashlib.sha256(checksums.read_bytes()).hexdigest()[:20]
    prefix = f'/model/resolve/{digest}/'
    files = {'/': (HERE / 'index.html', 'text/html; charset=utf-8'),
             '/preview.js': (HERE / 'preview.js', 'text/javascript'),
             '/preview.css': (HERE / 'preview.css', 'text/css'),
             '/runtime.js': (HERE / 'node_modules/@mlc-ai/web-llm/lib/index.js', 'text/javascript')}
    for name in assets:
        if name != Path(name).name or name in {'.', '..'}:
            raise ValueError('Unexpected nested model path.')
        path = pack / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing regular model asset {name}.')
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected.get(name):
                raise ValueError(f'Unverified model asset {name}.')
        files[prefix + name] = (path, 'application/wasm' if name == KERNEL else 'application/octet-stream')
    if not files['/runtime.js'][0].is_file():
        raise ValueError('Install the pinned preview runtime with npm ci --ignore-scripts.')
    return files, json.dumps(dict(id=MODEL, path=prefix, kernel=KERNEL)).encode()


class Preview(BaseHTTPRequestHandler):
    def __init__(self, *args, files, metadata, **kwargs):
        self.files, self.metadata = files, metadata
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path == '/pack.json':
            mime, length = 'application/json', len(self.metadata)
        elif path in self.files:
            file, mime = self.files[path]
            length = file.stat().st_size
        else:
            self.send_error(404)
            return
        self.send_response(200)
        for key, value in [('Content-Type', mime), ('Content-Length', str(length)),
                           ('Content-Security-Policy', CSP), ('X-Content-Type-Options', 'nosniff'),
                           ('Referrer-Policy', 'no-referrer'), ('Cross-Origin-Resource-Policy', 'same-origin')]:
            self.send_header(key, value)
        self.end_headers()
        if path == '/pack.json':
            self.wfile.write(self.metadata)
        else:
            with file.open('rb') as handle:
                copyfileobj(handle, self.wfile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', type=Path)
    parser.add_argument('checksums', type=Path)
    args = parser.parse_args()
    files, metadata = routes(args.pack, args.checksums)
    server = ThreadingHTTPServer(('127.0.0.1', 8764), partial(Preview, files=files, metadata=metadata))
    print('Open http://127.0.0.1:8764 after disconnecting from the internet.', flush=True)
    server.serve_forever()
