# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Read-only acceptance; retain counts/statuses, never account bodies or tokens."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    runner = Path(__file__).resolve().parents[1] / 'automation_integrations/api_read.py'
    rows = []

    def read(operation, params=None):
        response = subprocess.run(['/usr/bin/python3', str(runner), str(args.config)],
            input=json.dumps({'service': 'wirenboard', 'operation': operation, 'params': params or {}}),
            text=True, capture_output=True, timeout=100,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        try:
            result = json.loads(response.stdout)
        except Exception:
            result = {'ok': False, 'error': 'invalid_runner_response'}
        row = {k: result.get(k) for k in ('ok', 'error', 'http_status', 'result_state')}
        row.update(operation=operation, checked_at=dt.datetime.now(dt.timezone.utc).isoformat())
        if isinstance(result.get('data'), list):
            row['returned'] = len(result['data'])
        if 'pagination' in result:
            row['pagination'] = result['pagination']
        rows.append(row)
        print(json.dumps(row), flush=True)
        return result.get('data') if result.get('ok') else None

    read('me')
    organizations = read('organizations')
    read('counters')
    controllers = read('controllers', {'page_size': 20})
    candidates = controllers.get('results', []) if isinstance(controllers, dict) else []
    page = 1
    while isinstance(controllers, dict) and controllers.get('next') and page < 10:
        page += 1
        controllers = read('controllers', {'page_size': 20, 'page': page})
        candidates.extend(controllers.get('results', []) if isinstance(controllers, dict) else [])
    if isinstance(organizations, list) and organizations:
        grouped = next((c for c in candidates if c.get('group') and c.get('organization')), None)
        organization_id = grouped['organization']['id'] if grouped else organizations[0]['id']
        groups = read('groups', {'organization_id': organization_id})
        if isinstance(groups, list) and groups:
            read('group', {'id': groups[0]['id']})
        else:
            rows.append({'operation': 'group', 'ok': None, 'skipped': 'no_group_in_first_organization'})
    if candidates:
        controller = max(candidates, key=lambda c: c.get('lastMetricsAt') or '')
        serial = controller['serialNumber']
        read('controller', {'serial_number': serial})
        read('diagnostic', {'serial_number': serial})
        read('last_metrics_time', {'serial_number': serial})
        stop = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        read('metrics', {'serial_number': serial, 'name': 'mem_available',
            'start': (stop - dt.timedelta(hours=1)).isoformat(), 'stop': stop.isoformat()})
    report = {'service': 'wirenboard', 'transport': 'ssh:example-hermes',
        'business_writes': False, 'controller_actions': False,
        'passed': bool(rows) and all(row.get('ok') for row in rows),
        'controllers_observed': len(candidates),
        'all_controller_pages_read': isinstance(controllers, dict) and controllers.get('next') is None,
        'checks': rows}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
