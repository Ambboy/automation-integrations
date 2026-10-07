"""Reproducible inventory of every API contract and executable parameter schema.

Offline by default. The output contains public contracts only, never credentials
or provider account responses. Live acceptance is recorded separately.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from automation_integrations import api_read, documented_contract, media_api
from automation_integrations.catalog import Catalog


ROOT = Path(__file__).resolve().parents[1]


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def inventory(root=ROOT):
    root = Path(root)
    cards = {row['id']: row for row in Catalog(root / 'registry/catalog.json').load()['services']}
    services, problems = {}, []
    for path in sorted((root / 'registry/capabilities').glob('*.json')):
        service = path.stem
        capabilities = load(path)
        contract_path = root / 'registry/contracts' / path.name
        contract = load(contract_path) if contract_path.exists() else {}
        operations = contract.get('operations', {})
        card = cards.get(service, {})
        documented = {}
        for row in capabilities['capabilities']:
            ident = row['id']
            if ident in documented:
                problems.append(service + ': duplicate capability ' + ident)
            documented[ident] = {key: deepcopy(row[key]) for key in (
                'method', 'path', 'summary', 'source', 'source_kind', 'effect', 'adapter',
                'parameters', 'request_body', 'security', 'params_schema', 'executable_contracts',
                'implementation_status', 'unsupported_reason', 'limitations') if key in row}
        executable = {}
        for name, row in operations.items():
            # fal's `parameters` is the OpenAPI path/query/header list; its
            # complete tool input (including request body) lives in `schema`.
            schema = row.get('params_schema', row.get('schema', row.get('parameters', {})))
            executable[name] = {'contract_id': row.get('id', name),
                'effect': row.get('effect'), 'method': row.get('method'), 'path': row.get('path'),
                'source': row.get('source'), 'parameters': deepcopy(schema),
                'unsupported_reason': row.get('unsupported_reason'),
                'available_in_catalog': name in card.get('operations', {}) or name in card.get('write_operations', {})}
            if service == 'abcp':
                executable[name]['available_in_standalone_abcp_plugin'] = True
            if service in ('yandex_go', 'saby'):
                compiled = documented_contract.operations(service).get(name, {})
                for key in ('requires_idempotency_key', 'unsupported_reason'):
                    if key in compiled:
                        executable[name][key] = deepcopy(compiled[key])
        for field in ('operations', 'write_operations'):
            for name, spec in card.get(field, {}).items():
                entry = executable.setdefault(name, {'parameters': {}})
                entry.update(available_in_catalog=True, tool=('integration_read' if field == 'operations' else 'integration_write'))
                entry['catalog_parameters'] = deepcopy(spec.get('params', {}))
                if not entry['parameters']:
                    entry['parameters'] = deepcopy(spec.get('schema') or spec.get('params_schema') or {})
                if not entry['parameters']:
                    detailed = next((row for row in capabilities['capabilities']
                                     if row.get('adapter') == name and row.get('params_schema')), None)
                    if detailed:
                        entry['parameters'] = deepcopy(detailed['params_schema'])
                    elif service in media_api.SERVICES:
                        entry['parameters'] = deepcopy(media_api.module(service).OPERATION_SCHEMAS.get(name, {}))
                    else:
                        entry['parameter_contract'] = 'Fixed adapter parameters; see catalog_parameters and referenced validator.'
        for name, entry in executable.items():
            entry['schema_coverage'] = ('schema_present_documentation_may_be_partial' if entry['parameters']
                                        else 'catalog_descriptions_and_python_validator')
            entry['validator_sources'] = ([
                'automation_integrations/abcp_api.py'] if service == 'abcp' else [
                'automation_integrations/wirenboard.py', 'automation_integrations/wirenboard_control_contract.py',
                'automation_integrations/wirenboard_shell.py'] if service == 'wirenboard' else [
                'automation_integrations/media_api.py', 'automation_integrations/' + service.replace('inference', 'inference_media').replace('fal', 'fal_media') + '.py']
                if service in media_api.SERVICES else ['automation_integrations/api_read.py',
                'automation_integrations/extended_api.py', 'automation_integrations/openapi_contract.py',
                'automation_integrations/documented_contract.py'])
        if card:
            expected = set(api_read.OPERATIONS.get(service, {}))
            if set(card['operations']) != expected:
                problems.append(service + ': read catalog does not match runtime')
        references = [path]
        if contract_path.exists():
            references.append(contract_path)
        services[service] = {
            'scope': capabilities.get('scope'),
            'documentation_sources': capabilities.get('sources', contract.get('sources', [])),
            'contract_files': [{'path': str(p.relative_to(root)), 'sha256': file_sha(p)} for p in references],
            'capabilities_count': len(documented),
            'contract_operations_count': len(operations) if contract_path.exists() else None,
            'contract_storage': 'contracts_json' if contract_path.exists() else 'capabilities_and_python_validators',
            'runtime_reads': (len(card.get('operations', {})) if card else
                              sum(row.get('effect') == 'read' for row in operations.values())),
            'runtime_writes': (len(card.get('write_operations', {})) if card else
                               sum(row.get('effect') != 'read' for row in operations.values())),
            'deployment_target': 'Standalone ABCP plugin' if service == 'abcp' else 'Main API plugin',
            'documented': documented, 'executable': executable,
        }
    return {'schema_version': 1, 'scope': 'Public API contracts and local adapters. No claim of account rights or end-to-end success.',
            'services': services, 'problems': problems, 'passed': not problems,
            'consistency_checks': ['unique capability IDs', 'main catalog read names match runtime'],
            'not_checked': ['installed bytes', 'account permissions', 'live business outcomes',
                            'full JSON schema for every legacy alias', 'undocumented provider constraints']}


def render(report):
    lines = ['# Реестр параметров коннекторов', '',
        'Собрано из действующих машинных контрактов и каталога. Опубликованные вложенные параметры, обязательность, типы, '
        'enum, ограничения и источники находятся в [parameter-index.json](parameter-index.json). '
        'Пробелы типизации в документации и параметры старых имён отмечены через schema_coverage; для них приведены '
        'описания каталога и пути проверяющего кода. '
        'Документированные методы, исполняемые операции и успешные живые сценарии — разные показатели.', '',
        '| Подключение | В реестре возможностей | В контракте | Чтения | Записи |',
        '|---|---:|---:|---:|---:|']
    for service, row in report['services'].items():
        count = row['contract_operations_count'] if row['contract_operations_count'] is not None else '—'
        lines.append(f"| {service} | {row['capabilities_count']} | {count} | {row['runtime_reads']} | {row['runtime_writes']} |")
    lines += ['', 'Числа чтений/записей включают совместимые имена и локальные операции. '
              'ЭТМ включает явно отмеченные внутренние методы сайта; они не являются официальным публичным API. '
              'Для Wiren Board основой служит полный реестр OpenAPI и отдельные явные адаптеры.', '',
              'Проверка согласованности: ' + ('успешна.' if report['passed'] else 'есть ошибки.'), '']
    for problem in report['problems']:
        lines.append('- ' + problem)
    lines += ['', 'Воспроизведение из корня репозитория:', '', '```bash',
              'python3 -m ops.connector_audit --output docs/connector-audit/2026-10-07', '```', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inventory()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'parameter-index.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'README.md').write_text(render(report))
    print(json.dumps({'services': len(report['services']), 'passed': report['passed'],
                      'problems': report['problems']}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
