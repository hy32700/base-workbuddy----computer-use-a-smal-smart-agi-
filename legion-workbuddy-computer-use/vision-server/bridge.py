"""Lazy shared-helper startup, using a Windows lock and authenticated loopback RPC."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

STATE = Path(os.environ.get('VIEW_STATE_DIR', Path(__file__).resolve().parents[1] / '.runtime')).resolve()
IDENTITY = 'view-desktop-coordinator-v1'


def request(endpoint, payload, timeout=50):
    if endpoint.get('identity') != IDENTITY or type(endpoint.get('port')) is not int:
        raise ValueError('Invalid local coordinator endpoint')
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"http://127.0.0.1:{endpoint['port']}/rpc", data=body,
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + endpoint['token']})
    # Local traffic must not go through an environment-configured proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
        return json.load(response)


def existing_endpoint():
    try:
        endpoint = json.loads((STATE / 'endpoint.json').read_text(encoding='utf-8'))
        ping = request(endpoint, {'method': 'ping'}, timeout=1)
        if ping.get('identity') == IDENTITY and ping.get('pid') == endpoint['pid']:
            return endpoint
    except (OSError, ValueError, KeyError):
        pass
    return None


@contextmanager
def startup_lock():
    import msvcrt
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'startup.lock').open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 20
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Timed out waiting for coordinator startup')
                time.sleep(0.1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def ensure_backend():
    endpoint = existing_endpoint()
    if endpoint:
        return endpoint
    with startup_lock():
        endpoint = existing_endpoint()
        if endpoint:
            return endpoint
        with (STATE / 'coordinator.log').open('ab') as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).with_name('broker.py'))],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            endpoint = existing_endpoint()
            if endpoint:
                return endpoint
            if child.poll() is not None:
                raise RuntimeError('Coordinator startup failed; see .runtime/coordinator.log')
            time.sleep(0.1)
        child.terminate()
        raise TimeoutError('Coordinator did not become ready within 15 seconds')


def call(name, arguments):
    # Do not replay a mutating request after a connection error: outcome may be unknown.
    return request(ensure_backend(), {'method': 'call', 'name': name, 'arguments': arguments})
