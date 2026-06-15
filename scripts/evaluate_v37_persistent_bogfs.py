import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from make_v37_bogfs_image import (
    MANIFEST_B,
    MANIFEST_SECTORS,
    SECTOR_SIZE,
    SUPERBLOCK_A,
    SUPERBLOCK_B,
    make_image,
    root_hash,
)


ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS = ROOT / "artifacts"
BASE_IMAGE = ARTIFACTS / "bogos_v37_persistent_bogfs_base.img"
WRITTEN_IMAGE = ARTIFACTS / "bogos_v37_persistent_bogfs_written.img"
BOOT1_LOG = ARTIFACTS / "bogos_v37_persistent_bogfs_boot1_serial.log"
BOOT2_LOG = ARTIFACTS / "bogos_v37_persistent_bogfs_boot2_serial.log"
RECEIPT_PATH = ARTIFACTS / "bogos_v37_persistent_bogfs_receipt.json"
COMMITTED_DATA = b"V37-PERSISTED-DATA"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(data):
    return hashlib.sha256(data).digest()


def sha256_hex(data):
    return sha256(data).hex()


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
    process = subprocess.Popen(
        [
            "qemu-system-i386",
            "-kernel",
            str(kernel_path),
            "-serial",
            f"file:{serial_log}",
            "-display",
            "none",
            "-no-reboot",
            "-no-shutdown",
            "-drive",
            f"file={image},format=raw,if=ide,index=0,media=disk",
        ]
    )
    output = ""
    deadline = time.time() + 15
    while time.time() < deadline:
        if serial_log.exists():
            output = serial_log.read_text(errors="replace")
            if "BOGOS_PERSISTENT_BOGFS_INVARIANTS_END" in output:
                break
        time.sleep(0.1)
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    require("BOGOS_PERSISTENT_BOGFS_INVARIANTS_END" in output, f"v37 QEMU scenario did not complete: {serial_log}")
    return output


def sector(image, lba):
    start = lba * SECTOR_SIZE
    return image[start : start + SECTOR_SIZE]


def set_sector(image, lba, value):
    require(len(value) == SECTOR_SIZE, "invalid sector update")
    start = lba * SECTOR_SIZE
    image[start : start + SECTOR_SIZE] = value


def u32(data, offset):
    return int.from_bytes(data[offset : offset + 4], "little")


def inspect_active_image(path):
    image = path.read_bytes()
    roots = []
    for superblock_lba in (SUPERBLOCK_A, SUPERBLOCK_B):
        sb = sector(image, superblock_lba)
        if sb[0:8] != b"BOGFS37\0":
            continue
        require(sha256(sb[0:88]) == sb[88:120], "stored superblock checksum invalid")
        generation = u32(sb, 12)
        manifest_lba = u32(sb, 16)
        manifest = image[manifest_lba * SECTOR_SIZE : (manifest_lba + MANIFEST_SECTORS) * SECTOR_SIZE]
        require(sha256(manifest) == sb[24:56], "stored manifest hash invalid")
        require(root_hash(generation, manifest_lba, sb[24:56]) == sb[56:88], "stored root hash invalid")
        record = manifest[64:192]
        length = u32(record, 68)
        data_lba = u32(record, 72)
        content = sector(image, data_lba)[:length]
        require(sha256(content) == record[80:112], "stored file hash invalid")
        roots.append(
            {
                "generation": generation,
                "root_hash": sb[56:88].hex(),
                "manifest_hash": sb[24:56].hex(),
                "superblock_lba": superblock_lba,
                "manifest_lba": manifest_lba,
                "file_version": u32(record, 64),
                "file_length": length,
                "file_lba": data_lba,
                "file_hash": record[80:112].hex(),
                "file_bytes_hex": content.hex(),
            }
        )
    require(roots, "no inspectable roots")
    return max(roots, key=lambda value: value["generation"])


def refresh_superblock(sb):
    sb[88:120] = sha256(sb[0:88])


def corruption_images(written, directory):
    source = written.read_bytes()
    cases = {}

    def save(name, mutate):
        image = bytearray(source)
        mutate(image)
        path = directory / f"{name}.img"
        path.write_bytes(image)
        cases[name] = path

    def bad_superblock(image):
        sb = bytearray(sector(image, SUPERBLOCK_B))
        sb[88] ^= 1
        set_sector(image, SUPERBLOCK_B, sb)

    def bad_root(image):
        sb = bytearray(sector(image, SUPERBLOCK_B))
        sb[56] ^= 1
        refresh_superblock(sb)
        set_sector(image, SUPERBLOCK_B, sb)

    def bad_manifest(image):
        image[MANIFEST_B * SECTOR_SIZE + 300] ^= 1

    def bad_file_table(image):
        manifest_start = MANIFEST_B * SECTOR_SIZE
        image[manifest_start + 64] = ord("X")
        manifest = bytes(image[manifest_start : manifest_start + MANIFEST_SECTORS * SECTOR_SIZE])
        sb = bytearray(sector(image, SUPERBLOCK_B))
        manifest_hash = sha256(manifest)
        sb[24:56] = manifest_hash
        sb[56:88] = root_hash(u32(sb, 12), MANIFEST_B, manifest_hash)
        refresh_superblock(sb)
        set_sector(image, SUPERBLOCK_B, sb)

    def bad_data(image):
        image[65 * SECTOR_SIZE] ^= 1

    def no_roots(image):
        for lba in (SUPERBLOCK_A, SUPERBLOCK_B):
            sb = bytearray(sector(image, lba))
            sb[0] ^= 1
            set_sector(image, lba, sb)

    save("corrupt_superblock", bad_superblock)
    save("corrupt_root", bad_root)
    save("corrupt_manifest", bad_manifest)
    save("corrupt_file_table", bad_file_table)
    save("corrupt_file_data", bad_data)
    save("corrupt_both_roots", no_roots)
    return cases


def main():
    for tool in ["cargo", "qemu-system-i386"]:
        require(shutil.which(tool) is not None, f"{tool} not found in PATH")

    require((ROOT / "README.md").read_text().startswith(("# BOGBIN v37.0.0", "# BOGBIN v38.0.0", "# BOGBIN v39.0.0")), "README is not v37.0.0")
    require(any(marker in (ROOT / "PROJECT_STATUS.md").read_text() for marker in ["Current release: v37.0.0", "Current release: v38.0.0", "Current release: v39.0.0"]), "PROJECT_STATUS is not v37.0.0")
    require("## v37.0.0: Persistent Verified BogFS" in (ROOT / "RELEASE_NOTES.md").read_text(), "v37 release notes missing")
    docs = (ROOT / "docs/v37_persistent_bogfs_plan.md").read_text()
    for marker in ["On-Disk Layout", "Mount And Commit Protocol", "Crash-Safety Boundary", "No POSIX"]:
        require(marker in docs, f"v37 documentation marker missing: {marker}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    make_image(BASE_IMAGE)
    shutil.copyfile(BASE_IMAGE, WRITTEN_IMAGE)

    result = subprocess.run(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    kernel_path = KERNEL_DIR / "target/i686-unknown-linux-musl/debug/bogk-kernel"

    boot1 = run_qemu(kernel_path, WRITTEN_IMAGE, BOOT1_LOG)
    boot2 = run_qemu(kernel_path, WRITTEN_IMAGE, BOOT2_LOG)
    boot1_mounts = parse_receipts(boot1, "BOGOS_BOGFS_MOUNT_BEGIN", "BOGOS_BOGFS_MOUNT_END")
    boot2_mounts = parse_receipts(boot2, "BOGOS_BOGFS_MOUNT_BEGIN", "BOGOS_BOGFS_MOUNT_END")
    boot1_ops = parse_receipts(boot1, "BOGOS_PERSISTENT_BOGFS_BEGIN", "BOGOS_PERSISTENT_BOGFS_END")
    boot2_ops = parse_receipts(boot2, "BOGOS_PERSISTENT_BOGFS_BEGIN", "BOGOS_PERSISTENT_BOGFS_END")
    commits = parse_receipts(boot1, "BOGOS_BOGFS_COMMIT_BEGIN", "BOGOS_BOGFS_COMMIT_END")

    require(boot1_mounts[0]["STATUS"] == "accepted" and boot1_mounts[0]["GENERATION"] == "1", "boot one did not mount base root")
    require(len(commits) == 1 and commits[0]["STATUS"] == "accepted", "boot one did not commit exactly one root")
    require(commits[0]["OLD_GENERATION"] == "1" and commits[0]["NEW_GENERATION"] == "2", "commit generation transition invalid")
    require(commits[0]["MUTATED_TRUSTED_STATE"] == "true", "verified commit did not admit trusted root")
    accepted_write = next(op for op in boot1_ops if op["OPERATION"] == "write" and op["STATUS"] == "accepted")
    require(accepted_write["OLD_VERSION"] == "1" and accepted_write["NEW_VERSION"] == "2", "file version transition invalid")
    require(accepted_write["OLD_ROOT_HASH"] != accepted_write["NEW_ROOT_HASH"], "accepted write did not change root")

    rejected = [op for op in boot1_ops if op["STATUS"] == "rejected"]
    reject_reasons = {op["REJECT_REASON"] for op in rejected}
    required_rejections = {
        "unauthorized_caller",
        "invalid_pointer",
        "invalid_path",
        "protected_path",
        "oversized_write",
        "stale_preimage",
        "storage_full",
        "readback_hash_mismatch",
    }
    require(required_rejections <= reject_reasons, "write rejection matrix incomplete")
    require(all(op["MUTATED_TRUSTED_STATE"] == "false" for op in rejected), "rejected write mutated trusted root")
    require(all(op["OLD_ROOT_HASH"] == op["NEW_ROOT_HASH"] for op in rejected), "rejected write changed receipt root")

    require(boot2_mounts[0]["STATUS"] == "accepted" and boot2_mounts[0]["GENERATION"] == "2", "boot two did not mount committed root")
    reboot = next(op for op in boot2_ops if op["OPERATION"] == "reboot_verify")
    require(reboot["NEW_VERSION"] == "2", "reboot did not preserve file version")
    require(reboot["NEW_HASH"] == accepted_write["NEW_HASH"], "reboot did not preserve file hash")
    require(reboot["NEW_ROOT_HASH"] == accepted_write["NEW_ROOT_HASH"], "reboot did not preserve root hash")

    active = inspect_active_image(WRITTEN_IMAGE)
    require(bytes.fromhex(active["file_bytes_hex"]) == COMMITTED_DATA, "written image did not preserve committed bytes")
    require(active["file_hash"] == accepted_write["NEW_HASH"], "disk content hash disagrees with receipt")

    corruptions = {}
    with tempfile.TemporaryDirectory(prefix="bogos-v37-") as temp:
        for name, image in corruption_images(WRITTEN_IMAGE, Path(temp)).items():
            output = run_qemu(kernel_path, image, Path(temp) / f"{name}.log")
            mount = parse_receipts(output, "BOGOS_BOGFS_MOUNT_BEGIN", "BOGOS_BOGFS_MOUNT_END")[0]
            corruptions[name] = mount

    expected_slot_b_reasons = {
        "corrupt_superblock": "superblock_checksum_mismatch",
        "corrupt_root": "root_hash_mismatch",
        "corrupt_manifest": "manifest_hash_mismatch",
        "corrupt_file_table": "file_table_invalid",
        "corrupt_file_data": "file_content_hash_mismatch",
    }
    for name, reason in expected_slot_b_reasons.items():
        mount = corruptions[name]
        require(mount["STATUS"] == "accepted" and mount["GENERATION"] == "1", f"{name} did not fall back")
        require(mount["FALLBACK_USED"] == "true" and mount["SLOT_B_REASON"] == reason, f"{name} fallback reason invalid")
        require(mount["MUTATED_TRUSTED_STATE"] == "false", f"{name} mount mutated state")
    require(corruptions["corrupt_both_roots"]["STATUS"] == "rejected", "two corrupt roots did not reject mount")
    require(corruptions["corrupt_both_roots"]["REJECT_REASON"] == "no_valid_root", "two-root rejection reason invalid")

    receipt = {
        "format": "BOGOS-v37-persistent-bogfs-receipt-1.0",
        "milestone": "v37.0.0-persistent-verified-bogfs",
        "execution_status": "completed",
        "platform": "qemu-i686",
        "claim": "tiny fixed-file persistent verified BogFS over the v36 QEMU ATA PIO proof",
        "base_image_sha256": sha256_hex(BASE_IMAGE.read_bytes()),
        "written_image_sha256": sha256_hex(WRITTEN_IMAGE.read_bytes()),
        "boot1_mount": boot1_mounts[0],
        "accepted_commit": commits[0],
        "accepted_write": accepted_write,
        "rejected_writes": rejected,
        "boot2_mount": boot2_mounts[0],
        "reboot_verification": reboot,
        "active_disk_state": active,
        "corruption_evidence": corruptions,
        "two_boot_persistence_proven": True,
        "rejected_writes_mutated_trusted_root": False,
        "directories_implemented": False,
        "create_delete_implemented": False,
        "posix_filesystem": False,
        "physical_hardware_support": False,
        "boot1_serial_sha256": sha256_hex(BOOT1_LOG.read_bytes()),
        "boot2_serial_sha256": sha256_hex(BOOT2_LOG.read_bytes()),
        "evaluator_sha256": sha256_hex(Path(__file__).read_bytes()),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v37 Persistent Verified BogFS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v37 Persistent Verified BogFS evaluator FAILED: {exc}")
        sys.exit(1)
