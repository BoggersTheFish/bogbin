import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from make_v39_disk_apps_image import make_image
from make_v38_file_lifecycle_image import SECTOR_SIZE, SUPERBLOCK_A


ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS = ROOT / "artifacts"
BASE_IMAGE = ARTIFACTS / "bogos_v39_disk_apps_base.img"
BOOT1_LOG = ARTIFACTS / "bogos_v39_disk_apps_boot1_serial.log"
BOOT2_LOG = ARTIFACTS / "bogos_v39_disk_apps_boot2_serial.log"
RECEIPT_PATH = ARTIFACTS / "bogos_v39_disk_apps_receipt.json"


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


def run_qemu(kernel_path, image, serial_log):
    if serial_log.exists():
        serial_log.unlink()
    process = subprocess.Popen([
        "qemu-system-i386", "-kernel", str(kernel_path), "-serial", f"file:{serial_log}",
        "-display", "none", "-no-reboot", "-no-shutdown",
        "-drive", f"file={image},format=raw,if=ide,index=0,media=disk",
    ])
    output = ""
    deadline = time.time() + 30
    while time.time() < deadline:
        if serial_log.exists():
            output = serial_log.read_text(errors="replace")
            if "BOGOS_V39_INVARIANTS_END" in output:
                break
        time.sleep(0.1)
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    require("BOGOS_V39_INVARIANTS_END" in output, f"v39 QEMU scenario did not complete: {serial_log}")
    return output


def boot_evidence(output):
    loads = parse_receipts(output, "BOGOS_V39_LOAD_BEGIN", "BOGOS_V39_LOAD_END")
    admits = parse_receipts(output, "BOGOS_V39_ADMIT_BEGIN", "BOGOS_V39_ADMIT_END")
    executions = parse_receipts(output, "BOGOS_V39_EXECUTION_BEGIN", "BOGOS_V39_EXECUTION_END")
    processes = parse_receipts(output, "BOGOS_PROCESS_BEGIN", "BOGOS_PROCESS_END")
    valid = next(load for load in loads if load["APP_PATH"] == "/apps/hello.bogapp" and load["STATUS"] == "verified")
    admit = next(admit for admit in admits if admit["STATUS"] == "accepted")
    execution = next(receipt for receipt in executions if receipt["APP_PATH"] == "/apps/hello.bogapp")
    process = next(receipt for receipt in processes if receipt.get("PID") == admit["PID"] and receipt.get("STATE_EXITED") == "true")
    return loads, valid, admit, execution, process


def main():
    for tool in ["cargo", "qemu-system-i386"]:
        require(shutil.which(tool), f"{tool} not found in PATH")
    require((ROOT / "README.md").read_text().startswith("# BOGBIN v39.0.0"), "README is not v39.0.0")
    require("Current release: v39.0.0" in (ROOT / "PROJECT_STATUS.md").read_text(), "PROJECT_STATUS is not v39.0.0")
    require("## v39.0.0: Persistent Disk-Loaded Apps" in (ROOT / "RELEASE_NOTES.md").read_text(), "v39 release notes missing")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    metadata = make_image(BASE_IMAGE)
    result = subprocess.run(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR, capture_output=True, text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    kernel_path = KERNEL_DIR / "target/i686-unknown-linux-musl/debug/bogk-kernel"

    boot1 = run_qemu(kernel_path, BASE_IMAGE, BOOT1_LOG)
    boot2 = run_qemu(kernel_path, BASE_IMAGE, BOOT2_LOG)
    loads1, valid1, admit1, execution1, process1 = boot_evidence(boot1)
    loads2, valid2, admit2, execution2, process2 = boot_evidence(boot2)

    for valid, admit, execution, process in [(valid1, admit1, execution1, process1), (valid2, admit2, execution2, process2)]:
        require(valid["FILE_HASH"] == metadata["fixtures"]["/apps/hello.bogapp"]["file_sha256"], "BogFS app file hash mismatch")
        require(valid["APP_MANIFEST_HASH"] != "none" and valid["CODE_HASH"] != "none", "internal app hashes missing")
        require(valid["ABI_VERSION"] == "2" and valid["CAPABILITIES"] == "0", "app ABI/capability admission mismatch")
        require(valid["PID"] == "none" and valid["SCHEDULER_ADMITTED"] == "false", "PID allocated before verification")
        require(admit["PID"] != "none" and admit["SCHEDULER_ADMITTED"] == "true", "verified app not scheduled")
        require(admit["PROCESS_ISOLATION_ENFORCED"] == "true" and admit["USER_CODE_WRITABLE"] == "false", "isolated mapping missing")
        require(admit["FILESYSTEM_ROOT_HASH"] == valid["FILESYSTEM_ROOT_HASH"], "admission root mismatch")
        require(admit["FILE_HASH"] == valid["FILE_HASH"], "admission file hash mismatch")
        require(admit["APP_MANIFEST_HASH"] == valid["APP_MANIFEST_HASH"], "admission manifest hash mismatch")
        require(admit["CODE_HASH"] == valid["CODE_HASH"], "admission code hash mismatch")
        require(execution["PID"] == admit["PID"] and execution["RING3"] == "true", "Ring 3 execution evidence missing")
        require(execution["STATE_EXITED"] == "true" and execution["EXECUTION_STATUS"] == "completed", "disk app did not exit")
        require(process["APP_PATH"] == "/apps/hello.bogapp", "process record app path mismatch")

    require(valid1["FILESYSTEM_ROOT_HASH"] == valid2["FILESYSTEM_ROOT_HASH"], "persistent root changed across clean boots")
    require(valid1["FILE_HASH"] == valid2["FILE_HASH"], "persistent app file changed across clean boots")
    require(valid1["APP_MANIFEST_HASH"] == valid2["APP_MANIFEST_HASH"], "app manifest changed across clean boots")
    require(valid1["CODE_HASH"] == valid2["CODE_HASH"], "app code changed across clean boots")

    rejected = [load for load in loads1 if load["STATUS"] == "rejected"]
    reasons = {load["REJECT_REASON"] for load in rejected}
    expected = {
        "bad_magic", "code_hash_mismatch", "unsupported_capabilities", "missing_app_file",
        "app_path_outside_apps", "invalid_app_path", "stale_source_root", "stale_source_version",
        "stale_source_preimage", "protected_path_mutation", "truncated_manifest",
        "unsupported_app_version", "manifest_hash_mismatch", "entrypoint_out_of_range",
        "oversized_code", "unsupported_abi_version",
    }
    require(expected <= reasons, "v39 rejection matrix incomplete")
    require(all(load["PID"] == "none" and load["PROCESS_RECORD_ALLOCATED"] == "false" and load["SCHEDULER_ADMITTED"] == "false" for load in rejected), "rejected app received admission state")

    corruptions = {}
    with tempfile.TemporaryDirectory(prefix="bogos-v39-") as temp:
        root_image = Path(temp) / "corrupt-root.img"
        root_bytes = bytearray(BASE_IMAGE.read_bytes())
        root_bytes[SUPERBLOCK_A * SECTOR_SIZE + 56] ^= 1
        root_image.write_bytes(root_bytes)
        root_output = run_qemu(kernel_path, root_image, Path(temp) / "corrupt-root.log")
        corruptions["corrupt_root"] = parse_receipts(root_output, "BOGOS_V39_LOAD_BEGIN", "BOGOS_V39_LOAD_END")[0]

        app_image = Path(temp) / "corrupt-app-data.img"
        app_bytes = bytearray(BASE_IMAGE.read_bytes())
        hello_lba = metadata["fixtures"]["/apps/hello.bogapp"]["lba"]
        app_bytes[hello_lba * SECTOR_SIZE + 160] ^= 1
        app_image.write_bytes(app_bytes)
        app_output = run_qemu(kernel_path, app_image, Path(temp) / "corrupt-app.log")
        corruptions["corrupt_app_file_data"] = parse_receipts(app_output, "BOGOS_V39_LOAD_BEGIN", "BOGOS_V39_LOAD_END")[0]
    require(all(item["STATUS"] == "rejected" and item["REJECT_REASON"] == "no_valid_root" for item in corruptions.values()), "corrupt root/app data did not fail closed")

    receipt = {
        "format": "BOGOS-v39-disk-loaded-apps-receipt-1.0",
        "milestone": "v39.0.0-persistent-disk-loaded-apps",
        "execution_status": "completed",
        "platform": "qemu-i686",
        "claim": "verified .bogapp v2 loaded from persistent BogFS into isolated Ring 3",
        "image_sha256": hashlib.sha256(BASE_IMAGE.read_bytes()).hexdigest(),
        "image_metadata": metadata,
        "boot1_valid_load": valid1,
        "boot1_admission": admit1,
        "boot1_execution": execution1,
        "boot2_valid_load": valid2,
        "boot2_admission": admit2,
        "boot2_execution": execution2,
        "rejected_loads": rejected,
        "corruption_evidence": corruptions,
        "two_boot_disk_app_persistence_proven": True,
        "rejected_apps_allocated_pid": False,
        "rejected_apps_scheduler_admitted": False,
        "full_elf": False,
        "dynamic_libraries": False,
        "v40_shell": False,
        "boot1_serial_sha256": hashlib.sha256(BOOT1_LOG.read_bytes()).hexdigest(),
        "boot2_serial_sha256": hashlib.sha256(BOOT2_LOG.read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v39 Persistent Disk-Loaded Apps PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v39 Persistent Disk-Loaded Apps evaluator FAILED: {exc}")
        sys.exit(1)
