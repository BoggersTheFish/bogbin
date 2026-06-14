import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "bogos_v35_1_writable_bogfs_audit_receipt.json"


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
    require((ROOT / "README.md").read_text().startswith("# BOGBIN v35.0.0"), "v35.0.0 release claim changed")
    require("Current release: v35.0.0" in (ROOT / "PROJECT_STATUS.md").read_text(), "v35.0.0 status claim changed")
    require("## Unreleased / v35.1 writable BogFS hardening audit" in (ROOT / "RELEASE_NOTES.md").read_text(), "v35.1 release notes missing")
    docs = (ROOT / "docs/v35_1_writable_bogfs_hardening_audit.md").read_text()
    for marker in ["Length Boundary", "Version And Failure Preservation", "Path And Table Policy", "IPC Interaction"]:
        require(marker in docs, f"v35.1 documentation marker missing: {marker}")

    result = subprocess.run(
        ["python3", str(ROOT / "scripts/evaluate_v35_writable_bogfs.py")],
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
    syscalls = parse_receipts(serial, "BOGOS_SYSCALL_BEGIN", "BOGOS_SYSCALL_END")
    outputs = parse_receipts(serial, "BOGOS_USER_OUTPUT_BEGIN", "BOGOS_USER_OUTPUT_END")
    channels = parse_receipts(serial, "BOGOS_IPC_CHANNEL_BEGIN", "BOGOS_IPC_CHANNEL_END")
    sends = parse_receipts(serial, "BOGOS_IPC_SEND_BEGIN", "BOGOS_IPC_SEND_END")
    polls = parse_receipts(serial, "BOGOS_IPC_POLL_BEGIN", "BOGOS_IPC_POLL_END")
    recvs = parse_receipts(serial, "BOGOS_IPC_RECV_BEGIN", "BOGOS_IPC_RECV_END")

    paths = {
        "edges": "/apps/v35_1_bogfs_edges.bogapp",
        "ipc": "/apps/v35_1_ipc_bogfs.bogapp",
    }
    load_by_path = {r["APP_PATH"]: r for r in loads}
    admit_by_path = {r["APP_PATH"]: r for r in admits}
    latest_process = {r["APP_PATH"]: r for r in processes}
    for path in paths.values():
        require(load_by_path[path]["APP_ACCEPTED"] == "true", f"loader rejected audit app: {path}")
        require(admit_by_path[path]["PROCESS_ISOLATION_ENFORCED"] == "true", f"isolation missing: {path}")
        require(latest_process[path]["STATE_EXITED"] == "true", f"audit app did not exit: {path}")
        require(latest_process[path]["STATE_BLOCKED"] == "false", f"audit app blocked: {path}")

    edge_pid = load_by_path[paths["edges"]]["PID"]
    ipc_pid = load_by_path[paths["ipc"]]["PID"]
    edge_files = [r for r in files if r["PID"] == edge_pid]
    edge_writes = [r for r in edge_files if r["OPERATION"] == "write"]
    edge_syscalls = [r for r in syscalls if r["PID"] == edge_pid and r["SYSCALL"] == "bogfs_write"]

    zero = next(r for r in edge_writes if r["LENGTH"] == "0")
    require(zero["STATUS"] == "rejected" and zero["REJECT_REASON"] == "invalid_length", "zero-length behavior is not explicit rejection")
    exact_max = next(r for r in edge_writes if r["PATH"] == "/data/fill.bin" and r["LENGTH"] == "64" and r["STATUS"] == "accepted")
    require(exact_max["NEW_VERSION"] == str(int(exact_max["OLD_VERSION"]) + 1), "exact-max write did not version")
    require(any(r["ARG3"] == "00000041" and r["REJECT_REASON"] == "invalid_length" for r in edge_syscalls), "max+1 write rejection missing")

    shared_accepted = [r for r in edge_writes if r["PATH"] == "/data/shared.bin" and r["STATUS"] == "accepted"]
    require([(r["OLD_VERSION"], r["NEW_VERSION"]) for r in shared_accepted] == [("1", "2"), ("2", "3")], "repeated-write versions are not deterministic")
    committed_hash = hashlib.sha256(b"AUDIT-B!").hexdigest()
    require(shared_accepted[-1]["NEW_HASH"] == committed_hash, "repeated write committed wrong hash")

    failed = next(r for r in edge_writes if r["PATH"] == "/data/shared.bin" and r["REJECT_REASON"] == "storage_full")
    require(failed["OLD_VERSION"] == failed["NEW_VERSION"] == "3", "failed write changed version")
    require(failed["OLD_HASH"] == failed["NEW_HASH"] == committed_hash, "failed write changed hash")
    require(failed["MUTATED_TRUSTED_STATE"] == "false", "failed write reports mutation")
    stats = [r for r in edge_files if r["OPERATION"] == "stat" and r["PATH"] == "/data/shared.bin"]
    require(len(stats) == 2, "before/after stat receipts missing")
    require(stats[0]["NEW_VERSION"] == stats[1]["NEW_VERSION"] == "3", "failed write changed stat version")
    require(stats[0]["NEW_HASH"] == stats[1]["NEW_HASH"] == committed_hash, "failed write changed stat hash")
    reads = [r for r in edge_files if r["OPERATION"] == "read" and r["PATH"] == "/data/shared.bin"]
    require(len(reads) == 2, "before/after read receipts missing")
    require(all(r["SHA256"] == committed_hash and r["NEW_VERSION"] == "3" for r in reads), "failed write changed read result")
    require(any(r["PID"] == edge_pid and r["OUTPUT_PREVIEW"] == "hex:41554449542d4221" for r in outputs), "old committed read bytes not observed")

    reasons = {r["REJECT_REASON"] for r in edge_writes if r["STATUS"] == "rejected"}
    require({"invalid_path", "protected_path", "file_table_full", "invalid_pointer", "storage_full"} <= reasons, "path/table/pointer audit matrix incomplete")
    require(any(r["ARG2"] == "00800000" and r["REJECT_REASON"] == "invalid_pointer" for r in edge_syscalls), "cross-process pointer rejection missing")
    protected_pids = {r["PID"] for r in files if r["OPERATION"] == "write" and r["REJECT_REASON"] == "protected_path"}
    require({edge_pid, ipc_pid} <= protected_pids, "two-process protected-path rejection missing")
    require(all(r["MUTATED_TRUSTED_STATE"] == "false" for r in edge_writes if r["STATUS"] == "rejected"), "rejected audit write mutated state")

    channel = next(r for r in channels if r["PID"] == ipc_pid and r["STATUS"] == "accepted")
    channel_id = channel["CHANNEL_ID"]
    send = next(r for r in sends if r["FROM_PID"] == ipc_pid and r["CHANNEL_ID"] == channel_id)
    ipc_polls = [r for r in polls if r["PID"] == ipc_pid and r["CHANNEL_ID"] == channel_id]
    recv = next(r for r in recvs if r["TO_PID"] == ipc_pid and r["CHANNEL_ID"] == channel_id)
    require(send["QUEUE_DEPTH_AFTER"] == "1", "IPC audit message was not queued")
    require([r["QUEUE_DEPTH"] for r in ipc_polls] == ["1", "1"], "failed BogFS operation changed IPC queue depth")
    require(send["MESSAGE_ID"] == recv["MESSAGE_ID"] and send["PAYLOAD_HASH"] == recv["PAYLOAD_HASH"], "IPC message changed across failed BogFS operation")
    require(recv["QUEUE_DEPTH_AFTER"] == "0", "IPC audit message was not received")
    require(any(r["PID"] == ipc_pid and r["OUTPUT_PREVIEW"] == "hex:4950432d56333531" for r in outputs), "IPC payload not observed")

    receipt = {
        "milestone": "v35.1-writable-bogfs-hardening-audit",
        "release_under_audit": "v35.0.0",
        "zero_length_behavior": "rejected_invalid_length",
        "exact_max_write_succeeds": True,
        "max_plus_one_rejects": True,
        "repeated_write_versions": [r["NEW_VERSION"] for r in shared_accepted],
        "failed_write_preserved_hash_version": True,
        "failed_write_preserved_stat": True,
        "failed_write_preserved_read": True,
        "path_alias_rejected": True,
        "protected_paths_rejected_for_two_processes": True,
        "cross_process_pointer_rejected": True,
        "file_table_and_storage_full_rejected_without_mutation": True,
        "ipc_queue_preserved_across_failed_bogfs": True,
        "serial_log_hash": v30["qemu_serial_receipt_hash"],
        "initrd_or_bogfs_hash": v30["bogfs_image_hash"],
        "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_status": "completed",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v35.1 Writable BogFS Hardening Audit PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v35.1 Writable BogFS Hardening Audit FAILED: {exc}")
        sys.exit(1)
