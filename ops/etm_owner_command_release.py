"""Install the requested ETM purchasing policy and basket fix, with guarded rollback."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from ops import wirenboard_release as guarded


OLD_APPROVAL = ('- Show exact product, quantity, total ceiling, destination, contract and payment method. '
                'Execute only after the owner sends the returned confirmation command in a new private '
                'message; the original ordering request is not this second consent.')
NEW_APPROVAL = ('- For an owner instruction to order or arrange shipment, prepare the exact product, quantity, '
                'total ceiling, destination, contract and payment method. When the tool returns '
                '`confirmation_required=false`, call execute immediately: the owner has authorized ETM '
                'procurement by ordinary command, with no extra message or UUID. Read-only questions remain '
                'read-only. If `confirmation_required=true`, follow the returned confirmation mechanism. '
                'Ask only about genuinely missing conditions; reuse the established task context.')
OLD_CUT = ('- Distinguish regional logistics stock from destination-shop stock and planned transfer dates '
           'from ready-to-collect status. If a continuous length is required, set `continuous_cut=true`; '
           'stock totals alone do not guarantee a cut.')
NEW_CUT = ('- Distinguish regional logistics stock from destination-shop stock and planned transfer dates '
           'from ready-to-collect status. Set `continuous_cut=true` only when the owner requests a continuous '
           'length; a quantity in metres alone does not request it. The workflow checks one physical allocation '
           'and records the cutting instruction, but that does not prove a physical cut has already been made. '
           'Use the fresh complete basket total; preserve an explicit owner budget and never increase quantities.')


@dataclass(frozen=True)
class Layout(guarded.Layout):
    backup: Path = guarded.ROOT / 'update-20261004-etm-owner-command'

    @property
    def skill(self):
        return self.home / 'skills/productivity/supplier-order-audits/references/etm.md'

    def targets(self):
        release = self.root / 'release'
        plugin = self.home / 'plugins/automation-api-catalog'
        return [(self.source / 'automation_integrations' / name, release / name)
                for name in ('etm_authorization.py', 'etm_order.py', 'etm_workflow.py', 'confirmed_write.py')] + [
            (self.source / 'automation_integrations/catalog.py', plugin / 'catalog.py'),
            (self.source / 'registry/catalog.json', release / 'catalog.json'),
            (self.backup / 'candidate-private.json', self.root / 'private.json'),
            (self.backup / 'candidate-etm-skill.md', self.skill),
            (self.source / 'bridges/hermes_catalog/__init__.py', plugin / '__init__.py'),
            (self.source / 'bridges/hermes_catalog/plugin.yaml', plugin / 'plugin.yaml'),
        ]


def prepare(layout=Layout()):
    if layout.backup.exists():
        raise guarded.ReleaseError('Release staging already exists; inspect before retrying')
    private = json.loads(guarded.checked_bytes(layout.root / 'private.json'))
    private['etm_order_authorization'] = 'owner_command'
    skill = guarded.checked_bytes(layout.skill).decode()
    if skill.count(OLD_APPROVAL) != 1 or skill.count(OLD_CUT) != 1:
        raise guarded.ReleaseError('ETM skill changed; review the current instructions first')
    skill = skill.replace(OLD_APPROVAL, NEW_APPROVAL).replace(OLD_CUT, NEW_CUT)
    layout.backup.mkdir(mode=0o700, parents=True)
    guarded.atomic(layout.backup / 'candidate-private.json', guarded.json_bytes(private))
    guarded.atomic(layout.backup / 'candidate-etm-skill.md', skill.encode())
    return guarded.prepare(layout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    args = parser.parse_args()
    layout = Layout()
    actions = {'prepare': prepare, 'apply': guarded.apply, 'rollback': guarded.rollback}
    try:
        result = actions[args.action](layout)
    except (guarded.ReleaseError, OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, guarded.ReleaseError):
            raise SystemExit(str(exc)) from None
        raise SystemExit('ETM release validation failed; inspect state without printing private configuration.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
