import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "bogos_v33_syscall_abi_receipt.json"
AUDIT_RECEIPT_PATH = ARTIFACTS / "bogos_v33_syscall_abi_audit_receipt.json"


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
        (ROOT / "README.md").read_text().startswith(("# BOGBIN v33.0.0", "# BOGBIN v34.0.0")),
        "README does not claim v33 or a later release",
    )
    require(
        any(
            marker in (ROOT / "PROJECT_STATUS.md").read_text()
            for marker in ["Current release: v33.0.0", "Current release: v34.0.0"]
        ),
        "PROJECT_STATUS does not claim v33 or a later release",
    )
    require(
        "## v33.0.0: Syscall ABI v2" in (ROOT / "RELEASE_NOTES.md").read_text(),
        "v33 release notes missing",
    )
    docs = (ROOT / "docs/v33_syscall_abi_v2.md").read_text()
    for marker in ["Register ABI", "Pointer Validation", "Supported ABI v2 Syscalls", "QEMU-only"]:
        require(marker in docs, f"v33 documentation marker missing: {marker}")

    result = subprocess.run(
        ["python3", str(ROOT / "scripts/evaluate_v32_dynamic_loader.py")],
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
    syscalls = parse_receipts(serial, "BOGOS_SYSCALL_BEGIN", "BOGOS_SYSCALL_END")
    outputs = parse_receipts(serial, "BOGOS_USER_OUTPUT_BEGIN", "BOGOS_USER_OUTPUT_END")
    verifies = parse_receipts(serial, "BOGOS_VERIFY_HASH_BEGIN", "BOGOS_VERIFY_HASH_END")
    claims = parse_receipts(serial, "BOGOS_CLAIM_BEGIN", "BOGOS_CLAIM_END")
    saves = parse_receipts(serial, "BOGOS_CONTEXT_SAVE_BEGIN", "BOGOS_CONTEXT_SAVE_END")
    restores = parse_receipts(serial, "BOGOS_CONTEXT_RESTORE_BEGIN", "BOGOS_CONTEXT_RESTORE_END")
    preempts = parse_receipts(serial, "BOGOS_PREEMPT_BEGIN", "BOGOS_PREEMPT_END")
    address_spaces = parse_receipts(serial, "BOGOS_ADDRSPACE_BEGIN", "BOGOS_ADDRSPACE_END")
    isolation = parse_receipts(serial, "BOGOS_PROCESS_ISOLATION_BEGIN", "BOGOS_PROCESS_ISOLATION_END")
    invariants = parse_receipts(
        serial, "BOGOS_SYSCALL_INVARIANTS_BEGIN", "BOGOS_SYSCALL_INVARIANTS_END"
    )

    load_by_path = {receipt["APP_PATH"]: receipt for receipt in loads}
    admit_by_path = {receipt["APP_PATH"]: receipt for receipt in admits}
    latest_process = {receipt["APP_PATH"]: receipt for receipt in processes}
    v33_paths = [
        "/apps/v33_syscall_write.bogapp",
        "/apps/v33_syscall_verify.bogapp",
        "/apps/v33_syscall_claim.bogapp",
        "/apps/v33_bad_syscall_kernel_ptr.bogapp",
        "/apps/v33_bad_syscall_cross_process_ptr.bogapp",
        "/apps/v33_bad_syscall_overflow_ptr.bogapp",
        "/apps/v33_audit_lengths.bogapp",
        "/apps/v33_audit_ranges.bogapp",
        "/apps/v33_audit_misc.bogapp",
    ]
    for path in v33_paths:
        require(load_by_path[path]["APP_ACCEPTED"] == "true", f"v32 loader rejected {path}")
        require(load_by_path[path]["PID"] != "none", f"v32 loader omitted PID for {path}")
        require(admit_by_path[path]["PROCESS_ISOLATION_ENFORCED"] == "true", f"no isolation admit: {path}")
        require(admit_by_path[path]["ADMISSION_SOURCE"] == "dynamic_loader", f"wrong source: {path}")
        require(latest_process[path]["STATE_EXITED"] == "true", f"v33 app did not exit: {path}")
        require(latest_process[path]["STATE_BLOCKED"] == "false", f"v33 app was blocked: {path}")

    syscall_by_path = {}
    for receipt in syscalls:
        syscall_by_path.setdefault(receipt.get("APP_PATH"), []).append(receipt)
        required_fields = {
            "PID",
            "APP_PATH",
            "SYSCALL",
            "SYSCALL_NUMBER",
            "ARG0",
            "ARG1",
            "ARG2",
            "ARG3",
            "ARGS_HASH",
            "RESULT",
            "STATUS",
            "REJECT_REASON",
            "MUTATED_TRUSTED_STATE",
            "ABI_VERSION",
        }
        require(required_fields <= receipt.keys(), f"incomplete syscall receipt: {receipt}")
        require(receipt["ABI_VERSION"] == "2", "non-v2 syscall receipt found")
        require(len(receipt["ARGS_HASH"]) == 64, "syscall args hash missing")
        if receipt["STATUS"] == "rejected":
            require(receipt["REJECT_REASON"] != "none", "rejected syscall lacks reason")
            require(
                receipt["MUTATED_TRUSTED_STATE"] == "false",
                "rejected syscall reports trusted-state mutation",
            )
        else:
            require(receipt["REJECT_REASON"] == "none", "accepted syscall has rejection reason")

    write_path = v33_paths[0]
    write_pid = load_by_path[write_path]["PID"]
    write_calls = syscall_by_path[write_path]
    getpid = next(receipt for receipt in write_calls if receipt["SYSCALL"] == "getpid")
    require(getpid["RESULT"] == write_pid, "sys_getpid did not return the current PID")
    require(
        any(receipt["SYSCALL"] == "process_info" and receipt["STATUS"] == "accepted" for receipt in write_calls),
        "valid sys_process_info evidence missing",
    )
    write_outputs = [receipt for receipt in outputs if receipt["PID"] == write_pid]
    require(len(write_outputs) == 2, "sys_write_console did not emit two controlled outputs")
    require(
        [receipt["OUTPUT_PREVIEW"] for receipt in write_outputs]
        == ["hex:5633332d4f4e450a", "hex:5633332d54574f0a"],
        "kernel-controlled output changed",
    )
    require(any(receipt["PID"] == write_pid for receipt in saves), "sys_yield context save missing")
    require(any(receipt["PID"] == write_pid for receipt in restores), "sys_yield context restore missing")
    require(any(receipt["SYSCALL"] == "exit" for receipt in write_calls), "sys_exit receipt missing")

    verify_path = v33_paths[1]
    verify_pid = load_by_path[verify_path]["PID"]
    verify_cases = [receipt for receipt in verifies if receipt["PID"] == verify_pid]
    require({receipt["HASH_MATCH"] for receipt in verify_cases} == {"true", "false"}, "verify cases missing")
    claim_path = v33_paths[2]
    claim_pid = load_by_path[claim_path]["PID"]
    claim_cases = [receipt for receipt in claims if receipt["PID"] == claim_pid]
    require(len(claim_cases) == 1 and claim_cases[0]["CLAIM_ACCEPTED"] == "true", "claim missing")

    expected_rejections = {
        v33_paths[3]: ("write_console", "-2", "invalid_pointer"),
        v33_paths[4]: ("write_console", "-2", "invalid_pointer"),
        v33_paths[5]: ("write_console", "-2", "invalid_pointer"),
    }
    rejected_evidence = []
    for path, (name, error, reason) in expected_rejections.items():
        rejected = [
            receipt
            for receipt in syscall_by_path[path]
            if receipt["STATUS"] == "rejected" and receipt["SYSCALL"] == name
        ]
        require(len(rejected) == 1, f"missing rejected syscall evidence: {path}")
        require(rejected[0]["RESULT"] == error, f"wrong error result: {path}")
        require(rejected[0]["REJECT_REASON"] == reason, f"wrong rejection reason: {path}")
        require(
            not any(receipt.get("APP_PATH") == path for receipt in outputs),
            f"rejected syscall emitted output: {path}",
        )
        rejected_evidence.append(rejected[0])

    length_path = "/apps/v33_audit_lengths.bogapp"
    length_calls = syscall_by_path[length_path]
    require(
        any(r["SYSCALL"] == "write_console" and r["ARG1"] == "00000000" and r["RESULT"] == "-3" for r in length_calls),
        "zero-length write_console was not rejected",
    )
    require(
        any(r["SYSCALL"] == "write_console" and r["ARG1"] == "00000100" and r["RESULT"] == "256" for r in length_calls),
        "maximum write_console was not accepted",
    )
    require(
        any(r["SYSCALL"] == "write_console" and r["ARG1"] == "00000101" and r["RESULT"] == "-3" for r in length_calls),
        "over-maximum write_console was not rejected",
    )
    require(
        any(r["APP_PATH"] == length_path and r["OUTPUT_LENGTH"] == "256" for r in outputs),
        "maximum write_console output receipt missing",
    )

    ranges_path = "/apps/v33_audit_ranges.bogapp"
    range_calls = syscall_by_path[ranges_path]
    require(
        any(r["SYSCALL"] == "write_console" and r["ARG1"] == "00000001" and r["RESULT"] == "1" for r in range_calls),
        "last-byte user pointer was not accepted",
    )
    require(
        any(r["SYSCALL"] == "write_console" and r["ARG1"] == "00000002" and r["RESULT"] == "-2" for r in range_calls),
        "range crossing into unmapped/supervisor page was accepted",
    )
    require(
        any(r["SYSCALL"] == "process_info" and r["STATUS"] == "rejected" for r in range_calls),
        "cross-page writable output was accepted",
    )
    require(
        any(r["SYSCALL"] == "process_info" and r["STATUS"] == "accepted" for r in range_calls),
        "valid writable process_info target was rejected",
    )

    misc_path = "/apps/v33_audit_misc.bogapp"
    misc_calls = syscall_by_path[misc_path]
    misc_expected = [
        ("verify_hash", "-2", "invalid_pointer"),
        ("claim", "-3", "invalid_length"),
        ("unknown", "-1", "invalid_syscall"),
        ("legacy_emit_receipt", "-1", "legacy_syscall_denied"),
    ]
    for name, result_value, reason in misc_expected:
        require(
            any(
                r["SYSCALL"] == name
                and r["RESULT"] == result_value
                and r["REJECT_REASON"] == reason
                for r in misc_calls
            ),
            f"missing hardened syscall case: {name}/{reason}",
        )
    require(
        {r["SYSCALL_NUMBER"] for r in misc_calls if r["SYSCALL"] == "unknown"} == {"0", "255"},
        "invalid syscall 0/255 evidence missing",
    )
    require(
        any(r["PID"] == "none" and r["CLAIM_ACCEPTED"] == "false" for r in claims),
        "oversized rejected claim receipt missing",
    )

    require(len(invariants) == 1, "expected exactly one syscall-invariant receipt")
    invariant = invariants[0]
    for key in [
        "ACTIVE_CR3_MATCHES_PROCESS",
        "POINTER_VALIDATION_ENFORCED",
        "LENGTH_BOUNDS_ENFORCED",
        "OVERFLOW_REJECTED",
        "KERNEL_POINTER_REJECTED",
        "CROSS_PROCESS_POINTER_REJECTED",
        "CODE_WRITE_REJECTED",
    ]:
        require(invariant[key] == "true", f"syscall invariant failed: {key}")
    require(invariant["ABI_VERSION"] == "2", "wrong invariant ABI version")
    require(
        invariant["REJECTED_SYSCALLS_MUTATED_STATE"] == "false",
        "invariant claims rejected syscall mutation",
    )

    v33_pids = {load_by_path[path]["PID"] for path in v33_paths}
    isolated_pids = {
        receipt["PID"]
        for receipt in address_spaces
        if receipt.get("PROCESS_ISOLATION_ENFORCED") == "true"
    }
    require(v33_pids <= isolated_pids, "v33 apps lack private v31 address-space evidence")
    require(isolation and isolation[-1]["PROCESS_ISOLATION_ENFORCED"] == "true", "v31 proof missing")
    require("/apps/dynamic_hello.bogapp" in load_by_path, "v32 dynamic loader evidence missing")
    require(load_by_path["/apps/dynamic_hello.bogapp"]["APP_ACCEPTED"] == "true", "v32 loader regressed")
    require(any(receipt["PID"] == verify_pid for receipt in preempts), "v33 preemption evidence missing")
    require(all(marker in serial for marker in ["\nA1\n", "\nB1\n", "\nA2\n", "\nB2\n"]), "v30 proof missing")
    require(len(v30["qemu_serial_receipt_hash"]) == 64, "serial hash missing")
    require(len(v30["bogfs_image_hash"]) == 64, "BogFS hash missing")

    receipt = {
        "milestone": "v33.0.0-syscall-abi-v2",
        "platform": "qemu",
        "syscall_abi_version": 2,
        "supported_syscalls": {
            "6": "exit",
            "7": "yield",
            "8": "write_console",
            "9": "getpid",
            "10": "process_info",
            "11": "verify_hash",
            "12": "claim",
        },
        "valid_syscall_cases": {
            "getpid": getpid,
            "user_outputs": write_outputs,
            "verify_hash": verify_cases,
            "claim": claim_cases,
        },
        "rejected_syscall_cases": rejected_evidence,
        "rejected_syscalls_mutated_trusted_state": False,
        "syscall_receipt_count": len([r for r in syscalls if r.get("PID") in v33_pids]),
        "user_output_receipt_count": len(write_outputs),
        "hash_verification_cases": len(verify_cases),
        "claim_cases": len(claim_cases),
        "v31_isolation_preserved": True,
        "v32_loader_preserved": True,
        "v30_preemption_preserved": True,
        "qemu_only_boundary": True,
        "serial_log_hash": v30["qemu_serial_receipt_hash"],
        "initrd_or_bogfs_hash": v30["bogfs_image_hash"],
        "evaluator_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_status": "completed",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    audit_receipt = {
        "milestone": "v33.1-syscall-abi-hardening-audit",
        "release_under_audit": "v33.0.0",
        "syscall_abi_version": 2,
        "supported_syscalls": receipt["supported_syscalls"],
        "accepted_syscall_cases": [
            r for r in syscalls if r.get("PID") in v33_pids and r["STATUS"] == "accepted"
        ],
        "rejected_syscall_cases": [
            r for r in syscalls if r.get("PID") in v33_pids and r["STATUS"] == "rejected"
        ],
        "pointer_negative_cases": [
            r
            for r in syscalls
            if r.get("PID") in v33_pids
            and r["REJECT_REASON"] in {"invalid_pointer", "permission_denied"}
        ],
        "overflow_rejected": True,
        "rejected_syscalls_mutated_state": False,
        "syscall_invariants_passed": True,
        "v31_isolation_preserved": True,
        "v32_loader_preserved": True,
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
    print("v33 Syscall ABI v2 PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v33 Syscall ABI evaluator FAILED: {exc}")
        sys.exit(1)
