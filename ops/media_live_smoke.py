# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Explicit, idempotent provider validation; no Telegram message is sent.

Uses a clearly synthetic owner-route fixture to exercise the installed runner
contract. This is not evidence of a real inbound Telegram conversation.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
from automation_integrations import media_api


def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--execute' or sys.argv[2] not in ('fal', 'inference'):
        raise SystemExit('Use --execute fal|inference; performs one small paid generation at most.')
    service = sys.argv[2]
    base = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
    config = json.loads((base / 'private.json').read_text())
    for name in ('fal', 'inference'):
        config['item_ids'][name] = 'e06835f1-a55f-48df-b433-b71b3c53f551'
    config['media_authorization'] = 'owner_command'
    scope = ['integration-validation', 'integration-validation', 'media-20261004', '']
    message = 'media-20261004-' + service
    context = {'scope': scope, 'message_id': message, 'owner_message': {
        'source': 'native_owner_telegram', 'message_id': message, 'scope': scope,
        'text_sha256': hashlib.sha256(b'Authorized integration verification; synthetic route fixture.').hexdigest()}}
    prompt = 'A small red circle on a plain white background. Minimal flat icon.'
    params = {'endpoint_id': 'fal-ai/flux/schnell', 'input': {'prompt': prompt,
        'image_size': {'width': 256, 'height': 256}, 'num_images': 1,
        'num_inference_steps': 4, 'seed': 42}} if service == 'fal' else {
        'app': 'pruna/flux-dev', 'input': {'prompt': prompt, 'image_size': 512,
            'num_inference_steps': 4, 'output_format': 'png', 'seed': 42}}
    operation = 'submit' if service == 'fal' else 'app_run'
    prepared = media_api.process({'action': 'prepare', 'service': service,
        'operation': operation, 'params': params}, context, config)
    if not prepared.get('ok'):
        raise SystemExit(json.dumps(prepared, ensure_ascii=False))
    ident = prepared['job_id']
    print(json.dumps({'phase': 'prepared', 'service': service, 'job_id': ident,
                      'estimate': prepared.get('preview', {}).get('estimate')}), flush=True)
    if prepared['status'] == 'prepared':
        result = media_api.process({'action': 'execute', 'draft_id': ident}, context, config)
        print(json.dumps({'phase': 'executed', 'service': service, 'ok': result['ok'],
                          'status': result.get('status'), 'error': result.get('error')}), flush=True)
        if not result['ok']:
            raise SystemExit('Inspect persisted job; never rerun a generation with uncertain outcome.')
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        status = media_api.read(service, 'job_result', {'job_id': ident}, config)['data']
        if status['status'] in ('completed', 'failed', 'cancelled', 'outcome_unknown', 'rejected'):
            break
        print(json.dumps({'phase': 'poll', 'service': service, 'status': status['status']}), flush=True)
        time.sleep(5)
    response = status.get('result', {})
    payload = response.get('output', response) if isinstance(response, dict) else response
    ids = []
    def collect(value):
        if isinstance(value, dict):
            if value.get('artifact_id'):
                ids.append(value['artifact_id'])
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(payload)
    artifacts = [media_api.read(service, 'artifact_download', {'artifact_id': item}, config)['data']
                 for item in dict.fromkeys(ids)] if status['status'] == 'completed' else []
    report = {'service': service, 'job_id': ident, 'status': status['status'],
              'provider_job_id': status.get('provider_job_id'), 'billing': status.get('billing'),
              'artifacts': artifacts, 'route': 'synthetic integration fixture; no Telegram message',
              'passed': status['status'] == 'completed' and bool(artifacts)}
    media_api._save(base / 'update-20261004-media' / ('live-' + service + '.json'), report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
