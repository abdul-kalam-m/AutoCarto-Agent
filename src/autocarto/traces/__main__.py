"""python -m autocarto.traces validate FILE | diff BEFORE AFTER [--ignore-timing]."""
import argparse
import json
from pathlib import Path
from . import MAX_DOCUMENT_BYTES, differences, parse_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate").add_argument("file", type=Path)
    diff = sub.add_parser("diff")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--ignore-timing", action="store_true")
    args = parser.parse_args()
    def read(path):
        with path.open("rb") as stream:
            return parse_document(stream.read(MAX_DOCUMENT_BYTES + 1))
    try:
        if args.command == "validate":
            document = read(args.file)
            print(f"Valid {document['kind']} v{document['version']}")
            return 0
        changes = differences(read(args.before), read(args.after), ignore_timing=args.ignore_timing)
        print(json.dumps(changes, indent=2, ensure_ascii=False, allow_nan=False))
        return 1 if changes else 0
    except (ValueError, OSError) as error:
        print(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
