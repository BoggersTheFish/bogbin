import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "bogos_v34_ipc_receipt.json"


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
    require((ROOT / "README.md").read_text().startswith(("# BOGBIN v34.0.0", "# BOGBIN v35.0.0")), "README does not claim v34 or later")
    require(any(marker in (ROOT / "PROJECT_STATUS.md").read_text() for marker in ["Current release: v34.0.0", "Current release: v35.0.0"]), "PROJECT_STATUS does not claim v34 or later")
    require("## v34.0.0: Verified IPC / Message Passing" in (ROOT / "RELEASE_NOTES.md").read_text(), "v34 release notes missing")
    docs = (ROOT / "docs/v34_verified_ipc.md").read_text()
    for marker in ["Register ABI", "Channel And Queue Model", "Pointer Validation And Rejections", "QEMU-only"]:
        require(marker in docs, f"v34 documentation marker missing: {marker}")

    result = subprocess.run(
        ["python3", str(ROOT / "scripts/evaluate_v33_syscall_abi.py")],
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
    channels = parse_receipts(serial, "BOGOS_IPC_CHANNEL_BEGIN", "BOGOS_IPC_CHANNEL_END")
    sends = parse_receipts(serial, "BOGOS_IPC_SEND_BEGIN", "BOGOS_IPC_SEND_END")
    recvs = parse_receipts(serial, "BOGOS_IPC_RECV_BEGIN", "BOGOS_IPC_RECV_END")
    polls = parse_receipts(serial, "BOGOS_IPC_POLL_BEGIN", "BOGOS_IPC_POLL_END")
    invariants = parse_receipts(serial, "BOGOS_IPC_INVARIANTS_BEGIN", "BOGOS_IPC_INVARIANTS_END")
    syscalls = parse_receipts(serial, "BOGOS_SYSCALL_BEGIN", "BOGOS_SYSCALL_END")
    outputs = parse_receipts(serial, "BOGOS_USER_OUTPUT_BEGIN", "BOGOS_USER_OUTPUT_END")
    preempts = parse_receipts(serial, "BOGOS_PREEMPT_BEGIN", "BOGOS_PREEMPT_END")
    isolation = parse_receipts(serial, "BOGOS_PROCESS_ISOLATION_BEGIN", "BOGOS_PROCESS_ISOLATION_END")

    load_by_path = {receipt["APP_PATH"]: receipt for receipt in loads}
    admit_by_path = {receipt["APP_PATH"]: receipt for receipt in admits}
    latest_process = {receipt["APP_PATH"]: receipt for receipt in processes}
    paths = {
        "sender": "/apps/v34_ipc_sender.bogapp",
        "receiver": "/apps/v34_ipc_receiver.bogapp",
        "negative": "/apps/v34_ipc_negative.bogapp",
    }
    for path in paths.values():
        require(load_by_path[path]["APP_ACCEPTED"] == "true", f"v32 loader rejected {path}")
        require(admit_by_path[path]["PROCESS_ISOLATION_ENFORCED"] == "true", f"v31 isolation missing: {path}")
        require(admit_by_path[path]["ADMISSION_SOURCE"] == "dynamic_loader", f"not dynamically admitted: {path}")
        require(latest_process[path]["STATE_EXITED"] == "true", f"IPC app did not exit: {path}")
        require(latest_process[path]["STATE_BLOCKED"] == "false", f"IPC app was blocked: {path}")

    sender_pid = load_by_path[paths["sender"]]["PID"]
    receiver_pid = load_by_path[paths["receiver"]]["PID"]
    negative_pid = load_by_path[paths["negative"]]["PID"]
    require(len({sender_pid, receiver_pid, negative_pid}) == 3, "IPC proof apps do not have distinct PIDs")

    accepted_channels = [receipt for receipt in channels if receipt["STATUS"] == "accepted"]
    require(len(accepted_channels) == 2, "expected sender and self-test channels")
    channel = next(receipt for receipt in accepted_channels if receipt["PID"] == sender_pid)
    require(channel["PEER_PID"] == receiver_pid, "positive channel peer mismatch")
    require(channel["CREATED_BY_DYNAMIC_LOADER_ADMITTED_PROCESS"] == "true", "channel admission source missing")
    channel_id = channel["CHANNEL_ID"]

    accepted_send = next(
        receipt
        for receipt in sends
        if receipt["FROM_PID"] == sender_pid and receipt["STATUS"] == "accepted"
    )
    accepted_recv = next(
        receipt
        for receipt in recvs
        if receipt["TO_PID"] == receiver_pid and receipt["STATUS"] == "accepted"
    )
    require(accepted_send["CHANNEL_ID"] == channel_id == accepted_recv["CHANNEL_ID"], "delivery channel mismatch")
    require(accepted_send["MESSAGE_ID"] == accepted_recv["MESSAGE_ID"], "delivery message ID mismatch")
    require(accepted_send["PAYLOAD_HASH"] == accepted_recv["PAYLOAD_HASH"], "send/receive payload hash mismatch")
    require(accepted_send["PAYLOAD_LENGTH"] == accepted_recv["PAYLOAD_LENGTH"] == "8", "payload length mismatch")
    require(accepted_send["QUEUE_DEPTH_AFTER"] == "1", "send was not queued")
    require(accepted_recv["QUEUE_DEPTH_AFTER"] == "0", "receive did not consume delivery")
    require(
        any(receipt["PID"] == receiver_pid and receipt["OUTPUT_PREVIEW"] == "hex:5633342d4d53470a" for receipt in outputs),
        "receiver did not emit exact kernel-controlled confirmation",
    )

    rejected_sends = [receipt for receipt in sends if receipt["STATUS"] == "rejected"]
    rejected_recvs = [receipt for receipt in recvs if receipt["STATUS"] == "rejected"]
    rejected_polls = [receipt for receipt in polls if receipt["STATUS"] == "rejected"]
    send_reasons = {receipt["REJECT_REASON"] for receipt in rejected_sends}
    recv_reasons = {receipt["REJECT_REASON"] for receipt in rejected_recvs}
    require({"invalid_pointer", "invalid_length", "queue_full"} <= send_reasons, "send rejection matrix incomplete")
    require({"invalid_pointer", "buffer_too_small", "unauthorized"} <= recv_reasons, "receive rejection matrix incomplete")
    require(any(receipt["REJECT_REASON"] == "invalid_channel" for receipt in rejected_polls), "invalid channel rejection missing")
    for receipt in rejected_sends + rejected_recvs:
        require(receipt["MUTATED_TRUSTED_STATE"] == "false", "rejected IPC mutated trusted state")

    preserved = [
        receipt
        for receipt in rejected_recvs
        if receipt["TO_PID"] == negative_pid
        and receipt["REJECT_REASON"] in {"invalid_pointer", "buffer_too_small"}
    ]
    require(len(preserved) == 2, "rejected receive preservation cases missing")
    require(all(receipt["QUEUE_DEPTH_AFTER"] == "1" for receipt in preserved), "rejected receive dropped message")
    require(len({receipt["MESSAGE_ID"] for receipt in preserved}) == 1, "rejected receives observed different messages")
    negative_success = next(
        receipt
        for receipt in recvs
        if receipt["TO_PID"] == negative_pid and receipt["STATUS"] == "accepted"
    )
    require(negative_success["MESSAGE_ID"] == preserved[0]["MESSAGE_ID"], "preserved message was not later delivered")
    require(negative_success["PAYLOAD_HASH"] == preserved[0]["PAYLOAD_HASH"], "preserved payload changed")
    require(
        any(receipt["PID"] == negative_pid and receipt["QUEUE_DEPTH"] == "1" and receipt["STATUS"] == "accepted" for receipt in polls),
        "queue-depth preservation poll missing",
    )

    ipc_syscalls = [receipt for receipt in syscalls if receipt["SYSCALL_NUMBER"] in {"13", "14", "15", "16"}]
    require(ipc_syscalls, "IPC syscall receipts missing")
    require(all(receipt["ABI_VERSION"] == "2" for receipt in ipc_syscalls), "IPC escaped ABI v2 receipts")
    require(all(receipt["MUTATED_TRUSTED_STATE"] == "false" for receipt in ipc_syscalls if receipt["STATUS"] == "rejected"), "rejected IPC syscall mutation claim")
    require(len(invariants) == 1, "expected exactly one IPC invariant receipt")
    invariant = invariants[0]
    for key in [
        "KERNEL_MEDIATED",
        "POINTER_VALIDATION_ENFORCED",
        "QUEUE_BOUNDS_ENFORCED",
        "V31_ISOLATION_PRESERVED",
        "V33_SYSCALL_ABI_PRESERVED",
    ]:
        require(invariant[key] == "true", f"IPC invariant failed: {key}")
    require(invariant["SHARED_MEMORY_USED"] == "false", "IPC used shared memory")
    require(invariant["REJECTED_IPC_MUTATED_STATE"] == "false", "IPC invariant reports rejected mutation")

    require(isolation and isolation[-1]["PROCESS_ISOLATION_ENFORCED"] == "true", "v31 isolation evidence missing")
    require("/apps/dynamic_hello.bogapp" in load_by_path, "v32 loader evidence missing")
    require(any(receipt["APP_PATH"] == paths["sender"] and receipt["SYSCALL"] == "yield" for receipt in syscalls), "sender yield missing")
    for pid, role in [(sender_pid, "sender"), (receiver_pid, "receiver")]:
        require(any(receipt["PID"] == pid for receipt in preempts), f"IPC {role} preemption evidence missing")
    require(all(marker in serial for marker in ["\nA1\n", "\nB1\n", "\nA2\n", "\nB2\n"]), "v30 preemption proof missing")
    require(len(v30["qemu_serial_receipt_hash"]) == 64, "serial hash missing")
    require(len(v30["bogfs_image_hash"]) == 64, "BogFS hash missing")

    receipt = {
        "milestone": "v34.0.0-verified-ipc",
        "platform": "qemu",
        "ipc_abi_version": 1,
        "syscall_numbers": {
            "13": "ipc_register_channel",
            "14": "ipc_send",
            "15": "ipc_recv",
            "16": "ipc_poll",
        },
        "channel_count": len(accepted_channels),
        "accepted_send_count": len([receipt for receipt in sends if receipt["STATUS"] == "accepted"]),
        "accepted_recv_count": len([receipt for receipt in recvs if receipt["STATUS"] == "accepted"]),
        "rejected_ipc_cases": rejected_sends + rejected_recvs + rejected_polls,
        "rejected_ipc_mutated_state": False,
        "rejected_recv_preserved_messages": True,
        "shared_memory_used": False,
        "payload_hash_match": True,
        "queue_bounds_enforced": True,
        "pointer_validation_enforced": True,
        "v31_isolation_preserved": True,
        "v32_loader_preserved": True,
        "v33_syscall_abi_preserved": True,
        "v30_preemption_preserved": True,
        "qemu_only_boundary": True,
        "serial_log_hash": v30["qemu_serial_receipt_hash"],
        "initrd_or_bogfs_hash": v30["bogfs_image_hash"],
        "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_status": "completed",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v34 Verified IPC PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v34 Verified IPC evaluator FAILED: {exc}")
        sys.exit(1)
