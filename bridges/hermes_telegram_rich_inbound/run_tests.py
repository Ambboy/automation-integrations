"""Run offline tests using the installed managed Hermes interpreter, without PM changes."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if os.environ.get('RICH_INBOUND_MANAGED_TEST') != '1':
    command = json.loads(subprocess.check_output(['hermes', '--print-runtime-command'], text=True))
    old = "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
    assert old in command[-1], 'Unrecognized runtime bootstrap; refusing to guess'
    command[-1] = command[-1].replace(old, f"runpy.run_path({str(Path(__file__).resolve())!r}, run_name='__main__')")
    env = dict(os.environ, RICH_INBOUND_MANAGED_TEST='1', PYTHONDONTWRITEBYTECODE='1')
    env['RICH_TEST_ARGS'] = json.dumps(sys.argv[1:])
    raise SystemExit(subprocess.call(command, env=env, cwd=ROOT))

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
# Fail closed on any attempted external transport, including DNS.
def deny_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        raise RuntimeError('Offline test forbids network')
sys.addaudithook(deny_network)
import unittest
args = json.loads(os.environ.get('RICH_TEST_ARGS', '[]'))
suite = unittest.defaultTestLoader.loadTestsFromNames(args) if args else unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
