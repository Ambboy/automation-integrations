"""Run the pinned numeric guard in a killable process, not the service's worker thread."""
import sys

from .vendor.ru_numbers import normalize


def main():
    text = sys.stdin.read(8001)
    if len(text) > 8000:
        return 1
    try:
        result = normalize(text)
    except Exception:
        return 1
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
