"""Mirror the independent protocol client into the HACS custom component."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/ampio-python/src/ampio_python/client.py"
TARGET = ROOT / "custom_components/ampio/protocol.py"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if the HACS mirror differs")
    args = parser.parse_args()
    source = SOURCE.read_bytes()
    if args.check:
        if TARGET.read_bytes() != source:
            raise SystemExit("Protocol mirror is out of sync; run scripts/sync_protocol.py")
        return
    TARGET.write_bytes(source)


if __name__ == "__main__":
    main()
