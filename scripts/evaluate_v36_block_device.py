import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS = ROOT / "artifacts"
BASE_IMAGE = ARTIFACTS / "bogos_v36_block_base.img"
WRITTEN_IMAGE = ARTIFACTS / "bogos_v36_block_written.img"
SERIAL_LOG = ARTIFACTS / "bogos_v36_block_device_serial.log"
NO_DEVICE_SERIAL_LOG = ARTIFACTS / "bogos_v36_no_device_serial.log"
RECEIPT_PATH = ARTIFACTS / "bogos_v36_block_device_receipt.json"
SECTOR_SIZE = 512


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sector(label):
    data = label.encode("ascii") + b"\n"
    return data + bytes(SECTOR_SIZE - len(data))


def sector_bytes(path, lba):
    with path.open("rb") as handle:
        handle.seek(lba * SECTOR_SIZE)
        return handle.read(SECTOR_SIZE)


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


def run_qemu(kernel_path, serial_log, image=None):
    if serial_log.exists():
        serial_log.unlink()
    cmd = [
        "qemu-system-i386",
        "-kernel",
        str(kernel_path),
        "-serial",
        f"file:{serial_log}",
        "-display",
        "none",
        "-no-reboot",
        "-no-shutdown",
    ]
    if image is not None:
        cmd.extend(["-drive", f"file={image},format=raw,if=ide,index=0,media=disk"])
    process = subprocess.Popen(cmd)
    output = ""
    deadline = time.time() + 15
    while time.time() < deadline:
        if serial_log.exists():
            output = serial_log.read_text(errors="replace")
            if "BOGOS_BLOCK_INVARIANTS_END" in output:
                break
        time.sleep(0.1)
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    require("BOGOS_BLOCK_INVARIANTS_END" in output, f"v36 QEMU scenario did not complete: {serial_log}")
    return output


def main():
    for tool in ["cargo", "qemu-system-i386"]:
        require(shutil.which(tool) is not None, f"{tool} not found in PATH")

    readme = (ROOT / "README.md").read_text()
    status = (ROOT / "PROJECT_STATUS.md").read_text()
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text()
    docs = (ROOT / "docs/v36_block_device_plan.md").read_text()
    require(readme.startswith(("# BOGBIN v36.0.0", "# BOGBIN v37.0.0", "# BOGBIN v38.0.0", "# BOGBIN v39.0.0")), "README does not claim v36 or later")
    require(any(marker in status for marker in ["Current release: v36.0.0", "Current release: v37.0.0", "Current release: v38.0.0", "Current release: v39.0.0"]), "PROJECT_STATUS does not claim v36 or later")
    require("## v36.0.0: Verified Block Device Model" in release_notes, "v36 release notes missing")
    for marker in ["ATA PIO", "Negative Matrix", "Explicit Non-Goals", "not a filesystem"]:
        require(marker in docs, f"v36 documentation marker missing: {marker}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["python3", str(ROOT / "scripts/make_v36_block_image.py"), str(BASE_IMAGE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    shutil.copyfile(BASE_IMAGE, WRITTEN_IMAGE)

    result = subprocess.run(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    kernel_path = KERNEL_DIR / "target/i686-unknown-linux-musl/debug/bogk-kernel"

    base_hash = sha256(BASE_IMAGE.read_bytes())
    base_protected_hash = sha256(sector_bytes(BASE_IMAGE, 0))
    base_write_hash = sha256(sector_bytes(BASE_IMAGE, 65))
    output = run_qemu(kernel_path, SERIAL_LOG, WRITTEN_IMAGE)
    no_device_output = run_qemu(kernel_path, NO_DEVICE_SERIAL_LOG)

    devices = parse_receipts(output, "BOGOS_BLOCK_DEVICE_BEGIN", "BOGOS_BLOCK_DEVICE_END")
    reads = parse_receipts(output, "BOGOS_BLOCK_READ_BEGIN", "BOGOS_BLOCK_READ_END")
    writes = parse_receipts(output, "BOGOS_BLOCK_WRITE_BEGIN", "BOGOS_BLOCK_WRITE_END")
    operations = parse_receipts(output, "BOGOS_BLOCK_OPERATION_BEGIN", "BOGOS_BLOCK_OPERATION_END")
    invariants = parse_receipts(output, "BOGOS_BLOCK_INVARIANTS_BEGIN", "BOGOS_BLOCK_INVARIANTS_END")
    no_devices = parse_receipts(no_device_output, "BOGOS_BLOCK_DEVICE_BEGIN", "BOGOS_BLOCK_DEVICE_END")
    no_device_reads = parse_receipts(no_device_output, "BOGOS_BLOCK_READ_BEGIN", "BOGOS_BLOCK_READ_END")

    require(len(devices) == 1 and devices[0]["STATUS"] == "accepted", "attached ATA device was not admitted")
    require(devices[0]["MODEL"] == "qemu_legacy_ide_ata_pio", "unexpected device model")
    require(devices[0]["SECTOR_SIZE"] == "512" and devices[0]["SECTOR_COUNT"] == "8192", "device bounds mismatch")
    require(len(no_devices) == 1 and no_devices[0]["REJECT_REASON"] == "device_absent", "no-device rejection missing")
    require(no_device_reads and no_device_reads[0]["REJECT_REASON"] == "device_absent", "no-device read evidence missing")

    read_hash = sha256(sector("BOGOS-V36-VERIFIED-READ-SECTOR"))
    after_hash = sha256(sector("BOGOS-V36-WRITE-AFTER"))
    accepted_read = next(r for r in reads if r["LBA"] == "64" and r["STATUS"] == "accepted")
    require(accepted_read["EXPECTED_HASH"] == accepted_read["OBSERVED_HASH"] == read_hash, "verified read hash mismatch")

    read_reasons = {r["REJECT_REASON"] for r in reads if r["STATUS"] == "rejected"}
    require(
        {"lba_out_of_range", "unsupported_sector_count", "invalid_buffer_length", "sector_hash_mismatch"} <= read_reasons,
        "read rejection matrix incomplete",
    )
    write_reasons = {r["REJECT_REASON"] for r in writes if r["STATUS"] == "rejected"}
    require(
        {"protected_lba", "invalid_buffer_length", "stale_preimage", "write_hash_mismatch", "readback_hash_mismatch"} <= write_reasons,
        "write rejection matrix incomplete",
    )
    require(all(r["MUTATED_TRUSTED_STATE"] == "false" for r in reads if r["STATUS"] == "rejected"), "rejected read mutated trusted state")
    require(all(r["MUTATED_TRUSTED_STATE"] == "false" for r in writes if r["STATUS"] == "rejected"), "rejected write mutated trusted state")
    pre_io_rejections = [r for r in writes if r["STATUS"] == "rejected" and r["REJECT_REASON"] != "readback_hash_mismatch"]
    require(all(r["DEVICE_MAY_HAVE_CHANGED"] == "false" for r in pre_io_rejections), "pre-I/O rejection may have changed device")
    readback_failure = next(r for r in writes if r["REJECT_REASON"] == "readback_hash_mismatch")
    require(readback_failure["DEVICE_MAY_HAVE_CHANGED"] == "true", "read-back failure did not expose possible device mutation")
    require(readback_failure["MUTATED_TRUSTED_STATE"] == "false", "read-back failure admitted unverified trusted state")

    accepted_write = next(r for r in writes if r["STATUS"] == "accepted")
    require(accepted_write["LBA"] == "65", "accepted write used wrong LBA")
    require(accepted_write["BEFORE_HASH"] == base_write_hash, "accepted write preimage mismatch")
    require(accepted_write["REQUESTED_AFTER_HASH"] == accepted_write["READBACK_HASH"] == after_hash, "accepted write read-back mismatch")
    require(accepted_write["MUTATED_TRUSTED_STATE"] == "true", "accepted verified write did not mutate trusted state")

    require(sha256(sector_bytes(WRITTEN_IMAGE, 65)) == after_hash, "written image sector does not match accepted receipt")
    require(sha256(sector_bytes(WRITTEN_IMAGE, 0)) == base_protected_hash, "protected sector changed")
    require(any(r["REJECT_REASON"] == "unsupported_operation" for r in operations), "unsupported operation rejection missing")
    require(len(invariants) == 1, "expected one attached-device invariant receipt")
    invariant = invariants[0]
    for key in [
        "QEMU_ONLY",
        "ATA_PIO_ONLY",
        "ONE_DEVICE_ONLY",
        "SINGLE_SECTOR_ONLY",
        "BOUNDS_ENFORCED",
        "PROTECTED_RANGE_ENFORCED",
        "SECTOR_SHA256_VERIFIED",
        "WRITE_READBACK_VERIFIED",
        "V35_IN_MEMORY_BOGFS_PRESERVED",
    ]:
        require(invariant[key] == "true", f"v36 invariant failed: {key}")
    require(invariant["RAW_USER_BLOCK_ACCESS"] == "false", "v36 exposed raw user block access")
    require(invariant["FILESYSTEM_IMPLEMENTED"] == "false", "v36 claims a filesystem")
    require(invariant["REJECTED_OPERATIONS_MUTATED_TRUSTED_STATE"] == "false", "v36 invariant claims rejected mutation")

    receipt = {
        "format": "BOGOS-v36-verified-block-device-receipt-1.0",
        "milestone": "v36.0.0-verified-block-device-model",
        "execution_status": "completed",
        "platform": "qemu-i686",
        "device_model": "legacy-ide-ata-pio",
        "sector_size": 512,
        "sector_count": 8192,
        "writable_lba_range": [64, 127],
        "base_image_hash": base_hash,
        "written_image_hash": sha256(WRITTEN_IMAGE.read_bytes()),
        "accepted_read": accepted_read,
        "accepted_write": accepted_write,
        "rejected_reads": [r for r in reads if r["STATUS"] == "rejected"],
        "rejected_writes": [r for r in writes if r["STATUS"] == "rejected"],
        "unsupported_operations": operations,
        "no_device_evidence": no_devices[0],
        "rejected_operations_mutated_trusted_state": False,
        "filesystem_implemented": False,
        "raw_user_block_access": False,
        "v35_in_memory_bogfs_preserved": True,
        "serial_log_hash": sha256(SERIAL_LOG.read_bytes()),
        "no_device_serial_log_hash": sha256(NO_DEVICE_SERIAL_LOG.read_bytes()),
        "evaluator_hash": sha256(Path(__file__).read_bytes()),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v36 Verified Block Device Model PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v36 Verified Block Device Model evaluator FAILED: {exc}")
        sys.exit(1)
