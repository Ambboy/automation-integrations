"""Build the Wiren Board capability inventory from its public OpenAPI schema.

No account requests or credentials are used. Download the schema separately from
https://wirenboard.cloud/api/v1/docs/schema/ and pass the saved YAML/JSON file.
PyYAML is a build-time dependency, as in build_capabilities.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import yaml


SOURCE = "https://wirenboard.cloud/api/v1/docs/schema/"
ADAPTERS = {
    "GET /api/v1/users/me/": "me",
    "GET /api/v1/organizations/": "organizations",
    "GET /api/v1/controllers/": "controllers",
    "GET /api/v1/controllers-count/": "counters",
    "GET /api/v1/controllers/{serialNumber}/": "controller",
    "GET /api/v1/controllers/{serialNumber}/diagnostic/": "diagnostic",
    "POST /api/v1/controllers/{serialNumber}/system-metrics/": "metrics",
    "GET /api/v1/groups/": "groups",
    "GET /api/v1/groups/{id}/": "group",
    "GET /api/v1/controllers/{serialNumber}/last-metrics-time/": "last_metrics_time",
}
WRITE_ADAPTERS = {
    'PATCH /api/v1/controllers/{serialNumber}/': 'controller_update',
    'DELETE /api/v1/controllers/{serialNumber}/': 'controller_delete',
    'POST /api/v1/controllers/{serialNumber}/request-diagnostic/': 'request_diagnostic',
    'POST /api/v1/controllers/{serialNumber}/services/': 'service_add',
    'PATCH /api/v1/controllers/{serialNumber}/services/{port}/': 'service_update',
    'DELETE /api/v1/controllers/{serialNumber}/services/{port}/': 'service_delete',
    'POST /api/v1/groups/': 'group_create',
    'PATCH /api/v1/groups/{id}/': 'group_update',
    'DELETE /api/v1/groups/{id}/': 'group_delete',
    'POST /api/v1/groups/{id}/attach-controllers/': 'group_attach',
    'POST /api/v1/groups-detach-from-controllers/': 'group_detach',
}
COMPOSITE_ADAPTERS = {
    'POST /api/v1/controllers/{serialNumber}/tcp-tunnels/{identifier}/': 'controller_exec',
}


def write_operations():
    """Friendly exact parameter contracts for the confirmed local workflow."""
    def obj(properties, required, **extra):
        return {'type': 'object', 'properties': properties, 'required': required,
                'additionalProperties': False, **extra}

    serial = {'type': 'string', 'minLength': 1, 'maxLength': 36, 'pattern': '^[A-Za-z0-9_-]+$'}
    identifier = {'type': 'string', 'format': 'uuid'}
    parent = {'type': ['string', 'null'], 'format': 'uuid'}
    port = {'type': 'integer', 'minimum': 1, 'maximum': 65535}
    name = {'type': 'string', 'minLength': 1, 'maxLength': 255}
    label = {'type': 'string', 'maxLength': 64}
    controllers = {'type': 'array', 'minItems': 1, 'maxItems': 20, 'uniqueItems': True, 'items': serial,
                   'description': 'Local batch limit; normalized uppercase; duplicates after normalization rejected.'}
    coordinate = lambda bound: {'anyOf': [
        {'type': 'string', 'pattern': r'^-?\d{1,3}(?:\.\d{1,7})?$'},
        {'type': 'number', 'minimum': -bound, 'maximum': bound, 'multipleOf': 0.0000001},
        {'type': 'null'}], 'description': f'Finite decimal within {-bound}..{bound}, up to seven fractional digits; sent as decimal string or null.'}
    fields = obj({'description': {'type': ['string', 'null'], 'maxLength': 255},
                  'latitude': coordinate(90), 'longitude': coordinate(180),
                  'userDefinedData': {'type': ['array', 'null'], 'maxItems': 100,
                                      'items': obj({'label': {'type': 'string', 'minLength': 1, 'maxLength': 255},
                                                    'value': {'type': 'string', 'minLength': 1, 'maxLength': 1024}}, ['label', 'value'])},
                  'metricsEnabled': {'type': 'boolean'},
                  'metricsSendIntervalSeconds': {'type': 'integer', 'minimum': 60, 'maximum': 240}}, [], minProperties=1)
    schemas = {
        'controller_update': obj({'serial_number': serial, 'fields': fields}, ['serial_number', 'fields']),
        'controller_delete': obj({'serial_number': serial}, ['serial_number']),
        'request_diagnostic': obj({'serial_number': serial}, ['serial_number']),
        'service_add': obj({'serial_number': serial, 'port': port, 'name': label}, ['serial_number', 'port']),
        'service_update': obj({'serial_number': serial, 'port': port, 'fields': obj({'name': label}, ['name'])}, ['serial_number', 'port', 'fields']),
        'service_delete': obj({'serial_number': serial, 'port': port}, ['serial_number', 'port']),
        'group_create': obj({'organization_id': identifier, 'name': name, 'parent': parent}, ['organization_id', 'name']),
        'group_update': obj({'id': identifier, 'fields': obj({'name': name, 'parent': parent}, [], minProperties=1)}, ['id', 'fields']),
        'group_delete': obj({'id': identifier}, ['id']),
        'group_attach': obj({'id': identifier, 'controllers': controllers}, ['id', 'controllers']),
        'group_detach': obj({'controllers': controllers}, ['controllers']),
        'controller_exec': obj({'serial_number': serial,
                                'command': {'type': 'array', 'minItems': 1, 'maxItems': 64,
                                            'items': {'type': 'string', 'maxLength': 16000},
                                            'description': 'Exact argv, first argument nonempty; no NUL; JSON representation <=20000 characters.'},
                                'timeout': {'type': 'integer', 'minimum': 1, 'maximum': 30, 'default': 30}}, ['serial_number', 'command']),
    }
    descriptions = {
        'controller_update': 'Описание, координаты, метаданные и настройки системных метрик контроллера',
        'controller_delete': 'Удаление контроллера из облака',
        'request_diagnostic': 'Запрос сбора диагностики; готовность архива проверяется отдельно',
        'service_add': 'Добавление пользовательского сервиса по локальному порту',
        'service_update': 'Изменение подписи существующего сервиса; порт не меняется',
        'service_delete': 'Удаление сервиса контроллера',
        'group_create': 'Создание группы в организации, необязательная родительская группа',
        'group_update': 'Название группы и перенос к родительской группе; parent=null переносит на верхний уровень',
        'group_delete': 'Удаление группы; preview показывает существующую иерархию',
        'group_attach': 'Назначение до 20 контроллеров группе той же организации',
        'group_detach': 'Снятие назначения группы у выбранных контроллеров, до 20 за вызов',
        'controller_exec': 'Одна подтверждённая команда argv на контроллере через облачный SSH-туннель',
    }
    result = {}
    for operation, schema in schemas.items():
        result[operation] = {
            'effect': 'controller_command' if operation == 'controller_exec' else 'write',
            'description': descriptions[operation],
            'params': {key: ('required' if key in schema['required'] else 'optional')
                       for key in schema['properties']},
            'schema': schema, 'execution': 'integration_write',
            'confirmation_required': True, 'adapter_status': 'implemented',
            'account_access': 'not_live_tested',
            'live_check': {'status': 'not_tested', 'reason': 'Implemented and locally tested; no live mutation attempted.'},
        }
    result['controller_exec'].update(
        adapter_kind='composite',
        implementation='POST cloud tcp-tunnels/{identifier}/ with identifier=ssh, then exact argv over SSH. Not a direct REST shell endpoint. Tunnel credentials and URL stay internal.',
        credentials='Existing internal root/factory authentication or optional shared Vaultwarden SSH item; never supplied in model parameters.')
    return result


def resolve(document: dict, value, seen: tuple[str, ...] = ()):
    """Inline local references; retain recursive references without infinite loops."""
    if isinstance(value, list):
        return [resolve(document, item, seen) for item in value]
    if not isinstance(value, dict):
        return value
    ref = value.get("$ref")
    if ref:
        if not ref.startswith("#/"):
            raise ValueError("Only local OpenAPI references are supported")
        if ref in seen:
            return {"$ref": ref}
        target = document
        for key in ref[2:].split("/"):
            target = target[key.replace("~1", "/").replace("~0", "~")]
        return resolve(document, target, seen + (ref,))
    return {key: resolve(document, item, seen) for key, item in value.items()}


def effect(method: str, path: str) -> str:
    if path in ("/api/v1/auth/token/", "/api/v1/auth/token/refresh/"):
        return "authentication"
    if "/tcp-tunnels/" in path or path == "/api/v1/grafana-session-start/":
        return "remote_access"
    if path.endswith("/request-diagnostic/"):
        return "controller_action"
    # Treat the unsubscribe redirect conservatively: GET alone is not proof of
    # a harmless endpoint. Generic GET dispatch is intentionally unavailable.
    if path == "/api/v1/email-unsubscribe/":
        return "business_write"
    if method == "get" or path.endswith("/system-metrics/"):
        return "read"
    return "business_write"


def build(schema_file: Path, retrieved_at: str, previous: dict | None = None) -> dict:
    raw = schema_file.read_bytes()
    document = yaml.safe_load(raw)
    items = []
    writes = write_operations()
    prior = {row['id']: row for row in (previous or {}).get('capabilities', [])}
    for path, entries in document["paths"].items():
        for method, operation in entries.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            ident = f"{method.upper()} {path}"
            adapter = ADAPTERS.get(ident) or WRITE_ADAPTERS.get(ident) or COMPOSITE_ADAPTERS.get(ident)
            responses = operation.get("responses", {})
            items.append({
                "id": ident,
                "method": method.upper(),
                "path": path,
                "summary": operation.get("summary", operation.get("operationId", ident)),
                "description": operation.get("description", ""),
                "category": operation.get("tags", []),
                "effect": effect(method, path),
                "parameters": resolve(document, entries.get("parameters", []) + operation.get("parameters", [])),
                "request_body": resolve(document, operation.get("requestBody", {})),
                "security": operation.get("security", document.get("security", [])),
                "response_codes": list(responses),
                "responses": resolve(document, responses),
                "source": SOURCE,
                "provider_version": document["info"]["version"],
                "adapter": adapter,
                "execution": ('integration_read' if ident in ADAPTERS else 'integration_write') if adapter else "not_implemented",
                "access": "unverified",
                "live_check": {
                    "status": "not_tested",
                    "reason": "No live adapter probe yet" if adapter else "No executable adapter; schema inventory only",
                },
            })
            row = items[-1]
            if ident in WRITE_ADAPTERS or ident in COMPOSITE_ADAPTERS:
                row['params_schema'] = writes[adapter]['schema']
                row['adapter_status'] = 'implemented'
                row['confirmation_required'] = True
                row['live_check'] = writes[adapter]['live_check']
                if ident in COMPOSITE_ADAPTERS:
                    row['adapter_kind'] = 'composite'
                    row['implementation'] = writes[adapter]['implementation']
            old = prior.get(ident)
            if old and adapter and old.get('adapter') == adapter:
                for key in ('access', 'live_check'):
                    if key in old:
                        row[key] = old[key]
    missing = (set(ADAPTERS) | set(WRITE_ADAPTERS) | set(COMPOSITE_ADAPTERS)) - {item["id"] for item in items}
    if missing:
        raise ValueError(f"The schema is missing implemented operations: {sorted(missing)}")
    return {
        "schema_version": 1,
        "service": "wirenboard",
        "retrieved_at": retrieved_at,
        "scope": "All 72 documented methods in the official cloud OpenAPI snapshot. Ten explicit read adapters plus eleven confirmed cloud-management adapters are implemented. controller_exec is a separate composite of the documented SSH-tunnel method and one confirmed SSH argv command, not a REST shell endpoint. Cloud writes are locally tested; account mutation permissions and live mutation outcomes remain unverified. User profiles, account/security changes, activation and transfers remain unavailable. Documentation does not establish permissions.",
        "sources": [{"url": SOURCE, "sha256": hashlib.sha256(raw).hexdigest()}],
        "authentication_note": "The official schema describes an Authorization: Token prefix. The existing account client uses Authorization: Bearer with JWT access tokens and persists rotated refresh tokens.",
        "total": len(items),
        "capabilities": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema", type=Path)
    parser.add_argument("--output", type=Path, default=Path("registry/capabilities/wirenboard.json"))
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    args = parser.parse_args()
    date.fromisoformat(args.retrieved_at)
    previous = json.loads(args.output.read_text()) if args.output.exists() else None
    inventory = build(args.schema, args.retrieved_at, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wirenboard: {inventory['total']} documented operations, {len(ADAPTERS)} read, {len(WRITE_ADAPTERS)} cloud write, {len(COMPOSITE_ADAPTERS)} composite adapters")


if __name__ == "__main__":
    main()
