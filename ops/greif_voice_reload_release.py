"""Install/roll back the speech callback reload fix; no service or config changes."""
from dataclasses import dataclass
import argparse
import json
from pathlib import Path

from . import greif_voice_length_release as previous


ReleaseError = previous.ReleaseError


@dataclass(frozen=True)
class Layout(previous.Layout):
    backup: Path = previous.ROOT / 'update-20261004-voice-reload'

    def targets(self):
        return [(self.source / 'bridges/hermes_speech' / name,
                 self.home / 'plugins/automation-speech-source' / name)
                for name in ('delivery.py', 'plugin.yaml')]


def prepare(layout=Layout()):
    return previous.prepare(layout)


def apply(layout=Layout()):
    return previous.apply(layout)


def rollback(layout=Layout()):
    return previous.rollback(layout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'rollback'))
    args = parser.parse_args()
    try:
        result = {'prepare': prepare, 'apply': apply, 'rollback': rollback}[args.action]()
    except ReleaseError as exc:
        raise SystemExit(str(exc)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Release guard rejected the action; inspect hashes and idle state.') from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
