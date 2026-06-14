import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "bogos_v35_writable_bogfs_receipt.json"


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
    require((ROOT / "README.md").read_text().startswith("# BOGBIN v35.0.0"), "README is not v35")
    require("Current release: v35.0.0" in (ROOT / "PROJECT_STATUS.md").read_text(), "PROJECT_STATUS is not v35")
    require("## v35.0.0: Writable Verified BogFS" in (ROOT / "RELEASE_NOTES.md").read_text(), "v35 release notes missing")
    docs = (ROOT / "docs/v35_writable_verified_bogfs.md").read_text()
    for marker in ["Register ABI", "Commit Protocol", "Negative Proof Matrix", "QEMU-only"]:
        require(marker in docs, f"v35 documentation marker missing: {marker}")

    result = subprocess.run(
        ["python3", str(ROOT / "scripts/evaluate_v34_ipc.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)

    v30 = json.loads((ARTIFACTS / "bogos_v30_preemptive_scheduler_receipt.json").read_text())
    serial = v30["serial_output"]
    loads = parse_receipts(serial, "BOGOS_LOAD_BEGIN", "BOGOS_LOAD_END")
    admits = parse_receipts(serial, "BOGOS_PROCESS_ADMIT_BEGIN", "BOGOS_PROCESS_ADMIT_END")
    processes = parse_receipts(serial, "BOGOS_PROCESS_BEGIN", "BOGOS_PROCESS_END")
    files = parse_receipts(serial, "BOGOS_WRITABLE_BOGFS_BEGIN", "BOGOS_WRITABLE_BOGFS_END")
    invariants = parse_receipts(serial, "BOGOS_WRITABLE_BOGFS_INVARIANTS_BEGIN", "BOGOS_WRITABLE_BOGFS_INVARIANTS_END")
    syscalls = parse_receipts(serial, "BOGOS_SYSCALL_BEGIN", "BOGOS_SYSCALL_END")
    outputs = parse_receipts(serial, "BOGOS_USER_OUTPUT_BEGIN", "BOGOS_USER_OUTPUT_END")

    load_by_path = {receipt["APP_PATH"]: receipt for receipt in loads}
    admit_by_path = {receipt["APP_PATH"]: receipt for receipt in admits}
    latest_process = {receipt["APP_PATH"]: receipt for receipt in processes}
    paths = ["/apps/v35_bogfs_verified.bogapp", "/apps/v35_bogfs_negative.bogapp"]
    for path in paths:
        require(load_by_path[path]["APP_ACCEPTED"] == "true", f"v32 loader rejected {path}")
        require(admit_by_path[path]["PROCESS_ISOLATION_ENFORCED"] == "true", f"v31 isolation missing: {path}")
        require(latest_process[path]["STATE_EXITED"] == "true", f"v35 app did not exit: {path}")
        require(latest_process[path]["STATE_BLOCKED"] == "false", f"v35 app was blocked: {path}")

    verified_pid = load_by_path[paths[0]]["PID"]
    negative_pid = load_by_path[paths[1]]["PID"]
    payload_hash = hashlib.sha256(b"V35-DATA").hexdigest()
    shared_writes = [r for r in files if r["OPERATION"] == "write" and r["PATH"] == "/data/shared.bin"]
    accepted = next(r for r in shared_writes if r["STATUS"] == "accepted")
    require(accepted["PID"] == verified_pid, "accepted write PID mismatch")
    require(accepted["LENGTH"] == "8" and accepted["SHA256"] == payload_hash, "accepted write content receipt mismatch")
    require(accepted["OLD_VERSION"] == "0" and accepted["NEW_VERSION"] == "1", "accepted write version transition mismatch")
    require(accepted["NEW_HASH"] == payload_hash and accepted["MUTATED_TRUSTED_STATE"] == "true", "accepted write was not hash-visible")

    base_pids = {verified_pid, negative_pid}
    rejected_writes = [
        r for r in files
        if r["PID"] in base_pids and r["OPERATION"] == "write" and r["STATUS"] == "rejected"
    ]
    reasons = {r["REJECT_REASON"] for r in rejected_writes}
    require(
        {"invalid_pointer", "invalid_length", "read_only_path", "invalid_path", "storage_full", "receipt_hash_mismatch"} <= reasons,
        "negative write matrix incomplete",
    )
    require(all(r["MUTATED_TRUSTED_STATE"] == "false" for r in rejected_writes), "rejected write mutated trusted state")
    for receipt in rejected_writes:
        if receipt["OLD_HASH"] != "none":
            require(receipt["OLD_HASH"] == receipt["NEW_HASH"], f"rejected write changed hash: {receipt['REJECT_REASON']}")
            require(receipt["OLD_VERSION"] == receipt["NEW_VERSION"], f"rejected write changed version: {receipt['REJECT_REASON']}")

    invalid_pointer_writes = [r for r in rejected_writes if r["REJECT_REASON"] == "invalid_pointer"]
    require(len(invalid_pointer_writes) == 2, "bad-pointer and cross-process-pointer cases missing")
    require(any(r["REJECT_REASON"] == "storage_full" and r["PATH"] == "/data/shared.bin" for r in rejected_writes), "full-storage rejection missing")
    require(any(r["REJECT_REASON"] == "receipt_hash_mismatch" and r["PATH"] == "/data/hashfail.bin" for r in rejected_writes), "failed hash/state proof missing")

    shared_reads = [
        r for r in files
        if r["PID"] in base_pids
        and r["OPERATION"] == "read"
        and r["PATH"] == "/data/shared.bin"
        and r["STATUS"] == "accepted"
    ]
    require(len(shared_reads) == 2, "committed reads missing")
    require(all(r["LENGTH"] == "8" and r["SHA256"] == payload_hash and r["NEW_VERSION"] == "1" for r in shared_reads), "read returned uncommitted or changed content")
    require(any(r["OPERATION"] == "stat" and r["PATH"] == "/data/shared.bin" and r["SHA256"] == payload_hash for r in files), "verified stat receipt missing")
    require(sum(1 for r in outputs if r["OUTPUT_PREVIEW"] == "hex:5633352d44415441") == 2, "apps did not observe exact committed bytes")

    bogfs_syscalls = [r for r in syscalls if r["SYSCALL_NUMBER"] in {"17", "18", "19"}]
    require(bogfs_syscalls and all(r["ABI_VERSION"] == "2" for r in bogfs_syscalls), "BogFS calls escaped ABI v2")
    require(all(r["MUTATED_TRUSTED_STATE"] == "false" for r in bogfs_syscalls if r["STATUS"] == "rejected"), "rejected syscall mutation claim")
    write_syscalls = [r for r in bogfs_syscalls if r["SYSCALL_NUMBER"] == "17"]
    require(any(r["ARG2"] == "00100000" and r["REJECT_REASON"] == "invalid_pointer" for r in write_syscalls), "bad kernel pointer proof missing")
    require(any(r["ARG2"] == "00800000" and r["REJECT_REASON"] == "invalid_pointer" for r in write_syscalls), "cross-process pointer proof missing")
    require(len(invariants) == 1, "expected exactly one writable BogFS invariant receipt")
    invariant = invariants[0]
    for key in [
        "QEMU_ONLY", "IN_MEMORY_ONLY", "KERNEL_OWNED_STORAGE", "POINTER_VALIDATION_ENFORCED",
        "PATH_POLICY_ENFORCED", "BOUNDED_STORAGE_ENFORCED", "COMMIT_AFTER_HASH_RECEIPT_CHECK",
        "READS_RETURN_COMMITTED_VERIFIED_CONTENTS", "V31_ISOLATION_PRESERVED", "V32_LOADER_PRESERVED",
        "V33_SYSCALL_ABI_PRESERVED", "V34_IPC_PRESERVED",
    ]:
        require(invariant[key] == "true", f"writable BogFS invariant failed: {key}")
    require(invariant["REJECTED_WRITES_MUTATED_STATE"] == "false", "invariant reports rejected mutation")
    require(invariant["POSIX_FILESYSTEM"] == "false", "v35 claims POSIX filesystem")

    receipt = {
        "milestone": "v35.0.0-writable-verified-bogfs",
        "platform": "qemu",
        "syscall_numbers": {"17": "bogfs_write", "18": "bogfs_read", "19": "bogfs_stat"},
        "accepted_write": accepted,
        "rejected_write_cases": rejected_writes,
        "rejected_writes_mutated_state": False,
        "committed_read_hash": payload_hash,
        "bounded_storage_bytes": 96,
        "max_file_bytes": 64,
        "in_memory_only": True,
        "v31_isolation_preserved": True,
        "v32_loader_preserved": True,
        "v33_syscall_abi_preserved": True,
        "v34_ipc_preserved": True,
        "serial_log_hash": v30["qemu_serial_receipt_hash"],
        "initrd_or_bogfs_hash": v30["bogfs_image_hash"],
        "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_status": "completed",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v35 Writable Verified BogFS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v35 Writable Verified BogFS evaluator FAILED: {exc}")
        sys.exit(1)
