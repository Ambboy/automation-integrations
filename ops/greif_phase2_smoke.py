# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Explicit real rewrite+verification+TTS via native command provider, no Telegram sends."""
import json
import os
import shlex
import sys
from pathlib import Path
from unittest.mock import patch

if sys.argv[1:] != ['--execute']:
    raise SystemExit('Requires --execute: two main-model calls and speech synthesis')
os.umask(0o077)
r = Path('/home/operator/.local/share/automation-integrations/greif/phase2')
assert not (r / 'smoke-attempt.json').exists(), 'Inspect previous attempt before retrying'
(r / 'smoke-attempt.json').write_text('{"state":"started"}')
sys.path.insert(0, str(r / 'release'))
from automation_integrations.speech_source import Sources
from tools.tts_text_normalize import prepare_spoken_text
from tools.tts_tool import text_to_speech_tool
source = json.loads((r / 'input.json').read_text())
cleaned = prepare_spoken_text(prepare_spoken_text(source['original'], max_chars=None), max_chars=None)
Sources(r / 'sources').put('phase2-smoke', cleaned, source['original'], source['context'])
command = shlex.join(['/home/operator/.local/share/automation-integrations/greif/venv/bin/python',
                     str(r / 'release/command.py'), 'tts', '--config', str(r / 'tts.json')])
command += ' --input {input_path} --output {output_path}'
config = {'provider': 'automation-speech', 'providers': {'automation-speech': {
    'type': 'command', 'command': command, 'output_format': 'wav', 'voice_compatible': True,
    'max_text_length': 50000, 'timeout': 700}}}
(r / 'tts-provider.json').write_text(json.dumps(config, indent=2))
os.environ['HERMES_SESSION_PLATFORM'] = 'telegram'
with patch('tools.tts_tool._load_tts_config', return_value=config):
    result = json.loads(text_to_speech_tool(cleaned, output_path=str(r / 'result.wav')))
assert result.get('success') and result.get('voice_compatible'), {k:result.get(k) for k in ['success','error']}
report = {'passed': True, 'audio': result['file_path'], 'provider': result['provider'],
          'voice_compatible': result['voice_compatible'], 'telegram_sent': False}
(r / 'smoke-report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
