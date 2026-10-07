"""Bounded Cloud SSH web-terminal execution; cloud authentication stays with the caller.

Every command is an explicit management action. The worker receives the tunnel
URL and SSH credentials only through stdin and never loads another client's tokens.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys


class ShellFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


_REMOTE_PYTHON = '/home/operator/.hermes/hermes-agent/venv/bin/python'
_REMOTE_SCRIPT = r'''
import base64
import json
import re
import shlex
import sys
import time
import urllib.parse
import uuid

MAX_INPUT = 128 * 1024
MAX_OUTPUT = 64 * 1024
MAX_TRANSCRIPT = 256 * 1024
ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))')

class WorkerFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def trusted_url(value, serial):
    if not isinstance(value, str) or not 1 <= len(value) <= 16384 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise WorkerFailure('invalid_tunnel_url')
    try:
        parts = urllib.parse.urlsplit(value)
        valid = (parts.scheme == 'https' and parts.hostname == serial.lower() + '.ssh.wirenboard.cloud'
                 and parts.port in (None, 443) and not parts.username and not parts.password
                 and not parts.fragment and '\\' not in value)
    except ValueError:
        valid = False
    if not valid:
        raise WorkerFailure('untrusted_tunnel_origin')
    return value

def validate(request):
    if not isinstance(request, dict) or set(request) != {'serial_number', 'tunnel_url', 'command', 'credentials', 'timeout'}:
        raise WorkerFailure('invalid_shell_request')
    serial = request['serial_number']
    if not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', serial):
        raise WorkerFailure('invalid_serial_number')
    trusted_url(request['tunnel_url'], serial)
    command = request['command']
    if not isinstance(command, list) or not 1 <= len(command) <= 64:
        raise WorkerFailure('invalid_shell_command')
    if any(not isinstance(arg, str) or '\x00' in arg for arg in command) or not command[0]:
        raise WorkerFailure('invalid_shell_command')
    if sum(len(arg.encode('utf-8')) for arg in command) > 65536:
        raise WorkerFailure('shell_command_too_large')
    if type(request['timeout']) is not int or not 1 <= request['timeout'] <= 30:
        raise WorkerFailure('invalid_shell_timeout')
    credentials = request['credentials']
    if not isinstance(credentials, dict) or set(credentials) - {'username', 'password', 'privatekey', 'passphrase'}:
        raise WorkerFailure('invalid_ssh_credentials')
    if any(not isinstance(value, str) or len(value.encode('utf-8')) > 32768 or '\x00' in value for value in credentials.values()):
        raise WorkerFailure('invalid_ssh_credentials')
    if 'username' in credentials and (not credentials['username'] or any(ord(c) < 32 for c in credentials['username'])):
        raise WorkerFailure('invalid_ssh_credentials')

def clean(text):
    return ANSI.sub('', text).replace('\r', '')

def extract_result(text, start, end):
    value = clean(text)
    begin = re.search(r'(?m)^' + re.escape(start) + r'\n', value)
    if not begin:
        return None
    complete = re.search(r'(?m)^' + re.escape(end) + r':([0-9]{1,3})(?:\n|$)', value[begin.end():])
    if not complete:
        return None
    output = value[begin.end():begin.end() + complete.start()]
    # The wrapper adds exactly one newline before the completion marker.
    if output.endswith('\n'):
        output = output[:-1]
    code = int(complete.group(1))
    if code > 255:
        raise WorkerFailure('invalid_shell_result')
    if len(output.encode('utf-8')) > MAX_OUTPUT:
        raise WorkerFailure('shell_output_too_large_outcome_unknown')
    return output, code

def framed_command(command):
    start = '__WB_START_' + uuid.uuid4().hex + '__'
    end = '__WB_END_' + uuid.uuid4().hex + '__'
    script = ("printf '%s\\n' " + shlex.quote(start) + '\nset +e\n' + shlex.join(command)
              + "\nrc=$?\nprintf '\\n%s:%s\\n' " + shlex.quote(end) + ' "$rc"\n')
    encoded = base64.b64encode(script.encode('utf-8')).decode('ascii')
    return 'printf %s ' + shlex.quote(encoded) + ' | base64 -d | /bin/sh\n', start, end

def terminal_ids(answer):
    if not isinstance(answer, dict):
        raise WorkerFailure('invalid_terminal_response')
    if not answer.get('id') or not answer.get('client_id'):
        # The live provider uses a namespaced error code. Never echo its status
        # text, which may contain hostnames, internal addresses, or credentials.
        error = answer.get('error_code')
        normalized = re.sub(r'[^A-Za-z0-9]+', '_', error).strip('_').lower() if isinstance(error, str) and len(error) < 80 else ''
        if normalized in ('error_auth_failed', 'auth_failed'):
            raise WorkerFailure('ssh_authentication_failed')
        raise WorkerFailure('terminal_session_rejected')
    ids = {}
    for key in ('id', 'client_id'):
        value = answer[key]
        if type(value) is int and value > 0:
            value = str(value)
        if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise WorkerFailure('invalid_terminal_response')
        ids[key] = value
    return ids

def perform(request):
    validate(request)
    # Imports occur only after request validation; tests and inventory stay offline.
    import requests
    from websockets.sync.client import connect
    session = requests.Session()
    session.trust_env = False
    deadline = time.monotonic() + request['timeout']
    sent = False
    private_values = []
    credentials = {'username': 'root', 'password': 'wirenboard', 'privatekey': '', 'passphrase': ''}
    credentials.update(request['credentials'])
    if credentials['privatekey'] and 'password' not in request['credentials']:
        credentials['password'] = ''
    private_values += [value for key, value in credentials.items() if key != 'username' and value and value != 'wirenboard']
    private_values.append(request['tunnel_url'])
    private_values += [value for _, value in urllib.parse.parse_qsl(urllib.parse.urlsplit(request['tunnel_url']).query) if value]

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise WorkerFailure('shell_timeout_outcome_unknown' if sent else 'shell_connection_timeout')
        return max(0.01, seconds)

    try:
        current = request['tunnel_url']
        for _ in range(5):
            trusted_url(current, request['serial_number'])
            response = session.get(current, allow_redirects=False, timeout=min(remaining(), 10), stream=True, verify=True)
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('Location')
                    if not location:
                        raise WorkerFailure('tunnel_redirect_invalid')
                    current = trusted_url(urllib.parse.urljoin(current, location), request['serial_number'])
                    continue
                if response.status_code != 200:
                    raise WorkerFailure('tunnel_unavailable')
                break
            finally:
                response.close()
        else:
            raise WorkerFailure('tunnel_redirect_limit')
        host = request['serial_number'].lower() + '.ssh.wirenboard.cloud'
        base = 'https://' + host
        response = session.post(base + '/', files={key: (None, value) for key, value in credentials.items()},
                                allow_redirects=False, timeout=min(remaining(), 10), stream=True, verify=True)
        try:
            if response.status_code != 200:
                raise WorkerFailure('ssh_authentication_failed')
            raw = bytearray()
            for chunk in response.iter_content(4096):
                remaining()
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise WorkerFailure('invalid_terminal_response')
            answer = json.loads(raw)
        finally:
            response.close()
        answer = terminal_ids(answer)
        private_values += [answer['id'], answer['client_id']]
        cookie = '; '.join(key + '=' + value for key, value in session.cookies.items())
        private_values += list(session.cookies.values())
        if len(cookie) > 32768 or any(ord(c) < 32 for c in cookie):
            raise WorkerFailure('invalid_terminal_cookie')
        ws_url = 'wss://' + host + '/ws?' + urllib.parse.urlencode({key: answer[key] for key in ('id', 'client_id')})
        launcher, start, end = framed_command(request['command'])
        transcript = ''
        with connect(ws_url, additional_headers={'Cookie': cookie}, open_timeout=min(remaining(), 10), close_timeout=1,
                     max_size=MAX_TRANSCRIPT, ping_interval=10, ping_timeout=10, proxy=None) as websocket:
            websocket.send(json.dumps({'resize': [160, 50]}))
            sent = True
            websocket.send(json.dumps({'data': launcher}))
            while True:
                message = websocket.recv(timeout=remaining())
                if isinstance(message, bytes):
                    message = message.decode('utf-8', 'replace')
                if not isinstance(message, str):
                    raise WorkerFailure('invalid_terminal_response')
                transcript += message
                if len(transcript.encode('utf-8')) > MAX_TRANSCRIPT:
                    raise WorkerFailure('shell_output_too_large_outcome_unknown')
                result = extract_result(transcript, start, end)
                if result is not None:
                    output, code = result
                    for private in sorted(set(private_values), key=len, reverse=True):
                        if private:
                            output = output.replace(private, '[redacted]')
                    return {'stdout': output, 'exit_code': code}
    except WorkerFailure:
        raise
    except Exception:
        raise WorkerFailure('shell_outcome_unknown' if sent else 'shell_connection_failed') from None
    finally:
        session.close()

def main():
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise WorkerFailure('invalid_shell_request')
        result = perform(json.loads(raw))
        response = {'ok': True, 'data': result}
    except WorkerFailure as exc:
        response = {'ok': False, 'code': exc.code}
    except Exception:
        response = {'ok': False, 'code': 'shell_connection_failed'}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(',', ':')))

if __name__ == '__main__':
    main()
'''


class ShellTransport:
    def __init__(self, egress='example-hermes'):
        if egress not in ('example-hermes', 'direct'):
            raise ShellFailure('unsupported_shell_egress')
        self.egress = egress

    def call(self, serial_number, tunnel_url, command, credentials=None, timeout=30):
        request = {'serial_number': serial_number, 'tunnel_url': tunnel_url, 'command': command,
                   'credentials': {} if credentials is None else credentials, 'timeout': timeout}
        namespace = {'__name__': 'wb_shell_validation'}
        exec(_REMOTE_SCRIPT, namespace)
        try:
            namespace['validate'](request)
            payload = json.dumps(request, ensure_ascii=False, allow_nan=False)
        except Exception as exc:
            raise ShellFailure(getattr(exc, 'code', 'invalid_shell_request')) from None
        if len(payload.encode('utf-8')) > 128 * 1024:
            raise ShellFailure('invalid_shell_request')
        argv = [sys.executable, '-c', _REMOTE_SCRIPT]
        if self.egress == 'example-hermes':
            argv = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
                    'example-hermes', shlex.join([_REMOTE_PYTHON, '-c', _REMOTE_SCRIPT])]
        try:
            result = subprocess.run(argv, input=payload, text=True, capture_output=True, timeout=timeout + 12, check=False)
        except subprocess.TimeoutExpired:
            raise ShellFailure('shell_timeout_outcome_unknown') from None
        except OSError:
            raise ShellFailure('shell_transport_failed') from None
        if result.returncode or len(result.stdout.encode('utf-8')) > 512 * 1024:
            raise ShellFailure('shell_transport_failed_outcome_unknown')
        try:
            response = json.loads(result.stdout)
            if response.get('ok') is not True:
                code = response.get('code', 'shell_transport_failed')
                if not isinstance(code, str) or not code.replace('_', '').isalnum() or len(code) > 100:
                    code = 'shell_transport_failed'
                raise ShellFailure(code)
            data = response['data']
            if (set(data) != {'stdout', 'exit_code'} or not isinstance(data['stdout'], str)
                    or len(data['stdout'].encode('utf-8')) > 65536 or type(data['exit_code']) is not int
                    or not 0 <= data['exit_code'] <= 255):
                raise ValueError()
            return data
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ShellFailure('invalid_shell_response') from None
