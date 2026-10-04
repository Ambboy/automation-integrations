"""Publish compiled adapters into discovery without inventing live receipts."""
import datetime as dt
import json
from pathlib import Path

from automation_integrations import extended_api
from automation_integrations.api_read import OPERATIONS, LEGACY_OPERATIONS

ROOT = Path(__file__).resolve().parents[1]


def main():
    registry = ROOT / 'registry'
    catalog = json.loads((registry / 'catalog.json').read_text())
    catalog['version'] = '2026-10-04.3'
    summary = {}
    manifest_path = ROOT / 'docs/api-snapshots/2026-10-04/manifest.json'
    downloads = json.loads(manifest_path.read_text())['documents'] if manifest_path.exists() else []
    for service in catalog['services']:
        ident = service['id']
        # This service owns its explicit adapters and public OpenAPI inventory.
        if ident == 'wirenboard':
            continue
        compiled = extended_api.operations(ident)
        docpath = registry / 'capabilities' / (ident + '.json')
        doc = json.loads(docpath.read_text())
        raw_contract = json.loads((registry / 'contracts' / (ident + '.json')).read_text())
        blocked = raw_contract.get('unsupported', {})
        by_id = {}
        for name, row in compiled.items():
            by_id.setdefault(row['id'], []).append((name, row))
        if ident == 'saby':
            index = json.loads((ROOT / 'docs/api-snapshots/2026-10-04/saby-linked-methods.json').read_text())
            known = {row['id'] for row in doc['capabilities']}
            for item in index['methods']:
                if item['method_id'] not in known:
                    doc['capabilities'].append({'id': item['method_id'], 'method': 'JSON-RPC', 'path': None,
                        'summary': item['method_id'], 'effect': 'undetermined', 'parameters': [],
                        'source': item['source'], 'documentation_downloaded': item.get('download_status') == 'downloaded',
                        'adapter': None, 'execution': 'not_implemented', 'access': 'unverified',
                        'live_check': {'status': 'not_tested', 'reason': 'Expanded published directory; account entitlement unverified.'}})
                if not any(source['url'] == item['source'] for source in doc['sources']):
                    doc['sources'].append({'url': item['source']})
            doc['total'] = len(doc['capabilities'])
            doc['scope'] = ('Published EDO command directory and linked organization/department/employee/HR directories: '
                            '91 named methods. Separate licensing, signatures and service-account permissions are unverified. '
                            'Some downloaded pages contain only shells or contradictory request fields; see blocked reasons.')
            for row in doc['capabilities']:
                if row['id'] == 'СБИС.ИнформацияОКонтрагенте':
                    row['effect'] = 'business_write'
        for row in doc['capabilities']:
            is_legacy = row.get('adapter') in LEGACY_OPERATIONS[ident] or (ident == 'yandex_go' and row.get('adapter') in ('order_create', 'order_cancel'))
            if not is_legacy:
                row.update(adapter=None, execution='not_implemented')
                for key in ('additional_adapters', 'executable_contracts'):
                    row.pop(key, None)
            candidates = by_id.get(row['id'], [])
            if not candidates:
                reason = blocked.get(row['id'], blocked.get(row['id'].replace('-', '_')))
                if reason and row['execution'] == 'not_implemented':
                    row['unsupported_reasons'] = [reason]
                    row['implementation_status'] = 'blocked'
                continue
            supported = [(name, contract) for name, contract in candidates if not contract.get('unsupported_reason')]
            # Auth APIs stay owned by the transport. No model-supplied passwords.
            supported = [(name, contract) for name, contract in supported if contract['effect'] != 'authentication']
            if supported:
                primary_name, primary = supported[0]
                row['effect'] = primary['effect']
                row['path'] = primary['path']
                if row.get('adapter') not in LEGACY_OPERATIONS[ident]:
                    row['adapter'] = primary_name
                    row['access'] = 'unknown_not_tested'
                    row['live_check'] = {'status': 'not_tested', 'reason': 'New compiled adapter; see dated test evidence.'}
                row['execution'] = 'integration_read' if row['effect'] == 'read' else 'integration_write'
                row['additional_adapters'] = [name for name, _ in supported if name != row['adapter']]
                row['executable_contracts'] = {
                    name: {'params_schema': contract.get('params_schema', contract.get('parameters')),
                           'limits': contract.get('limitations', contract.get('notes', [])),
                           'source': contract.get('source'),
                           'response_kind': contract.get('response_kind', 'json')}
                    for name, contract in supported}
                row['implementation_status'] = 'compiled_and_validated'
            elif row.get('adapter') not in LEGACY_OPERATIONS[ident]:
                row['implementation_status'] = 'blocked'
                row['unsupported_reasons'] = sorted({r.get('unsupported_reason', 'transport_owned_authentication') for _, r in candidates})
        for source in doc.get('sources', []):
            match = next((r for r in downloads if r['url'] == source['url'] and r.get('status') == 'downloaded'), None)
            if match:
                source.update(sha256=match['sha256'], local_snapshot='docs/api-snapshots/2026-10-04/' + match['file'],
                              retrieved_at=match['downloaded_at'])
        doc['compiled_contract'] = 'registry/contracts/' + ident + '.json'
        doc['retrieved_at'] = '2026-10-04'
        docpath.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
        # Remove stale generated aliases when re-running after a contract correction.
        service['operations'] = {name: spec for name, spec in service['operations'].items()
                                 if name in LEGACY_OPERATIONS[ident]}
        writes = {name: spec for name, spec in service.get('write_operations', {}).items()
                  if ident == 'yandex_go' and name in ('order_create', 'order_cancel')}
        for name, row in compiled.items():
            if row.get('unsupported_reason') or row['effect'] == 'authentication' or name in LEGACY_OPERATIONS[ident]:
                continue
            entry = {'summary': row.get('summary', name),
                     'params': {section: 'Exact nested schema: view=capabilities, capability_id=' + row['id']
                                for section in ('path', 'query', 'body', 'headers')},
                     'capability_id': row['id'], 'effect': row['effect'], 'access': 'unknown_not_tested'}
            (service['operations'] if row['effect'] == 'read' else writes)[name] = entry
        service['write_operations'] = writes
        service['adapter_status'] = 'Legacy operations plus schema-validated compiled contracts; account rights are per-operation.'
        addition = ('\nРасширенные операции принимают вложенные path/query/body/headers; точная схема — '
                    'view=capabilities с capability_id. Запись и генерация отчётов выполняются только через '
                    'integration_write: prepare(service,operation,params), отдельное новое сообщение владельца '
                    'с точной командой подтверждения, execute. Неопределённую отправку не повторять. '
                    'accepted_unverified означает принятие запроса провайдером, не окончательный бизнес-результат. '
                    'PDF сохраняются закрыто, инструмент возвращает путь/размер/хеш.')
        if addition not in service['instructions']:
            service['instructions'] += addition
        summary[ident] = {'documented': doc['total'], 'read_tool_operations': len(service['operations']),
                          'write_tool_operations': len(writes),
                          'executable_documented_methods': sum(r['execution'] != 'not_implemented' for r in doc['capabilities']),
                          'blocked': [{'id': r['id'], 'reasons': r.get('unsupported_reasons', ['no_executable_contract'])}
                                      for r in doc['capabilities'] if r['execution'] == 'not_implemented']}
        assert set(service['operations']) == set(OPERATIONS[ident])
    (registry / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'docs/API_IMPLEMENTATION_SUMMARY.json').write_text(json.dumps({
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'services': summary,
        'production_writes_tested': False}, ensure_ascii=False, indent=2) + '\n')
    # ETM's order manual supplements its null OpenAPI body; checkout is a
    # separate portal workflow. Preserve both across general catalog refreshes.
    from ops.extend_etm_catalog import update as update_etm
    update_etm(ROOT)
    current = json.loads((registry / 'catalog.json').read_text())
    etm = next(s for s in current['services'] if s['id'] == 'etm')
    summary['etm'].update(read_tool_operations=len(etm['operations']),
                          write_tool_operations=len(etm['write_operations']),
                          executable_documented_methods=19, blocked=[],
                          website_checkout='implemented; read-only live checks, production order not placed')
    (ROOT / 'docs/API_IMPLEMENTATION_SUMMARY.json').write_text(json.dumps({
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'services': summary,
        'production_writes_tested': False}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
