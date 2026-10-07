"""Stage/apply/rollback controller management over the current full-API release.

The operator verifies the installed baseline before prepare. This helper reuses
the read release's staged-content, target-hash, config and idle-gateway guards.
It never restarts Hermes or changes credentials, sessions, or control drafts.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

try:
    from . import wirenboard_release as guarded
except ImportError:
    import wirenboard_release as guarded


SOURCE = Path(__file__).resolve().parents[1]
BACKUP = guarded.ROOT / 'update-20261004-wirenboard-control'
ReleaseError = guarded.ReleaseError


@dataclass(frozen=True)
class Layout(guarded.Layout):
    source: Path = SOURCE
    backup: Path = BACKUP

    def targets(self) -> list[tuple[Path, Path]]:
        release = self.root / 'release'
        plugin = self.home / 'plugins/automation-api-catalog'
        # Dependencies first, write dispatcher next, discovery and plugin last.
        modules = ('wirenboard_control_contract.py', 'wirenboard_shell.py',
                   'wirenboard_control.py', 'wirenboard_http.py',
                   'wirenboard.py', 'api_write.py')
        return [(self.source / 'automation_integrations' / name, release / name)
                for name in modules] + [
            (self.source / 'registry/capabilities/wirenboard.json', release / 'capabilities/wirenboard.json'),
            (self.source / 'registry/catalog.json', release / 'catalog.json'),
            (self.source / 'bridges/hermes_catalog/__init__.py', plugin / '__init__.py'),
            (self.source / 'bridges/hermes_catalog/plugin.yaml', plugin / 'plugin.yaml'),
        ]


def prepare(layout: Layout = Layout()) -> dict:
    return guarded.prepare(layout)


def apply(layout: Layout = Layout()) -> dict:
    return guarded.apply(layout)


def rollback(layout: Layout = Layout()) -> dict:
    return guarded.rollback(layout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    args = parser.parse_args()
    try:
        result = {'prepare': prepare, 'apply': apply, 'rollback': rollback}[args.action]()
    except ReleaseError as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Release guard rejected the action; inspect target/config/staging hashes and gateway idle state.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
