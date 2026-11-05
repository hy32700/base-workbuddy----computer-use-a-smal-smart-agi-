"""One loopback coordinator shared across all WorkBuddy MCP/chat processes."""

import asyncio
import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from jsonschema import validate
from runtime import DesktopRuntime
from tools import TOOLS, dispatch, screenshot

STATE = Path(os.environ.get('VIEW_STATE_DIR', Path(__file__).resolve().parents[1] / '.runtime')).resolve()
IDENTITY = 'view-desktop-coordinator-v1'


async def main():
    STATE.mkdir(parents=True, exist_ok=True)
    runtime = DesktopRuntime(STATE / 'screenshots', screenshot.capture_details)
    loop = asyncio.get_running_loop()
    token = secrets.token_urlsafe(32)
    activity = [time.monotonic()]
    schemas = {t.name: t.inputSchema for t in TOOLS}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log the local capability token, screenshots, or request content.

        def reply(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if (self.path != '/rpc' or self.headers.get('Origin')
                    or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)):
                self.reply(403, {'error': 'Forbidden'})
                return
            future = None
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1_000_000:
                    raise ValueError('Invalid request length')
                request = json.loads(self.rfile.read(size))
                activity[0] = time.monotonic()
                if request.get('method') == 'ping':
                    self.reply(200, {'identity': IDENTITY, 'pid': os.getpid()})
                    return
                if request.get('method') != 'call':
                    raise ValueError('Unknown method')
                name, args = request['name'], request.get('arguments', {})
                validate(args, schemas[name])
                future = asyncio.run_coroutine_threadsafe(dispatch(runtime, name, args), loop)
                result = future.result(timeout=45)
                self.reply(200, {'content': [c.model_dump(mode='json') for c in result], 'isError': False})
            except Exception as error:
                if future is not None and not future.done():
                    future.cancel()
                self.reply(200, {'content': [{'type': 'text', 'text': json.dumps({
                    'success': False, 'error': f'{type(error).__name__}: {error}'}, ensure_ascii=False)}],
                    'isError': True})

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    endpoint = {'identity': IDENTITY, 'port': http.server_address[1], 'token': token, 'pid': os.getpid()}
    temp = STATE / f'endpoint-{os.getpid()}.tmp'
    temp.write_text(json.dumps(endpoint), encoding='utf-8')
    os.replace(temp, STATE / 'endpoint.json')
    try:
        while True:
            await asyncio.sleep(15)
            # Retire the idle helper; a future MCP call can launch a fresh helper.
            if not runtime.jobs and time.monotonic() - activity[0] > 600:
                return
    finally:
        await runtime.stop()
        http.shutdown()
        http.server_close()


if __name__ == '__main__':
    asyncio.run(main())
