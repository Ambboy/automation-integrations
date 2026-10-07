# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Bounded production read checks; never create test business objects.

Only public ETM goods IDs or IDs returned by an authorized read are used.
Business response bodies and identifiers stay in memory, outside the report.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import sys

from automation_integrations.api_read import execute, Failure, Vault, atomic

ROOT = Path('/home/operator/.local/share/automation-integrations/greif/api-catalog')
PROJECT = Path(__file__).resolve().parents[1]


class CachedVault(Vault):
    def __init__(self, config):
        super().__init__(config)
        self.values = {}

    def get(self, service):
        if service not in self.values:
            self.values[service] = super().get(service)
        return self.values[service]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--only', action='append', default=[])
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit('Requires --execute: current provider accounts, read operations only.')
    os.umask(0o077)
    config = json.loads((ROOT / 'private.json').read_text())

    def check(service):
        rows, results = [], {}
        vault = CachedVault(config)

        def run(operation, params=None):
            if args.only and service + '.' + operation not in args.only:
                return None
            row = {'service': service, 'operation': operation, 'environment': 'production',
                   'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'business_write': False}
            try:
                result = execute({'service': service, 'operation': operation, 'params': params or {}}, config, vault=vault)
                data = result['data']; results[operation] = data
                row.update(ok=True, keys=list(data)[:20] if isinstance(data, dict) else [],
                           result_state=result.get('result_state'))
            except Failure as exc:
                row.update(ok=False, error=exc.code, http_status=exc.status)
            except Exception as exc:
                row.update(ok=False, error=type(exc).__name__)
            rows.append(row)
            atomic(ROOT / 'state' / (service + '.' + operation + '.json'), row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            return results.get(operation)

        if service == 'yandex_go':
            users = run('users', {'limit': 1}) or {}
            orders = run('orders', {'limit': 1}) or {}
            for name in ('cost_center_list', 'department_list', 'region_list', 'limit_list'):
                run(name, {'query': {'limit': 1, 'offset': 0}})
            for name in ('promocodes_list', 'role_list'):
                run(name, {'query': {'limit': 1}})
            run('vehicles_list', {'query': {'limit': 1}})
            run('travels_list', {'body': {'limit': 1}})
            run('food_list', {'query': {'limit': 1}, 'body': {}})
            if users.get('items'):
                user = users['items'][0]['id']
                run('user_info', {'query': {'user_id': user}})
                run('users_spending_details', {'body': {'user_ids': [user]}})
            if orders.get('items'):
                ident = orders['items'][0]['id']
                run('order_get', {'query': {'order_id': ident}})
                run('order_progress', {'query': {'order_id': ident}})
                run('taxi_report', {'body': {'ids': [ident]}})
        elif service == 'etm':
            run('goods_get', {'path': {'id': '5301409'}, 'query': {'type': 'etm'}})
            run('goods_price', {'path': {'id': '5301409'}, 'query': {'type': 'etm'}})
            run('goods_remains', {'path': {'id': '5301409'}, 'query': {'type': 'etm'}})
            run('catalog_search', {'query': {'val': '5301409', 'type': 'code'}})
            run('reference_search', {'path': {'type': 'r-manuf'}, 'query': {'term': 'IEK', 'page': 1, 'rows': 1}})
            today = dt.date.today()
            invoices = run('invoices', {'date_from': (today - dt.timedelta(days=30)).isoformat(),
                                        'date_to': today.isoformat(), 'limit': 1}) or {}
            existing = invoices.get('data', {}).get('rows', [])
            if existing:
                params = {'path': {'id': str(existing[0]['id'])}}
                run('invoice_get', params)
                run('invoice_approvals', params)
        elif service == 'saby':
            run('current_user', {'body': {'Параметр': {}}})
            run('organizations_list', {'body': {'Фильтр': {'Навигация': {'РазмерСтраницы': '1', 'Страница': '0'}}}})
            page = {'РазмерСтраницы': '1', 'Страница': '0'}
            filt = {'НашаОрганизация': {'СвЮЛ': config['saby_org']}}
            run('departments_list', {'body': {'Параметр': {'Фильтр': filt, 'Навигация': page}}})
            run('employees_list', {'body': {'Параметр': {'Фильтр': filt, 'Навигация': page}}})
            run('documents_list', {'body': {'Фильтр': {**filt, 'Тип': 'ДокОтгрВх', 'Навигация': page}}})
            run('version_info', {'body': {'Параметр': {}}})
        return rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(pool.map(check, ('yandex_go', 'etm', 'saby')))
    rows = [row for batch in batches for row in batch]
    if args.only and (PROJECT / 'docs/EXPANDED_READ_AUDIT.json').exists():
        previous = json.loads((PROJECT / 'docs/EXPANDED_READ_AUDIT.json').read_text())
        rows = previous['checks'] + rows
    latest = {(r['service'], r['operation']): r for r in rows}
    report = {'latest_distinct_operations': len(latest), 'latest_passed': sum(r['ok'] for r in latest.values()),
              'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope': 'New adapter reads on current accounts; no production business mutations.',
              'checks': rows, 'passed': sum(row['ok'] for row in rows), 'attempted': len(rows)}
    atomic(ROOT / 'expanded-read-smoke-20261004.json', report)
    (PROJECT / 'docs/EXPANDED_READ_AUDIT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'attempted': len(rows), 'passed': report['passed']}))


if __name__ == '__main__':
    main()
