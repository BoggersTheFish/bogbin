import argparse
import json
from pathlib import Path

from .assembler import Assembler, assemble_file
from .packer import pack_bytes_to_bogasm
from .vm import run_file_with_block_receipt


def main() -> None:
    parser = argparse.ArgumentParser(prog="bogvm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_asm = sub.add_parser("assemble")
    p_asm.add_argument("src")
    p_asm.add_argument("dst")

    p_run = sub.add_parser("run")
    p_run.add_argument("bogbin")
    p_run.add_argument("--receipt", default=None)

    p_pack = sub.add_parser("pack")
    p_pack.add_argument("input")
    p_pack.add_argument("output")
    p_pack.add_argument("--bogasm", required=True)
    p_pack.add_argument("--receipt", required=True)

    args = parser.parse_args()

    if args.cmd == "assemble":
        assemble_file(args.src, args.dst)
        print(f"assembled: {args.src} -> {args.dst}")

    elif args.cmd == "run":
        receipt, exit_code = run_file_with_block_receipt(args.bogbin)
        text = json.dumps(receipt, indent=2, sort_keys=True)

        if args.receipt:
            Path(args.receipt).write_text(text + "\n")
            print(f"receipt written: {args.receipt}")

        print(text)

        if exit_code != 0:
            raise SystemExit(exit_code)

    elif args.cmd == "pack":
        data = Path(args.input).read_bytes()
        bogasm = pack_bytes_to_bogasm(data)

        bogasm_path = Path(args.bogasm)
        bogasm_path.write_text(bogasm)

        bogbin_path = Path(args.output)
        assembler = Assembler()
        bogbin_path.write_bytes(assembler.assemble_text(bogasm))

        receipt, exit_code = run_file_with_block_receipt(bogbin_path)
        receipt_text = json.dumps(receipt, indent=2, sort_keys=True)
        Path(args.receipt).write_text(receipt_text + "\n")

        if (
            exit_code != 0
            or receipt.get("execution_status") != "completed"
            or "payload" not in receipt.get("accepted_data_block_names", [])
        ):
            print(receipt_text)
            raise SystemExit(1)

        print(f"packed: {args.input} -> {args.output}")
        print(f"bogasm written: {args.bogasm}")
        print(f"receipt written: {args.receipt}")


if __name__ == "__main__":
    main()
