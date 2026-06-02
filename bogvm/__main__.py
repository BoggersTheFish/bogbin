import argparse
import json
from pathlib import Path

from .assembler import assemble_file
from .vm import run_file


def main() -> None:
    parser = argparse.ArgumentParser(prog="bogvm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_asm = sub.add_parser("assemble")
    p_asm.add_argument("src")
    p_asm.add_argument("dst")

    p_run = sub.add_parser("run")
    p_run.add_argument("bogbin")
    p_run.add_argument("--receipt", default=None)

    args = parser.parse_args()

    if args.cmd == "assemble":
        assemble_file(args.src, args.dst)
        print(f"assembled: {args.src} -> {args.dst}")

    elif args.cmd == "run":
        receipt = run_file(args.bogbin)
        text = json.dumps(receipt, indent=2, sort_keys=True)
        if args.receipt:
            Path(args.receipt).write_text(text + "\n")
            print(f"receipt written: {args.receipt}")
        print(text)


if __name__ == "__main__":
    main()
