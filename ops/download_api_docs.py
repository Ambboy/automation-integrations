# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Download the official API documentation without business API calls or credentials.

Uses the source URLs recorded in registry/capabilities, plus current discovery and
sandbox pages. Every successful manifest entry is a fresh HTTPS response; older
research snapshots are never copied. No redirects, disabled TLS or curlrc files.
Saby can use the existing pinned SG -> Example Egress SSH route (read-only curl only).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shlex
import ssl
import subprocess
import re
from urllib.parse import urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
YANDEX = 'https://taxi__business-api.docs-viewer.yandex.ru'
CA_SHA256 = 'd26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31'
EXTRA = [
    ('yandex_go', YANDEX + '/ru/concepts/request-index-api20.md', 'yandex/request-index-api20.md'),
    ('yandex_go', YANDEX + '/ru/concepts/quickstart.md', 'yandex/quickstart.md'),
    ('yandex_go', YANDEX + '/ru/concepts/api20/roles.md', 'yandex/roles.md'),
    ('yandex_go', YANDEX + '/ru/llms.txt', 'yandex/llms.txt'),
    ('saby', 'https://saby.ru/help/integration/api/all_methods', 'saby/all_methods.html'),
    ('saby', 'https://saby.ru/help/integration/api/auth/service', 'saby/auth_service.html'),
    ('saby', 'https://saby.ru/help/integration/api/doc_guide', 'saby/doc_guide.html'),
    ('saby', 'https://saby.ru/help/integration/api/techreq_edo', 'saby/techreq_edo.html'),
    ('saby', 'https://saby.ru/help/start/test_saby', 'saby/test_account.html'),
    ('saby', 'https://saby.ru/help/integration/api/all_methods/update_division', 'saby/update_division.html'),
    ('saby', 'https://link.saby.ru/article/885fcb48-f55d-4ab6-a8c4-d7f62a9a73c5/39fd6a6f-dfc1-4559-91aa-49e8563dcd98',
     'saby/companyinfo_linked_article.html'),
    ('tochka', 'https://developers.tochka.com/docs/tochka-api/pesochnica', 'tochka/sandbox.html'),
]
EXTRA += [('saby', 'https://saby.ru/help/integration/api/' + path,
           'saby/' + path.replace('/', '_') + '.html') for path in (
               'authentication', 'counterparty', 'documents', 'partner', 'powers',
               'recruit/directory/employee', 'service_func', 'signature', 'user_reg')]


def now():
    return datetime.now(timezone.utc).isoformat()


def sources():
    result = []
    for service in ('yandex_go', 'etm', 'saby', 'tochka'):
        doc = json.loads((ROOT / 'registry/capabilities' / (service + '.json')).read_text())
        saby_names = {c['source'].rstrip('/'): c['id'] for c in doc['capabilities']} if service == 'saby' else {}
        for source in doc['sources']:
            url = source['url']
            name = urlsplit(url).path.rsplit('/', 1)[-1]
            if service == 'yandex_go':
                target = 'yandex/' + name
            elif service == 'saby':
                target = 'saby-methods/' + saby_names[url.rstrip('/')] + '.html'
            elif service == 'etm':
                target = 'etm.yaml' if name == 'cli.yaml' else name
            else:
                target = 'tochka-openapi.json'
            result.append({'service': service, 'url': url, 'file': target,
                           'previous_sha256': source.get('sha256'), 'kind': 'contract'})
    for service, url, target in EXTRA:
        result.append({'service': service, 'url': url, 'file': target, 'kind': 'index_or_guidance'})
    # A registry may keep both canonical and trailing-slash evidence URLs. One
    # download per document is sufficient; avoid duplicate target writers too.
    unique = {}
    for row in result:
        unique.setdefault(row['url'].rstrip('/'), row)
    return list(unique.values())


def validate_source(row):
    parts = urlsplit(row['url'])
    allowed = {
        'yandex_go': [('taxi__business-api.docs-viewer.yandex.ru', '/ru/')],
        'etm': [('ipro.etm.ru', '/ns2000/yaml/')],
        'saby': [('saby.ru', '/help/integration/api/'), ('saby.ru', '/help/partner/api/'),
                 ('saby.ru', '/help/start/test_saby'),
                 ('link.saby.ru', '/article/885fcb48-f55d-4ab6-a8c4-d7f62a9a73c5/')],
        'tochka': [('enter.tochka.com', '/doc/openapi/'), ('developers.tochka.com', '/docs/tochka-api/')],
    }
    if (parts.scheme != 'https' or parts.username or parts.password or parts.query or parts.fragment
            or not any(parts.netloc == host and parts.path.startswith(prefix)
                       for host, prefix in allowed[row['service']])):
        raise ValueError('Source is outside the official documentation allowlist')
    path = Path(row['file'])
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Invalid snapshot path')


def linked_saby_sources(output, existing):
    """One discovery level from the downloaded command/category pages, no broad crawl."""
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links, self.href, self.text = [], None, []

        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.href, self.text = dict(attrs).get('href'), []

        def handle_endtag(self, tag):
            if tag == 'a' and self.href:
                self.links.append((self.href, ' '.join(self.text).strip()))
                self.href = None

        def handle_data(self, data):
            if self.href:
                self.text.append(data)

    result = []
    seen = {r['url'].rstrip('/') for r in existing}
    observed = {}
    for path in sorted((output / 'saby').glob('*.html')):
        parser = Links()
        parser.feed(path.read_text())
        for href, ident in parser.links:
            if not re.fullmatch(r'(?:СБИС\.|saby[A-Z]|ekdapi\.)[\w.]+', ident):
                continue
            url = urljoin('https://saby.ru', href)
            observed[ident] = {'method_id': ident, 'source': url,
                               'linked_from': str(path.relative_to(output))}
            if url.rstrip('/') in seen:
                continue
            row = {'service': 'saby', 'url': url, 'file': 'saby-extra-methods/' + ident + '.html',
                   'kind': 'supplementary_contract', 'method_id': ident,
                   'discovered_from': str(path.relative_to(output))}
            validate_source(row)
            result.append(row)
            seen.add(url.rstrip('/'))
    mapping = {r['url'].rstrip('/'): r for r in existing}
    for row in observed.values():
        found = mapping.get(row['source'].rstrip('/'))
        if found:
            row.update(file=found['file'], download_source=found['url'], download_status=found['status'])
    (output / 'saby-linked-methods.json').write_text(json.dumps(
        {'generated_at': now(), 'provenance': 'Extracted named links from freshly downloaded category pages',
         'total': len(observed), 'methods': [observed[k] for k in sorted(observed)]},
        ensure_ascii=False, indent=2) + '\n')
    return result


def download(row, args):
    validate_source(row)
    row = dict(row, attempted_at=now())
    url = row['url']
    cmd = ['curl', '-q', '--proto', '=https', '--silent', '--show-error', '--fail',
           '--connect-timeout', '12', '--max-time', '40', '--max-filesize', '8388608',
           '--write-out', '\n__DOC_HTTP_STATUS__%{http_code}', '--noproxy', '*']
    transport = 'direct_https'
    if row['service'] == 'yandex_go':
        url = url.replace('taxi__business-api.', 'taxi-business-api.', 1)
        cmd += ['--header', 'Host: taxi__business-api.docs-viewer.yandex.ru']
        transport = 'tls_valid_frontdoor_with_canonical_host'
    elif row['service'] == 'etm':
        cmd += ['--noproxy', '', '--proxy', args.etm_proxy]
        transport = 'existing_loopback_socks'
    elif row['service'] == 'tochka':
        pem = args.tochka_ca.read_text()
        if hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() != CA_SHA256:
            raise ValueError('Untrusted Tochka root certificate')
        cmd += ['--cacert', str(args.tochka_ca)]
        transport = 'https_pinned_official_root'
    cmd.append(url)
    if row['service'] == 'saby' and args.saby_transport == 'example_egress':
        inner = shlex.join(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                            '-F', '/home/operator/.ssh/cloudcli-vpn-admin.conf',
                            'example-egress-admin', shlex.join(cmd)])
        cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', 'example-hermes', inner]
        transport = 'existing_pinned_ssh_sg_example_egress_https'
    row['transport'] = transport
    try:
        response = subprocess.run(cmd, capture_output=True, timeout=65, check=False)
        body, separator, status = response.stdout.rpartition(b'\n__DOC_HTTP_STATUS__')
        row['http_status'] = int(status) if separator and status.isdigit() else None
        if response.returncode or row['http_status'] != 200:
            row.update(status='failed', error='https_download_failed', process_exit=response.returncode)
            return row
        if not body or len(body) > 8 * 1024 * 1024:
            raise ValueError('Empty or oversized document')
        if row['file'].endswith('.json'):
            parsed = json.loads(body)
            if not isinstance(parsed.get('paths'), dict):
                raise ValueError('Not an OpenAPI document')
        elif row['file'].endswith('.html') and b'<html' not in body[:2000].lower():
            raise ValueError('Not an HTML document')
        elif row['file'].endswith('.md') and b'# ' not in body:
            raise ValueError('Not a Markdown document')
        digest = hashlib.sha256(body).hexdigest()
        target = args.output / row['file']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        row.update(status='downloaded', downloaded_at=now(), sha256=digest, bytes=len(body))
        if row.get('previous_sha256'):
            row['changed_since_registry'] = digest != row['previous_sha256']
    except subprocess.TimeoutExpired:
        row.update(status='failed', error='download_timeout')
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        row.update(status='failed', error=type(exc).__name__)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 6), default=4)
    parser.add_argument('--etm-proxy', default='socks5h://127.0.0.1:10929')
    parser.add_argument('--saby-transport', choices=('example_egress', 'direct'), default='example_egress')
    parser.add_argument('--tochka-ca', type=Path, default=Path.home() /
                        '.local/share/automation-integrations/greif/api-catalog/tochka-root.pem')
    parser.add_argument('--retry-failed', action='store_true', help='Retry failures in this new snapshot only')
    args = parser.parse_args()
    args.output = args.output.resolve()
    manifest_path = args.output / 'manifest.json'
    entries = sources()
    rows = []
    started = now()
    if manifest_path.exists():
        if not args.retry_failed:
            parser.error('Snapshot exists; choose a new output or explicitly use --retry-failed')
        previous = json.loads(manifest_path.read_text())
        started = previous['started_at']
        for row in previous['documents']:
            if row['status'] == 'downloaded':
                existing = args.output / row['file']
                if not existing.exists() or hashlib.sha256(existing.read_bytes()).hexdigest() != row['sha256']:
                    parser.error('Existing downloaded document does not match the manifest')
                rows.append(row)
        completed = {r['url'].rstrip('/') for r in rows}
        entries = [r for r in entries if r['url'].rstrip('/') not in completed]
    args.output.mkdir(parents=True, exist_ok=True)

    def save():
        content = {'schema_version': 1, 'started_at': started, 'updated_at': now(),
                   'source': 'fresh HTTPS downloads; no old snapshot fallback',
                   'business_api_called': False,
                   'documents': sorted(rows, key=lambda r: (r['service'], r['file']))}
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(manifest_path)

    def fetch_batch(batch):
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(download, row, args): row for row in batch}
            for future in as_completed(futures):
                original = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    row = dict(original, status='failed', attempted_at=now(), error=type(exc).__name__)
                rows.append(row)
                save()
                print(json.dumps({k: row[k] for k in ('service', 'file', 'status')}, ensure_ascii=False), flush=True)

    fetch_batch(entries)
    fetch_batch(linked_saby_sources(args.output, rows))
    linked_saby_sources(args.output, rows)  # Refresh the derived source/file/status index.
    save()
    failed = sum(r['status'] != 'downloaded' for r in rows)
    print(json.dumps({'total': len(rows), 'downloaded': len(rows) - failed, 'failed': failed}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
