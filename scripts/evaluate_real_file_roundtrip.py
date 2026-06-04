from __future__ import annotations

import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bogvm.assembler import Assembler
from bogvm.bases import BASIS_ORDER
from bogvm.container import (
    build_bog_container_v1,
    compile_bog_container_to_bogasm,
    read_container,
    reconstruct_bog_container_bytes,
    write_bogpk_container,
)
from bogvm.transforms import TRANSFORM_ORDER
from bogvm.vm import run_file_with_block_receipt


DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "real_file_roundtrip"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "real_file_roundtrip_report.json"
DEFAULT_RECEIPT_PATH = ROOT / "artifacts" / "real_file_roundtrip_receipt.json"
DEFAULT_TRANSFORM_REPORT_PATH = ROOT / "artifacts" / "reversible_transform_tournament_report.json"
DEFAULT_TRANSFORM_RECEIPT_PATH = ROOT / "artifacts" / "reversible_transform_tournament_receipt.json"
V1_2_MEAN_RESIDUAL_DENSITY = 0.631188


def deterministic_fixtures() -> list[dict]:
    return [
        {
            "name": "text_payload",
            "file_type": "text",
            "filename": "text_payload.txt",
            "data": (
                b"BOGBIN real file roundtrip text fixture.\n"
                b"Line two has repeated words words words and ramp-like punctuation: !\"#$%&'()*+,-./\n"
            ),
        },
        {
            "name": "json_payload",
            "file_type": "json",
            "filename": "json_payload.json",
            "data": (
                b'{"format":"fixture","items":[1,2,3,4],"name":"bogbin",'
                b'"nested":{"alpha":true,"beta":"deterministic"},"text":"aaaaabbbbbccccc"}\n'
            ),
        },
        {
            "name": "binary_noise_like_payload",
            "file_type": "binary",
            "filename": "binary_noise_like_payload.bin",
            "data": bytes(((i * 73 + 41) % 256) for i in range(160)),
        },
        {
            "name": "png_payload",
            "file_type": "png",
            "filename": "png_payload.png",
            "data": _png_bytes(),
        },
        {
            "name": "wav_payload",
            "file_type": "wav",
            "filename": "wav_payload.wav",
            "data": _wav_bytes(),
        },
    ]


def evaluate(
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    report_path: Path = DEFAULT_REPORT_PATH,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    chunk_size: int = 64,
    auto_chunk: bool = True,
    transform_tournament: bool = True,
) -> tuple[dict, dict]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir = artifact_dir / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    per_case = []
    for fixture in deterministic_fixtures():
        case = _evaluate_case(
            fixture,
            artifact_dir,
            fixtures_dir,
            chunk_size,
            auto_chunk=auto_chunk,
            transform_tournament=transform_tournament,
        )
        per_case.append(case)

    total_input_bytes = sum(case["input_size"] for case in per_case)
    total_chunk_count = sum(case["chunk_count"] for case in per_case)
    total_residual_count = sum(case["total_residual_count"] for case in per_case)
    total_container_bytes = sum(case["container_size"] for case in per_case)
    passed_roundtrip_count = sum(1 for case in per_case if case["roundtrip_passed"])
    case_count = len(per_case)

    current_mean_residual_density = _ratio(total_residual_count, total_input_bytes)
    residual_density_delta = round(current_mean_residual_density - V1_2_MEAN_RESIDUAL_DENSITY, 6)

    report = {
        "format": "BOGBIN-real-file-roundtrip-report-1.5",
        "v1_2_mean_residual_density": V1_2_MEAN_RESIDUAL_DENSITY,
        "current_mean_residual_density": current_mean_residual_density,
        "residual_density_delta_from_v1_2": residual_density_delta,
        "residual_density_improved_from_v1_2": current_mean_residual_density < V1_2_MEAN_RESIDUAL_DENSITY,
        "case_count": case_count,
        "container_format": "BOGPK-0.1",
        "passed_roundtrip_count": passed_roundtrip_count,
        "roundtrip_success_rate": _ratio(passed_roundtrip_count, case_count),
        "total_input_bytes": total_input_bytes,
        "total_chunk_count": total_chunk_count,
        "total_residual_count": total_residual_count,
        "mean_residual_density": current_mean_residual_density,
        "transform_tournament_enabled": transform_tournament,
        "candidate_transforms": list(TRANSFORM_ORDER) if transform_tournament else ["identity"],
        "aggregate_transform_counts": _aggregate_transform_counts(per_case),
        "total_container_bytes": total_container_bytes,
        "mean_container_to_input_ratio": _ratio(total_container_bytes, total_input_bytes),
        "aggregate_container_smaller_than_input": total_container_bytes < total_input_bytes,
        "all_containers_smaller_than_input": all(case["container_smaller_than_input"] for case in per_case),
        "per_case": per_case,
    }

    receipt = {
        "format": "BOGBIN-real-file-roundtrip-receipt-1.5",
        "report_path": str(report_path),
        "case_count": case_count,
        "passed_roundtrip_count": passed_roundtrip_count,
        "roundtrip_success_rate": report["roundtrip_success_rate"],
        "all_cases_passed": passed_roundtrip_count == case_count,
        "execution_status": "completed" if passed_roundtrip_count == case_count else "blocked",
        "transform_tournament_enabled": transform_tournament,
        "all_containers_smaller_than_input": report["all_containers_smaller_than_input"],
        "aggregate_container_smaller_than_input": report["aggregate_container_smaller_than_input"],
        "report_sha256": _stable_json_hash(report),
    }

    _write_json(report_path, report)
    receipt["report_file_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    _write_json(receipt_path, receipt)
    return report, receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument("--transform-report", default=None)
    parser.add_argument("--transform-receipt", default=None)
    parser.add_argument("--chunk-size", type=int, default=64)
    parser.add_argument("--fixed-chunk", action="store_true")
    args = parser.parse_args()

    report, receipt = evaluate(
        artifact_dir=Path(args.artifact_dir),
        report_path=Path(args.report),
        receipt_path=Path(args.receipt),
        chunk_size=args.chunk_size,
        auto_chunk=not args.fixed_chunk,
        transform_tournament=True,
    )
    transform_report_path = Path(args.transform_report) if args.transform_report else _default_transform_report_path(Path(args.report))
    transform_receipt_path = Path(args.transform_receipt) if args.transform_receipt else _default_transform_receipt_path(Path(args.receipt))
    transform_report, transform_receipt = write_transform_tournament_report(
        report,
        transform_report_path,
        transform_receipt_path,
    )
    print(json.dumps({
        "report": str(Path(args.report)),
        "receipt": str(Path(args.receipt)),
        "transform_report": str(transform_report_path),
        "transform_receipt": str(transform_receipt_path),
        "case_count": report["case_count"],
        "passed_roundtrip_count": report["passed_roundtrip_count"],
        "transform_tournament_enabled": transform_report["transform_tournament_enabled"],
        "execution_status": receipt["execution_status"],
    }, indent=2, sort_keys=True))
    if receipt["execution_status"] != "completed":
        raise SystemExit(1)


def _evaluate_case(
    fixture: dict,
    artifact_dir: Path,
    fixtures_dir: Path,
    chunk_size: int,
    auto_chunk: bool,
    transform_tournament: bool,
) -> dict:
    name = fixture["name"]
    data = fixture["data"]
    input_path = fixtures_dir / fixture["filename"]
    container_path = artifact_dir / f"{name}.bogpk"
    bogasm_path = artifact_dir / f"{name}.bogasm"
    bogbin_path = artifact_dir / f"{name}.bogbin"
    run_receipt_path = artifact_dir / f"{name}_run_receipt.json"
    recovered_path = artifact_dir / f"{name}_recovered.bin"

    input_path.write_bytes(data)
    original_sha256 = hashlib.sha256(data).hexdigest()

    source_container = build_bog_container_v1(
        data,
        chunk_size=chunk_size,
        auto_chunk=auto_chunk,
        transform_tournament=transform_tournament,
    )
    write_bogpk_container(source_container, str(container_path))
    container_size = container_path.stat().st_size
    container = read_container(str(container_path))

    bogasm = compile_bog_container_to_bogasm(container)
    bogasm_path.write_text(bogasm)
    bogbin_path.write_bytes(Assembler().assemble_text(bogasm))

    run_receipt, exit_code = run_file_with_block_receipt(bogbin_path)
    _write_json(run_receipt_path, run_receipt)

    recovered = reconstruct_bog_container_bytes(container)
    recovered_path.write_bytes(recovered)
    recovered_sha256 = hashlib.sha256(recovered).hexdigest()

    basis_counts = {basis: 0 for basis in BASIS_ORDER}
    transform_counts = {transform: 0 for transform in TRANSFORM_ORDER}
    for chunk in container["chunks"]:
        basis_counts[chunk["basis"]] += 1
        transform_counts[chunk.get("transform", "identity")] += 1

    input_size = len(data)
    total_residual_count = container["total_residual_count"]
    accepted_names = run_receipt.get("accepted_data_block_names", [])
    expected_names = [f"payload_chunk_{index:04d}" for index in range(container["chunk_count"])]
    vm_run_status = run_receipt.get("execution_status", "blocked")
    roundtrip_passed = (
        exit_code == 0
        and vm_run_status == "completed"
        and accepted_names == expected_names
        and original_sha256 == recovered_sha256 == container["whole_sha256"]
    )

    return {
        "name": name,
        "file_type": fixture["file_type"],
        "input_size": input_size,
        "chunk_count": container["chunk_count"],
        "chunk_tournament_enabled": source_container.get("chunk_tournament_enabled", False),
        "candidate_chunk_sizes": source_container.get("candidate_chunk_sizes", [container["chunk_size"]]),
        "selected_chunk_size": source_container.get("selected_chunk_size", container["chunk_size"]),
        "chunk_tournament_results": source_container.get("chunk_tournament_results", []),
        "transform_tournament_enabled": container.get("transform_tournament_enabled", False),
        "candidate_transforms": container.get("candidate_transforms", ["identity"]),
        "selected_transform_counts": container.get("selected_transform_counts", transform_counts),
        "total_residual_count": total_residual_count,
        "residual_density": _ratio(total_residual_count, input_size),
        "basis_counts": basis_counts,
        "transform_counts": transform_counts,
        "container_size": container_size,
        "container_to_input_ratio": _ratio(container_size, input_size),
        "container_smaller_than_input": container_size < input_size,
        "original_sha256": original_sha256,
        "recovered_sha256": recovered_sha256,
        "vm_run_status": vm_run_status,
        "roundtrip_passed": roundtrip_passed,
    }


def _png_bytes() -> bytes:
    width = 8
    height = 8
    color_type = 2
    bit_depth = 8
    scanlines = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend((
                (x * 31 + y * 17) % 256,
                (x * 11 + y * 47) % 256,
                (x * 23 + y * 7) % 256,
            ))
        scanlines.append(bytes(row))

    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    idat = zlib.compress(b"".join(scanlines), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _wav_bytes() -> bytes:
    samples = bytes(((i * 9 + (i // 3) * 5) % 256) for i in range(256))
    size = (36 + len(samples)).to_bytes(4, "little")
    data_size = len(samples).to_bytes(4, "little")
    return (
        b"RIFF" + size + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (8000).to_bytes(4, "little")
        + (8000).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (8).to_bytes(2, "little")
        + b"data" + data_size + samples
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _stable_json_hash(obj: dict) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _aggregate_transform_counts(per_case: list[dict]) -> dict:
    counts = {transform: 0 for transform in TRANSFORM_ORDER}
    for case in per_case:
        for transform, count in case["transform_counts"].items():
            counts[transform] += count
    return counts


def build_transform_tournament_report(roundtrip_report: dict) -> dict:
    return {
        "format": "BOGBIN-reversible-transform-tournament-report-1.5",
        "transform_tournament_enabled": roundtrip_report["transform_tournament_enabled"],
        "container_format": roundtrip_report["container_format"],
        "candidate_transforms": roundtrip_report["candidate_transforms"],
        "aggregate_transform_counts": roundtrip_report["aggregate_transform_counts"],
        "case_count": roundtrip_report["case_count"],
        "total_input_bytes": roundtrip_report["total_input_bytes"],
        "total_container_bytes": roundtrip_report["total_container_bytes"],
        "mean_container_to_input_ratio": roundtrip_report["mean_container_to_input_ratio"],
        "aggregate_container_smaller_than_input": roundtrip_report["aggregate_container_smaller_than_input"],
        "all_containers_smaller_than_input": roundtrip_report["all_containers_smaller_than_input"],
        "total_residual_count": roundtrip_report["total_residual_count"],
        "mean_residual_density": roundtrip_report["mean_residual_density"],
        "per_case": [
            {
                "name": case["name"],
                "file_type": case["file_type"],
                "input_size": case["input_size"],
                "chunk_count": case["chunk_count"],
                "selected_chunk_size": case["selected_chunk_size"],
                "transform_counts": case["transform_counts"],
                "total_residual_count": case["total_residual_count"],
                "residual_density": case["residual_density"],
                "container_size": case["container_size"],
                "container_to_input_ratio": case["container_to_input_ratio"],
                "container_smaller_than_input": case["container_smaller_than_input"],
                "roundtrip_passed": case["roundtrip_passed"],
            }
            for case in roundtrip_report["per_case"]
        ],
    }


def write_transform_tournament_report(roundtrip_report: dict, report_path: Path, receipt_path: Path) -> tuple[dict, dict]:
    report = build_transform_tournament_report(roundtrip_report)
    receipt = {
        "format": "BOGBIN-reversible-transform-tournament-receipt-1.5",
        "report_path": str(report_path),
        "case_count": report["case_count"],
        "transform_tournament_enabled": report["transform_tournament_enabled"],
        "all_containers_smaller_than_input": report["all_containers_smaller_than_input"],
        "aggregate_container_smaller_than_input": report["aggregate_container_smaller_than_input"],
        "execution_status": "completed" if all(case["roundtrip_passed"] for case in report["per_case"]) else "blocked",
        "report_sha256": _stable_json_hash(report),
    }
    _write_json(report_path, report)
    receipt["report_file_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    _write_json(receipt_path, receipt)
    return report, receipt


def _default_transform_report_path(report_path: Path) -> Path:
    if report_path == DEFAULT_REPORT_PATH:
        return DEFAULT_TRANSFORM_REPORT_PATH
    return report_path.with_name("reversible_transform_tournament_report.json")


def _default_transform_receipt_path(receipt_path: Path) -> Path:
    if receipt_path == DEFAULT_RECEIPT_PATH:
        return DEFAULT_TRANSFORM_RECEIPT_PATH
    return receipt_path.with_name("reversible_transform_tournament_receipt.json")


if __name__ == "__main__":
    main()
