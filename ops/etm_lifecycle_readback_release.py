"""Install only the ETM lifecycle readback correction, with guarded rollback.

The full lifecycle release already includes the current source module. This
incremental helper updates installations of the initial release while preserving
that release's backup and manifest. Roll this patch back before rolling back the
full release. Runner subprocesses pick it up without a gateway restart.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from ops import wirenboard_release as guarded


@dataclass(frozen=True)
class Layout(guarded.Layout):
    backup: Path = guarded.ROOT / 'update-20261007-etm-lifecycle-readback'

    def targets(self):
        return [(self.source / 'automation_integrations/etm_lifecycle.py',
                 self.root / 'release/etm_lifecycle.py')]


def prepare(layout: Layout = Layout()) -> dict:
    if layout.backup.exists() or layout.backup.is_symlink():
        raise guarded.ReleaseError('Readback patch staging already exists; inspect before retrying')
    if guarded.checked_bytes(layout.targets()[0][1]) is None:
        raise guarded.ReleaseError('Install the full ETM lifecycle release before this incremental patch')
    return guarded.prepare(layout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    args = parser.parse_args()
    try:
        result = {'prepare': prepare, 'apply': guarded.apply,
                  'rollback': guarded.rollback}[args.action](Layout())
    except guarded.ReleaseError as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('ETM readback patch failed; inspect hashes and gateway state without printing credentials.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
