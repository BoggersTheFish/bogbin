import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "bogos_v32_dynamic_loader_receipt.json"
AUDIT_RECEIPT_PATH = ARTIFACTS / "bogos_v32_loader_audit_receipt.json"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def parse_receipts(output, begin, end):
    receipts = []
    for block in output.split(begin + "\n")[1:]:
        receipt = {}
        for line in block.split(end, 1)[0].splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                receipt[key] = value
        receipts.append(receipt)
    return receipts


def main():
    require(
        (ROOT / "README.md").read_text().startswith(
            ("# BOGBIN v32.0.0", "# BOGBIN v33.0.0", "# BOGBIN v34.0.0", "# BOGBIN v35.0.0")
        ),
        "README does not claim v32 or a later release",
    )
    require(
        any(
            marker in (ROOT / "PROJECT_STATUS.md").read_text()
            for marker in [
                "Current release: v32.0.0",
                "Current release: v33.0.0",
                "Current release: v34.0.0",
                "Current release: v35.0.0",
            ]
        ),
        "PROJECT_STATUS does not claim v32 or a later release",
    )
    require(
        "## v32.0.0: Dynamic Verified Process Loading" in (ROOT / "RELEASE_NOTES.md").read_text(),
        "v32 release notes missing",
    )
    docs = (ROOT / "docs/v32_dynamic_verified_loader.md").read_text()
    for marker in ["Minimal `.bogapp` Contract", "Verification And Admission", "QEMU-only"]:
        require(marker in docs, f"v32 documentation marker missing: {marker}")
    result = subprocess.run(
        ["python3", str(ROOT / "scripts/evaluate_v31_verified_paging.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    v30 = json.loads((ARTIFACTS / "bogos_v30_preemptive_scheduler_receipt.json").read_text())
    serial = v30["serial_output"]

    loads = {
        receipt["APP_PATH"]: receipt
        for receipt in parse_receipts(serial, "BOGOS_LOAD_BEGIN", "BOGOS_LOAD_END")
    }
    valid_path = "/apps/dynamic_hello.bogapp"
    require(valid_path in loads, "valid dynamic app load receipt missing")
    valid = loads[valid_path]
    required_load_fields = {
        "APP_PATH",
        "APP_NAME",
        "APP_VERSION",
        "CONTAINER_LENGTH",
        "CONTAINER_MAGIC_OK",
        "CONTAINER_VERSION_OK",
        "MANIFEST_HASH",
        "CODE_OFFSET",
        "CODE_LENGTH",
        "ENTRYPOINT",
        "CODE_HASH_EXPECTED",
        "CODE_HASH_ACTUAL",
        "HASH_MATCH",
        "CAPABILITY_POLICY",
        "APP_ACCEPTED",
        "REJECT_REASON",
        "PID",
    }
    for path, load in loads.items():
        require(required_load_fields <= load.keys(), f"incomplete load receipt for {path}")
    require(valid["APP_NAME"] == "dynamic_hello", "dynamic app name mismatch")
    require(valid["APP_VERSION"] == "1.0.0", "dynamic app version mismatch")
    require(int(valid["CONTAINER_LENGTH"]) == 136 + int(valid["CODE_LENGTH"]), "bad exact length")
    require(valid["CONTAINER_MAGIC_OK"] == "true", "valid magic was not recognized")
    require(valid["CONTAINER_VERSION_OK"] == "true", "valid version was not recognized")
    require(int(valid["CODE_OFFSET"]) == 136, "valid code offset is not canonical")
    require(int(valid["ENTRYPOINT"], 16) == 0, "v32 phase-1 entrypoint offset is not zero")
    require(valid["CAPABILITY_POLICY"] == "empty_only", "capability policy changed")
    require(valid["HASH_MATCH"] == "true", "dynamic code hash did not match")
    require(valid["APP_ACCEPTED"] == "true", "valid dynamic app was rejected")
    require(valid["REJECT_REASON"] == "none", "valid dynamic app has reject reason")
    require(valid["PID"] != "none", "valid dynamic app did not receive PID")
    require(len(valid["MANIFEST_HASH"]) == 64, "manifest hash missing")
    require(valid["CODE_HASH_EXPECTED"] == valid["CODE_HASH_ACTUAL"], "code hashes contradict")

    expected_rejections = {
        "/apps/bad_dynamic_hello.bogapp": "hash_mismatch",
        "/apps/malformed_dynamic.bogapp": "malformed",
        "/apps/invalid_entrypoint.bogapp": "invalid_entrypoint",
        "/apps/missing_dynamic.bogapp": "not_found",
        "/apps/bad_magic.bogapp": "bad_magic",
        "/apps/bad_version.bogapp": "bad_version",
        "/apps/zero_code_length.bogapp": "zero_code_length",
        "/apps/bad_code_offset.bogapp": "bad_offset",
        "/apps/bad_code_length.bogapp": "bad_length",
        "/apps/entrypoint_at_end.bogapp": "invalid_entrypoint",
        "/apps/unsupported_capability.bogapp": "unsupported_capability",
        "/apps/trailing_bytes.bogapp": "trailing_bytes",
        "/apps/bad_manifest_hash.bogapp": "manifest_hash_mismatch",
        "/apps/noncanonical_name.bogapp": "malformed",
    }
    for path, reason in expected_rejections.items():
        require(path in loads, f"missing rejection receipt for {path}")
        receipt = loads[path]
        require(receipt["APP_ACCEPTED"] == "false", f"{path} was unexpectedly accepted")
        require(receipt["REJECT_REASON"] == reason, f"wrong rejection reason for {path}")
        require(receipt["PID"] == "none", f"{path} received a PID before verification")
    require(loads["/apps/bad_dynamic_hello.bogapp"]["HASH_MATCH"] == "false", "bad hash matched")
    require(
        loads["/apps/invalid_entrypoint.bogapp"]["HASH_MATCH"] == "true",
        "invalid-entrypoint app should be rejected despite valid code hash",
    )
    require(
        loads["/apps/unsupported_capability.bogapp"]["HASH_MATCH"] == "true",
        "unsupported-capability app must retain a valid code hash",
    )

    admits = parse_receipts(serial, "BOGOS_PROCESS_ADMIT_BEGIN", "BOGOS_PROCESS_ADMIT_END")
    admits_by_path = {receipt.get("APP_PATH"): receipt for receipt in admits}
    accepted_paths = {
        path
        for path, load in loads.items()
        if load.get("APP_ACCEPTED") == "true"
        and not path.startswith(("/apps/v33_", "/apps/v34_", "/apps/v35_"))
    }
    require(accepted_paths == {valid_path}, "unexpected accepted dynamic app set")
    for path in accepted_paths:
        require(path in admits_by_path, f"accepted app lacks process admission: {path}")
    admit = next((receipt for receipt in admits if receipt.get("APP_PATH") == valid_path), None)
    require(admit is not None, "dynamic process admission receipt missing")
    require(admit["PID"] == valid["PID"], "load/admission PID mismatch")
    require(int(admit["CR3"], 16) != 0 and int(admit["CR3"], 16) % 4096 == 0, "invalid dynamic CR3")
    require(admit["PROCESS_ISOLATION_ENFORCED"] == "true", "v31 isolation not enforced")
    require(admit["APP_EXECUTION_ALLOWED"] == "true", "dynamic execution not allowed")
    require(admit["USER_CODE_WRITABLE"] == "false", "dynamic code is writable")
    require(admit["USER_STACK_WRITABLE"] == "true", "dynamic stack is not writable")
    require(admit["ADMISSION_SOURCE"] == "dynamic_loader", "wrong admission source")

    processes = parse_receipts(serial, "BOGOS_PROCESS_BEGIN", "BOGOS_PROCESS_END")
    latest = {receipt.get("APP_PATH"): receipt for receipt in processes}
    admitted_paths = {receipt.get("APP_PATH") for receipt in admits}
    for path, load in loads.items():
        if load["APP_ACCEPTED"] == "true":
            continue
        require(load["PID"] == "none", f"rejected app received a PID: {path}")
        require(load["REJECT_REASON"] != "none", f"rejected app lacks rejection reason: {path}")
        require(path not in latest, f"rejected app received a process record: {path}")
        require(path not in admitted_paths, f"rejected app received admission: {path}")
    dynamic_process = latest[valid_path]
    require(dynamic_process["PID"] == valid["PID"], "dynamic process PID mismatch")
    require(dynamic_process["STATE_EXITED"] == "true", "dynamic app did not exit")
    require(dynamic_process["STATE_PREEMPTED"] == "true", "dynamic app was not preempted")

    preempts = parse_receipts(serial, "BOGOS_PREEMPT_BEGIN", "BOGOS_PREEMPT_END")
    require(any(receipt["PID"] == valid["PID"] for receipt in preempts), "dynamic preemption receipt missing")
    restores = parse_receipts(serial, "BOGOS_CONTEXT_RESTORE_BEGIN", "BOGOS_CONTEXT_RESTORE_END")
    require(any(receipt["PID"] == valid["PID"] for receipt in restores), "dynamic resume receipt missing")
    user_outputs = parse_receipts(serial, "BOGOS_USER_OUTPUT_BEGIN", "BOGOS_USER_OUTPUT_END")
    dynamic_outputs = [receipt for receipt in user_outputs if receipt.get("PID") == valid["PID"]]
    require(
        [receipt["OUTPUT_PREVIEW"] for receipt in dynamic_outputs]
        == ["hex:4431", "hex:4432"],
        "dynamic Ring 3 output order changed",
    )

    address_spaces = parse_receipts(serial, "BOGOS_ADDRSPACE_BEGIN", "BOGOS_ADDRSPACE_END")
    address_space = next(receipt for receipt in address_spaces if receipt.get("PID") == valid["PID"])
    require(address_space["PAGE_DIRECTORY_KIND"] == "per_process_isolated", "dynamic mapping not private")
    require(address_space["PROCESS_ISOLATION_ENFORCED"] == "true", "dynamic address space not isolated")
    require(address_space["WRITABLE_CODE_BLOCKED"] == "true", "dynamic code protection missing")

    isolation = parse_receipts(
        serial, "BOGOS_PROCESS_ISOLATION_BEGIN", "BOGOS_PROCESS_ISOLATION_END"
    )
    require(isolation and isolation[-1]["PROCESS_ISOLATION_ENFORCED"] == "true", "v31 isolation proof missing")
    require(
        all(marker in serial for marker in ["\nA1\n", "\nB1\n", "\nA2\n", "\nB2\n"]),
        "v30 preemption output evidence missing",
    )
    require(len(v30["qemu_serial_receipt_hash"]) == 64, "serial log hash missing")
    require(len(v30["bogfs_image_hash"]) == 64, "BogFS image hash missing")

    receipt = {
        "format": "BOGOS-v32-dynamic-loader-receipt-1.0",
        "milestone_status": "dynamic_verified_loader_phase1",
        "execution_status": "completed",
        "platform_boundary": "qemu-only",
        "dynamic_app_loaded": True,
        "dynamic_app_pid": valid["PID"],
        "dynamic_app_private_mapping": True,
        "dynamic_app_ring3_execution": True,
        "dynamic_app_preempted": True,
        "hash_mismatch_rejected": True,
        "malformed_rejected": True,
        "invalid_entrypoint_rejected": True,
        "missing_app_rejected": True,
        "v31_isolation_preserved": True,
        "v30_preemption_preserved": True,
        "serial_log_hash": v30["qemu_serial_receipt_hash"],
        "bogfs_image_hash": v30["bogfs_image_hash"],
        "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "load_evidence": [loads[valid_path], *[loads[path] for path in expected_rejections]],
        "admission_evidence": admit,
        "address_space_evidence": address_space,
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    audit_receipt = {
        "milestone": "v32.1-loader-hardening-audit",
        "release_under_audit": "v32.0.0",
        "accepted_dynamic_app_count": len(accepted_paths),
        "rejected_dynamic_app_count": len(expected_rejections),
        "rejection_reasons_seen": sorted(
            {loads[path]["REJECT_REASON"] for path in expected_rejections}
        ),
        "rejected_apps_allocated_pid": False,
        "accepted_apps_private_mapped": True,
        "v31_isolation_preserved": True,
        "v30_preemption_preserved": True,
        "qemu_only_boundary": True,
        "serial_log_hash": v30["qemu_serial_receipt_hash"],
        "initrd_or_bogfs_hash": v30["bogfs_image_hash"],
        "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_status": "completed",
    }
    AUDIT_RECEIPT_PATH.write_text(json.dumps(audit_receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print(f"Audit receipt written to {AUDIT_RECEIPT_PATH}")
    print("v32 Dynamic Verified Loader Phase 1 PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v32 Dynamic Loader evaluator FAILED: {exc}")
        sys.exit(1)
