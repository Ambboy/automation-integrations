# Public example: replace synthetic identities and deployment paths before explicit execution.
"""Prepare/apply/rollback the longer voice-message release without service changes.

Only the two speech preparation modules and the installed delivery/plugin
manifest are targets. Credentials, configuration and the HTTP provider stay as
installed. The operator manages the gateway service separately.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

try:
    from . import wirenboard_release as guarded
except ImportError:
    import wirenboard_release as guarded


SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path('/home/operator/.local/share/automation-integrations/greif/short-voice')
BACKUP = ROOT / 'update-20261004-voice-length'
ReleaseError = guarded.ReleaseError


@dataclass(frozen=True)
class Layout(guarded.Layout):
    source: Path = SOURCE
    root: Path = ROOT
    backup: Path = BACKUP

    @property
    def speech_database(self) -> Path:
        return self.root.parent / 'phase2/sources/sources.sqlite3'

    def targets(self) -> list[tuple[Path, Path]]:
        release = self.root / 'release/automation_integrations'
        plugin = self.home / 'plugins/automation-speech-source'
        return [
            (self.source / 'automation_integrations' / name, release / name)
            for name in ('hermes_speech.py', 'speech_segments.py')
        ] + [
            (self.source / 'bridges/hermes_speech' / name, plugin / name)
            for name in ('delivery.py', 'plugin.yaml')
        ]


def ensure_speech_idle(layout: Layout) -> None:
    """Background voice preparation/delivery can outlive Hermes' model turn."""
    path = layout.speech_database
    if path.is_symlink():
        raise ReleaseError('Refusing a symlink speech database')
    if not path.exists():
        return
    if not path.is_file():
        raise ReleaseError('Expected a regular speech database')
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='delivery_jobs'").fetchone():
                return
            if db.execute("SELECT 1 FROM delivery_jobs WHERE state IN "
                          "('queued','synthesizing','ready','sending') LIMIT 1").fetchone():
                raise ReleaseError('Speech jobs are still active; wait for preparation and delivery to finish')
    except sqlite3.Error:
        raise ReleaseError('Cannot verify that background speech jobs are idle') from None


def prepare(layout: Layout = Layout()) -> dict:
    return guarded.prepare(layout)


def apply(layout: Layout = Layout()) -> dict:
    ensure_speech_idle(layout)
    return guarded.apply(layout)


def rollback(layout: Layout = Layout()) -> dict:
    ensure_speech_idle(layout)
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
        raise SystemExit('Release guard rejected the action; inspect target/config/staging hashes and idle states.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
