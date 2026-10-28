"""Smoke test of a built Apipos binary (CI runs it before uploading installers).

Starts the binary headless (APIPOS_NO_TRAY=1) with its log in a temp file,
waits for the API and checks that the packaged dependencies work:

  GET  /health  -> success; data.version and X-Apipos-Version == --version
  GET  /fonts   -> success with at least one system font family (fontTools)
  POST /render  -> a PDF and a PNG with a system font (PyMuPDF + fontTools)

On failure it prints the reason, the process output and the tail of the app
log, and exits 1. Standard library only: CI runs it with the runner's Python.

Usage:
  python scripts/smoke_binary.py --version 2.0.3 -- dist/Apipos.exe
  python scripts/smoke_binary.py --version 2.0.3 -- dist/Apipos.app/Contents/MacOS/Apipos
  python scripts/smoke_binary.py --version 2.0.3 -- .venv/bin/python apipos.py
"""
import argparse
import base64
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

DEFAULT_PORT = 50432  # FLASK_PORT in src/config.py
PREFERRED_FAMILIES = ('Arial', 'DejaVu Sans', 'Helvetica', 'Liberation Sans')


def port_in_use(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def request(port, path, body=None):
    """Return (HTTP status, headers, parsed JSON body); HTTP errors included."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}{path}', data=data,
        headers={'Content-Type': 'application/json'} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, json.loads(exc.read() or b'null')


def check(port, version):
    """Run the checks against the live API. Returns OK lines; raises
    AssertionError with the reason at the first failure."""
    ok = []
    status, headers, body = request(port, '/health')
    assert status == 200 and body['status'] == 'success', f'/health -> {status} {body}'
    got = body['data']['version']
    assert got == version, f'/health dice v{got}, se esperaba v{version}'
    header = headers.get('X-Apipos-Version')
    assert header == version, f'X-Apipos-Version {header!r}, se esperaba {version!r}'
    ok.append(f'/health OK (v{version})')

    status, _, body = request(port, '/fonts')
    assert status == 200 and body['status'] == 'success', f'/fonts -> {status} {body}'
    families = [f['family'] for f in body['data']['families']]
    assert families, '/fonts no encontró fuentes del sistema (escaneo de fontTools vacío)'
    ok.append(f'/fonts OK ({len(families)} familias)')

    family = next((f for f in PREFERRED_FAMILIES if f in families), families[0])
    ticket = {
        'settings': {'font': {'family': family}},
        'content': [
            {'type': 'text', 'data': 'Apipos smoke ñ áé', 'align': 'center'},
            {'type': 'special_text', 'data': {'text1': 'TOTAL', 'text2': '$1.00'}},
        ],
    }
    for fmt, magic in (('pdf', b'%PDF'), ('png', b'\x89PNG')):
        status, _, body = request(port, '/render', dict(ticket, format=fmt))
        assert status == 200 and body['status'] == 'success', f'/render {fmt} -> {status} {body}'
        raw = base64.b64decode(body['data']['base64'])
        assert raw.startswith(magic), f'/render {fmt} no devolvió un {fmt.upper()}: {raw[:8]!r}'
        ok.append(f'/render {fmt} OK ({len(raw)} bytes, fuente {family!r})')
    return ok


def stop(proc):
    """End the app and its children (the onefile bootloader runs it in a child)."""
    if proc.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def tail(path, lines=60):
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return ''.join(fh.readlines()[-lines:])
    except OSError:
        return '(no existe)\n'


def main():
    parser = argparse.ArgumentParser(description='Smoke test de un binario de Apipos.')
    parser.add_argument('--version', required=True, help='versión esperada (APP_VERSION)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--timeout', type=float, default=90,
                        help='segundos de espera a que el API abra el puerto')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='-- <binario> [args...]')
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('falta el comando: -- <binario> [args...]')
    if os.path.exists(command[0]):
        command[0] = os.path.abspath(command[0])  # dist/Apipos.exe -> absolute, native separators

    if port_in_use(args.port):
        print(f'SMOKE FAIL: el puerto {args.port} ya está ocupado (¿otro Apipos corriendo?)')
        return 1

    workdir = tempfile.mkdtemp(prefix='apipos-smoke-')
    log_file = os.path.join(workdir, 'apipos.log')
    console_file = os.path.join(workdir, 'console.txt')
    env = dict(os.environ, APIPOS_NO_TRAY='1', APIPOS_LOG_FILE=log_file)
    extra = {} if sys.platform == 'win32' else {'start_new_session': True}
    with open(console_file, 'w', encoding='utf-8') as console:
        proc = subprocess.Popen(command, env=env, stdout=console,
                                stderr=subprocess.STDOUT, **extra)
    try:
        deadline = time.monotonic() + args.timeout
        while not port_in_use(args.port):
            if proc.poll() is not None:
                raise AssertionError(
                    f'el proceso terminó (código {proc.returncode}) antes de abrir el API')
            if time.monotonic() > deadline:
                raise AssertionError(f'el API no abrió el puerto en {args.timeout:.0f} s')
            time.sleep(0.5)
        lines = check(args.port, args.version)
    except (AssertionError, OSError, ValueError, KeyError) as exc:
        stop(proc)
        print(f'SMOKE FAIL: {exc}')
        print(f'--- salida del proceso ({console_file}) ---')
        print(tail(console_file), end='')
        print(f'--- apipos.log ({log_file}) ---')
        print(tail(log_file), end='')
        return 1
    stop(proc)
    for line in lines:
        print(f'SMOKE {line}')
    print(f'SMOKE OK: {" ".join(command)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
