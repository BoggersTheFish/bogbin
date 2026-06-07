import argparse
import hashlib
import json
from pathlib import Path

from .archive import build_directory_archive, restore_directory_archive
from .assembler import Assembler, assemble_file
from .bogfs import BogFS
from .container import (
    build_bog_container_v1,
    compile_bog_container_to_bogasm,
    read_container,
    reconstruct_bog_container_bytes,
    write_bog_container,
    write_bogpk_container,
)
from .packer import build_pack_receipt_metadata, pack_bytes_to_bogasm, pack_chunked_bytes_to_bogasm
from .store import init_store, install_bundle, package_directory, verify_installed_package
from .signing import generate_keypair
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
    p_pack.add_argument("--chunk-size", type=int, default=64)
    p_pack.add_argument("--auto-chunk", action="store_true")
    p_pack.add_argument("--transform-tournament", action="store_true")
    p_pack.add_argument("--single-block", action="store_true")
    p_pack.add_argument("--bogasm", default=None)
    p_pack.add_argument("--receipt", required=True)

    p_compile = sub.add_parser("compile")
    p_compile.add_argument("container")
    p_compile.add_argument("output")
    p_compile.add_argument("--bogasm", required=True)

    p_unpack = sub.add_parser("unpack")
    p_unpack.add_argument("container")
    p_unpack.add_argument("output")
    p_unpack.add_argument("--receipt", required=True)

    p_roundtrip = sub.add_parser("roundtrip")
    p_roundtrip.add_argument("input")
    p_roundtrip.add_argument("recovered")
    p_roundtrip.add_argument("--container", required=True)
    p_roundtrip.add_argument("--bogbin", required=True)
    p_roundtrip.add_argument("--bogasm", required=True)
    p_roundtrip.add_argument("--receipt", required=True)
    p_roundtrip.add_argument("--chunk-size", type=int, default=64)
    p_roundtrip.add_argument("--auto-chunk", action="store_true")
    p_roundtrip.add_argument("--transform-tournament", action="store_true")

    p_archive = sub.add_parser("archive")
    p_archive.add_argument("source_dir")
    p_archive.add_argument("archive_dir")
    p_archive.add_argument("--chunk-size", type=int, default=64)
    p_archive.add_argument("--fixed-chunk", action="store_true")
    p_archive.add_argument("--no-transform-tournament", action="store_true")
    p_archive.add_argument("--receipt", required=True)

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("archive_dir")
    p_restore.add_argument("output_dir")
    p_restore.add_argument("--receipt", required=True)

    p_fs = sub.add_parser("fs")
    fs_sub = p_fs.add_subparsers(dest="fs_cmd", required=True)
    p_fs_ls = fs_sub.add_parser("ls")
    p_fs_ls.add_argument("archive_dir")
    p_fs_ls.add_argument("path", nargs="?", default="")
    p_fs_cat = fs_sub.add_parser("cat")
    p_fs_cat.add_argument("archive_dir")
    p_fs_cat.add_argument("path")
    p_fs_stat = fs_sub.add_parser("stat")
    p_fs_stat.add_argument("archive_dir")
    p_fs_stat.add_argument("path")

    p_store = sub.add_parser("store")
    store_sub = p_store.add_subparsers(dest="store_cmd", required=True)
    p_store_init = store_sub.add_parser("init")
    p_store_init.add_argument("store_dir")
    p_store_keygen = store_sub.add_parser("keygen")
    p_store_keygen.add_argument("private_key")
    p_store_keygen.add_argument("public_key")
    p_store_package = store_sub.add_parser("package")
    p_store_package.add_argument("source_dir")
    p_store_package.add_argument("bundle_dir")
    p_store_package.add_argument("--name", required=True)
    p_store_package.add_argument("--version", required=True)
    p_store_package.add_argument("--receipt", required=True)
    p_store_package.add_argument("--dependency", action="append", default=[])
    p_store_package.add_argument("--signing-key", default=None)
    p_store_install = store_sub.add_parser("install")
    p_store_install.add_argument("store_dir")
    p_store_install.add_argument("bundle_dir")
    p_store_install.add_argument("--receipt", required=True)
    p_store_install.add_argument("--trusted-key", action="append", default=[])
    p_store_install.add_argument("--require-signature", action="store_true")
    p_store_verify = store_sub.add_parser("verify")
    p_store_verify.add_argument("store_dir")
    p_store_verify.add_argument("package")
    p_store_verify.add_argument("--receipt", required=True)
    p_store_verify.add_argument("--trusted-key", action="append", default=[])
    p_store_verify.add_argument("--require-signature", action="store_true")

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
        output_path = Path(args.output)

        if output_path.suffix in {".bog", ".bogpk"}:
            if args.single_block:
                raise SystemExit("--single-block is only supported for direct .bogbin pack output")
            container = build_bog_container_v1(
                data,
                chunk_size=args.chunk_size,
                auto_chunk=args.auto_chunk,
                transform_tournament=args.transform_tournament,
            )
            if output_path.suffix == ".bogpk":
                write_bogpk_container(container, str(output_path))
            else:
                write_bog_container(container, str(output_path))
            receipt = {
                "execution_status": "completed",
                "format": container["format"],
                "vm_format": container["vm_format"],
                "pack_mode": container["pack_mode"],
                "chunk_size": container["chunk_size"],
                "chunk_count": container["chunk_count"],
                "total_residual_count": container["total_residual_count"],
                "whole_sha256": container["whole_sha256"],
                "chunk_tournament_enabled": container.get("chunk_tournament_enabled", False),
                "candidate_chunk_sizes": container.get("candidate_chunk_sizes", [container["chunk_size"]]),
                "selected_chunk_size": container.get("selected_chunk_size", container["chunk_size"]),
                "selected_total_residual_count": container.get("selected_total_residual_count", container["total_residual_count"]),
                "selected_residual_density": container.get("selected_residual_density", 0.0),
                "chunk_tournament_results": container.get("chunk_tournament_results", []),
                "transform_tournament_enabled": container.get("transform_tournament_enabled", False),
                "candidate_transforms": container.get("candidate_transforms", ["identity"]),
                "selected_transform_counts": container.get("selected_transform_counts", {"identity": container["chunk_count"]}),
            }
            Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(f"container written: {args.output}")
            print(f"receipt written: {args.receipt}")
            return

        if output_path.suffix != ".bogbin":
            raise SystemExit("pack output must end in .bog, .bogpk, or .bogbin")
        if args.auto_chunk:
            raise SystemExit("--auto-chunk is only supported for .bog container output")
        if args.transform_tournament:
            raise SystemExit("--transform-tournament is only supported for .bog container output")
        if args.bogasm is None:
            raise SystemExit("--bogasm is required for direct .bogbin pack output")

        chunked = not args.single_block and len(data) > args.chunk_size
        if chunked:
            bogasm = pack_chunked_bytes_to_bogasm(data, chunk_size=args.chunk_size)
        else:
            bogasm = pack_bytes_to_bogasm(data)

        bogasm_path = Path(args.bogasm)
        bogasm_path.write_text(bogasm)

        bogbin_path = output_path
        assembler = Assembler()
        bogbin_path.write_bytes(assembler.assemble_text(bogasm))

        receipt, exit_code = run_file_with_block_receipt(bogbin_path)
        receipt.update(build_pack_receipt_metadata(data, args.chunk_size, single_block=not chunked))
        receipt_text = json.dumps(receipt, indent=2, sort_keys=True)
        Path(args.receipt).write_text(receipt_text + "\n")

        accepted_names = receipt.get("accepted_data_block_names", [])
        expected_names = (
            [f"payload_chunk_{index:04d}" for index in range(receipt["chunk_count"])]
            if chunked else
            ["payload"]
        )
        if (
            exit_code != 0
            or receipt.get("execution_status") != "completed"
            or accepted_names != expected_names
        ):
            print(receipt_text)
            raise SystemExit(1)

        print(f"packed: {args.input} -> {args.output}")
        print(f"bogasm written: {args.bogasm}")
        print(f"receipt written: {args.receipt}")

    elif args.cmd == "compile":
        container = read_container(args.container)
        bogasm = compile_bog_container_to_bogasm(container)
        Path(args.bogasm).write_text(bogasm)
        Path(args.output).write_bytes(Assembler().assemble_text(bogasm))
        print(f"compiled: {args.container} -> {args.output}")
        print(f"bogasm written: {args.bogasm}")

    elif args.cmd == "unpack":
        container = read_container(args.container)
        reconstructed = reconstruct_bog_container_bytes(container)
        Path(args.output).write_bytes(reconstructed)
        reconstructed_sha256 = hashlib.sha256(reconstructed).hexdigest()
        receipt = {
            "format": container["format"],
            "source_container": args.container,
            "output_path": args.output,
            "chunk_count": container["chunk_count"],
            "chunk_size": container["chunk_size"],
            "total_residual_count": container["total_residual_count"],
            "whole_sha256": container["whole_sha256"],
            "reconstructed_sha256": reconstructed_sha256,
            "per_chunk_verified_count": container["chunk_count"],
            "execution_status": "completed",
        }
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(f"unpacked: {args.container} -> {args.output}")
        print(f"receipt written: {args.receipt}")

    elif args.cmd == "roundtrip":
        data = Path(args.input).read_bytes()
        container = build_bog_container_v1(
            data,
            chunk_size=args.chunk_size,
            auto_chunk=args.auto_chunk,
            transform_tournament=args.transform_tournament,
        )
        if Path(args.container).suffix == ".bogpk":
            write_bogpk_container(container, args.container)
        else:
            write_bog_container(container, args.container)

        bogasm = compile_bog_container_to_bogasm(container)
        Path(args.bogasm).write_text(bogasm)
        Path(args.bogbin).write_bytes(Assembler().assemble_text(bogasm))

        run_receipt, exit_code = run_file_with_block_receipt(args.bogbin)
        reconstructed = reconstruct_bog_container_bytes(container)
        Path(args.recovered).write_bytes(reconstructed)

        input_sha256 = hashlib.sha256(data).hexdigest()
        reconstructed_sha256 = hashlib.sha256(reconstructed).hexdigest()
        accepted_names = run_receipt.get("accepted_data_block_names", [])
        expected_names = [f"payload_chunk_{index:04d}" for index in range(container["chunk_count"])]
        execution_status = "completed" if (
            exit_code == 0
            and run_receipt.get("execution_status") == "completed"
            and accepted_names == expected_names
            and input_sha256 == reconstructed_sha256 == container["whole_sha256"]
        ) else "blocked"

        receipt = {
            "format": container["format"],
            "vm_format": container["vm_format"],
            "input_path": args.input,
            "container_path": args.container,
            "bogasm_path": args.bogasm,
            "bogbin_path": args.bogbin,
            "recovered_path": args.recovered,
            "chunk_count": container["chunk_count"],
            "chunk_size": container["chunk_size"],
            "total_residual_count": container["total_residual_count"],
            "whole_sha256": container["whole_sha256"],
            "input_sha256": input_sha256,
            "reconstructed_sha256": reconstructed_sha256,
            "per_chunk_verified_count": container["chunk_count"],
            "vm_execution_status": run_receipt.get("execution_status"),
            "accepted_data_block_names": accepted_names,
            "transform_tournament_enabled": container.get("transform_tournament_enabled", False),
            "candidate_transforms": container.get("candidate_transforms", ["identity"]),
            "selected_transform_counts": container.get("selected_transform_counts", {"identity": container["chunk_count"]}),
            "execution_status": execution_status,
        }
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

        if execution_status != "completed":
            print(json.dumps(receipt, indent=2, sort_keys=True))
            raise SystemExit(1)

        print(f"roundtrip: {args.input} -> {args.recovered}")
        print(f"container written: {args.container}")
        print(f"bogasm written: {args.bogasm}")
        print(f"bogbin written: {args.bogbin}")
        print(f"receipt written: {args.receipt}")

    elif args.cmd == "archive":
        manifest = build_directory_archive(
            args.source_dir,
            args.archive_dir,
            chunk_size=args.chunk_size,
            auto_chunk=not args.fixed_chunk,
            transform_tournament=not args.no_transform_tournament,
        )
        receipt = {
            "format": "BOGARCHIVE-create-receipt-2.0",
            "archive": args.archive_dir,
            "source": args.source_dir,
            "file_count": manifest["file_count"],
            "tree_sha256": manifest["tree_sha256"],
            "execution_status": "completed",
        }
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(f"archive written: {args.archive_dir}")
        print(f"receipt written: {args.receipt}")

    elif args.cmd == "restore":
        receipt = restore_directory_archive(args.archive_dir, args.output_dir)
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(f"restored: {args.archive_dir} -> {args.output_dir}")
        print(f"receipt written: {args.receipt}")

    elif args.cmd == "fs":
        fs = BogFS(args.archive_dir)
        if args.fs_cmd == "ls":
            print(json.dumps(fs.listdir(args.path), indent=2))
        elif args.fs_cmd == "cat":
            sys_stdout = getattr(__import__("sys"), "stdout")
            sys_stdout.buffer.write(fs.read_bytes(args.path))
        elif args.fs_cmd == "stat":
            print(json.dumps(fs.stat(args.path), indent=2, sort_keys=True))

    elif args.cmd == "store":
        if args.store_cmd == "init":
            index = init_store(args.store_dir)
            print(json.dumps(index, indent=2, sort_keys=True))
        elif args.store_cmd == "keygen":
            result = generate_keypair(args.private_key, args.public_key)
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.store_cmd == "package":
            receipt = package_directory(
                args.source_dir,
                args.bundle_dir,
                name=args.name,
                version=args.version,
                dependencies=args.dependency,
                signing_key=args.signing_key,
            )
            Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(f"package written: {args.bundle_dir}")
            print(f"receipt written: {args.receipt}")
        elif args.store_cmd == "install":
            receipt = install_bundle(
                args.store_dir,
                args.bundle_dir,
                trusted_public_keys=args.trusted_key,
                require_signature=args.require_signature,
            )
            Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(f"installed: {receipt['package']}")
            print(f"receipt written: {args.receipt}")
        elif args.store_cmd == "verify":
            receipt = verify_installed_package(
                args.store_dir,
                args.package,
                trusted_public_keys=args.trusted_key,
                require_signature=args.require_signature,
            )
            Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(json.dumps(receipt, indent=2, sort_keys=True))
            if receipt["execution_status"] != "completed":
                raise SystemExit(1)


if __name__ == "__main__":
    main()
