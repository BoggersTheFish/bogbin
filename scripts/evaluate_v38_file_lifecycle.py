import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from make_v38_file_lifecycle_image import (
    MANIFEST_B,
    MANIFEST_SECTORS,
    RECORD_SIZE,
    SECTOR_SIZE,
    SUPERBLOCK_A,
    SUPERBLOCK_B,
    TYPE_FILE,
    TYPE_TOMBSTONE,
    make_image,
    root_hash,
)


ROOT = Path(__file__).resolve().parents[1]
KERNEL_DIR = ROOT / "kernel"
ARTIFACTS = ROOT / "artifacts"
BASE_IMAGE = ARTIFACTS / "bogos_v38_file_lifecycle_base.img"
WRITTEN_IMAGE = ARTIFACTS / "bogos_v38_file_lifecycle_written.img"
BOOT1_LOG = ARTIFACTS / "bogos_v38_file_lifecycle_boot1_serial.log"
BOOT2_LOG = ARTIFACTS / "bogos_v38_file_lifecycle_boot2_serial.log"
RECEIPT_PATH = ARTIFACTS / "bogos_v38_file_lifecycle_receipt.json"
WRITTEN_DATA = b"V38-LIFECYCLE-DATA"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(data):
    return hashlib.sha256(data).digest()


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
            "qemu-system-i386", "-kernel", str(kernel_path), "-serial", f"file:{serial_log}",
            "-display", "none", "-no-reboot", "-no-shutdown",
            "-drive", f"file={image},format=raw,if=ide,index=0,media=disk",
        ]
    )
    output = ""
    deadline = time.time() + 15
    while time.time() < deadline:
        if serial_log.exists():
            output = serial_log.read_text(errors="replace")
            if "BOGOS_V38_INVARIANTS_END" in output:
                break
        time.sleep(0.1)
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    require("BOGOS_V38_INVARIANTS_END" in output, f"v38 QEMU scenario did not complete: {serial_log}")
    return output


def u32(data, offset):
    return int.from_bytes(data[offset : offset + 4], "little")


def sector(image, lba):
    return image[lba * SECTOR_SIZE : (lba + 1) * SECTOR_SIZE]


def set_sector(image, lba, value):
    image[lba * SECTOR_SIZE : (lba + 1) * SECTOR_SIZE] = value


def active_state(path):
    image = path.read_bytes()
    roots = []
    for sb_lba in (SUPERBLOCK_A, SUPERBLOCK_B):
        sb = sector(image, sb_lba)
        if sb[0:8] != b"BOGFS38\0":
            continue
        require(sha256(sb[0:88]) == sb[88:120], "invalid superblock checksum")
        generation = u32(sb, 12)
        manifest_lba = u32(sb, 16)
        manifest = image[manifest_lba * SECTOR_SIZE : (manifest_lba + MANIFEST_SECTORS) * SECTOR_SIZE]
        require(sha256(manifest) == sb[24:56], "invalid manifest hash")
        require(root_hash(generation, manifest_lba, sb[24:56]) == sb[56:88], "invalid root hash")
        count = u32(manifest, 12)
        records = {}
        for index in range(count):
            record = manifest[64 + index * RECORD_SIZE : 64 + (index + 1) * RECORD_SIZE]
            path_end = record[0:64].index(0)
            record_path = record[0:path_end].decode()
            entry_type = u32(record, 76)
            length = u32(record, 68)
            lba = u32(record, 72)
            content = sector(image, lba)[:length] if entry_type == TYPE_FILE and length else b""
            if entry_type == TYPE_FILE:
                require(sha256(content) == record[80:112], f"invalid content hash: {record_path}")
            records[record_path] = {
                "type": entry_type,
                "version": u32(record, 64),
                "length": length,
                "lba": lba,
                "hash": record[80:112].hex(),
                "lifecycle_id": u32(record, 112),
                "content_hex": content.hex(),
            }
        roots.append({
            "generation": generation,
            "root_hash": sb[56:88].hex(),
            "manifest_hash": sb[24:56].hex(),
            "superblock_lba": sb_lba,
            "manifest_lba": manifest_lba,
            "record_count": count,
            "next_free_lba": u32(manifest, 16),
            "records": records,
        })
    require(roots, "no valid roots in image")
    return max(roots, key=lambda root: root["generation"])


def refresh_sb(sb):
    sb[88:120] = sha256(sb[0:88])


def refresh_active_metadata(image, refresh_listing=True):
    start = MANIFEST_B * SECTOR_SIZE
    manifest = bytearray(image[start : start + MANIFEST_SECTORS * SECTOR_SIZE])
    count = u32(manifest, 12)
    if refresh_listing:
        manifest[24:56] = sha256(manifest[64 : 64 + count * RECORD_SIZE])
    image[start : start + len(manifest)] = manifest
    sb = bytearray(sector(image, SUPERBLOCK_B))
    manifest_hash = sha256(manifest)
    sb[24:56] = manifest_hash
    sb[56:88] = root_hash(u32(sb, 12), MANIFEST_B, manifest_hash)
    refresh_sb(sb)
    set_sector(image, SUPERBLOCK_B, sb)


def corruption_images(written, directory):
    source = written.read_bytes()
    cases = {}

    def save(name, mutate):
        image = bytearray(source)
        mutate(image)
        path = directory / f"{name}.img"
        path.write_bytes(image)
        cases[name] = path

    def bad_root(image):
        sb = bytearray(sector(image, SUPERBLOCK_B))
        sb[56] ^= 1
        refresh_sb(sb)
        set_sector(image, SUPERBLOCK_B, sb)

    def bad_file_table(image):
        image[MANIFEST_B * SECTOR_SIZE + 64] = ord("X")
        refresh_active_metadata(image, refresh_listing=True)

    def bad_directory_table(image):
        image[MANIFEST_B * SECTOR_SIZE + 24] ^= 1
        refresh_active_metadata(image, refresh_listing=False)

    def bad_file_data(image):
        active = active_state(written)
        image[active["records"]["/data/new.txt"]["lba"] * SECTOR_SIZE] ^= 1

    def no_roots(image):
        for lba in (SUPERBLOCK_A, SUPERBLOCK_B):
            sb = bytearray(sector(image, lba))
            sb[0] ^= 1
            set_sector(image, lba, sb)

    save("corrupt_root", bad_root)
    save("corrupt_file_table", bad_file_table)
    save("corrupt_directory_table", bad_directory_table)
    save("corrupt_file_data", bad_file_data)
    save("corrupt_both_roots", no_roots)
    return cases


def main():
    for tool in ["cargo", "qemu-system-i386"]:
        require(shutil.which(tool), f"{tool} not found in PATH")
    require((ROOT / "README.md").read_text().startswith(("# BOGBIN v38.0.0", "# BOGBIN v39.0.0")), "README is not v38.0.0")
    require(any(marker in (ROOT / "PROJECT_STATUS.md").read_text() for marker in ["Current release: v38.0.0", "Current release: v39.0.0"]), "PROJECT_STATUS is not v38.0.0")
    require("## v38.0.0: File Lifecycle" in (ROOT / "RELEASE_NOTES.md").read_text(), "v38 release notes missing")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    make_image(BASE_IMAGE)
    shutil.copyfile(BASE_IMAGE, WRITTEN_IMAGE)
    result = subprocess.run(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=KERNEL_DIR, capture_output=True, text=True,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    kernel_path = KERNEL_DIR / "target/i686-unknown-linux-musl/debug/bogk-kernel"

    boot1 = run_qemu(kernel_path, WRITTEN_IMAGE, BOOT1_LOG)
    boot2 = run_qemu(kernel_path, WRITTEN_IMAGE, BOOT2_LOG)
    mounts1 = parse_receipts(boot1, "BOGOS_V38_MOUNT_BEGIN", "BOGOS_V38_MOUNT_END")
    mounts2 = parse_receipts(boot2, "BOGOS_V38_MOUNT_BEGIN", "BOGOS_V38_MOUNT_END")
    ops1 = parse_receipts(boot1, "BOGOS_BOGFS_LIFECYCLE_BEGIN", "BOGOS_BOGFS_LIFECYCLE_END")
    ops2 = parse_receipts(boot2, "BOGOS_BOGFS_LIFECYCLE_BEGIN", "BOGOS_BOGFS_LIFECYCLE_END")
    lists1 = parse_receipts(boot1, "BOGOS_BOGFS_LIST_BEGIN", "BOGOS_BOGFS_LIST_END")
    lists2 = parse_receipts(boot2, "BOGOS_BOGFS_LIST_BEGIN", "BOGOS_BOGFS_LIST_END")

    require(mounts1[0]["STATUS"] == "accepted" and mounts1[0]["GENERATION"] == "1", "boot one base mount failed")
    accepted = [op for op in ops1 if op["STATUS"] == "accepted" and op["OPERATION"] in {"create", "write", "delete"}]
    require([op["OPERATION"] for op in accepted] == ["create", "write", "delete"], "accepted lifecycle sequence invalid")
    require([op["NEW_ROOT_HASH"] for op in accepted] == list(dict.fromkeys(op["NEW_ROOT_HASH"] for op in accepted)), "mutations did not produce distinct roots")
    require(all(op["MUTATED_TRUSTED_STATE"] == "true" for op in accepted), "accepted mutation did not admit root")
    rejected = [op for op in ops1 if op["STATUS"] == "rejected"]
    reasons = {op["REJECT_REASON"] for op in rejected}
    expected_reasons = {
        "unauthorized_caller", "invalid_pointer", "invalid_path", "path_traversal", "path_alias", "duplicate_create", "outside_mutable_area",
        "protected_path", "missing_file", "oversized_file", "file_table_full", "storage_full",
        "stale_expected_root", "stale_version", "stale_preimage", "list_on_file",
        "readback_hash_mismatch", "metadata_readback_mismatch", "deleted_file",
    }
    require(expected_reasons <= reasons, "negative lifecycle matrix incomplete")
    require(all(op["MUTATED_TRUSTED_STATE"] == "false" for op in rejected), "rejected lifecycle operation mutated root")
    require(all(op["OLD_ROOT_HASH"] == op["NEW_ROOT_HASH"] for op in rejected), "rejected lifecycle receipt changed root")
    require(lists1[-1]["COUNT"] == "2", "post-delete list count invalid")

    require(mounts2[0]["STATUS"] == "accepted" and mounts2[0]["GENERATION"] == "4", "boot two did not mount lifecycle root")
    reboot = next(op for op in ops2 if op["OPERATION"] == "reboot_verify")
    require(reboot["NEW_ROOT_HASH"] == accepted[-1]["NEW_ROOT_HASH"], "reboot root mismatch")
    require(lists2[-1]["COUNT"] == "2" and lists2[-1]["RESULT_HASH"] == lists1[-1]["RESULT_HASH"], "listing did not persist")

    disk = active_state(WRITTEN_IMAGE)
    require(disk["generation"] == 4, "active image generation invalid")
    require(bytes.fromhex(disk["records"]["/data/new.txt"]["content_hex"]) == WRITTEN_DATA, "created file bytes did not persist")
    require(disk["records"]["/data/new.txt"]["version"] == 2, "created file version did not persist")
    require(disk["records"]["/data/delete.txt"]["type"] == TYPE_TOMBSTONE, "deleted file tombstone did not persist")
    require(disk["records"]["/data/delete.txt"]["version"] == 2, "deleted file version did not persist")

    corruptions = {}
    with tempfile.TemporaryDirectory(prefix="bogos-v38-") as temp:
        for name, image in corruption_images(WRITTEN_IMAGE, Path(temp)).items():
            output = run_qemu(kernel_path, image, Path(temp) / f"{name}.log")
            corruptions[name] = parse_receipts(output, "BOGOS_V38_MOUNT_BEGIN", "BOGOS_V38_MOUNT_END")[0]
    expected_corruptions = {
        "corrupt_root": "root_hash_mismatch",
        "corrupt_file_table": "file_table_invalid",
        "corrupt_directory_table": "directory_table_hash_mismatch",
    }
    for name, reason in expected_corruptions.items():
        mount = corruptions[name]
        require(mount["STATUS"] == "accepted" and mount["GENERATION"] == "3", f"{name} did not fall back")
        require(mount["FALLBACK_USED"] == "true" and mount["SLOT_B_REASON"] == reason, f"{name} reason invalid")
    require(corruptions["corrupt_file_data"]["STATUS"] == "rejected", "shared corrupt file data did not reject mount")
    require(corruptions["corrupt_file_data"]["REJECT_REASON"] == "no_valid_root", "corrupt file data rejection reason invalid")
    require(corruptions["corrupt_both_roots"]["STATUS"] == "rejected", "both corrupt roots did not reject")

    receipt = {
        "format": "BOGOS-v38-file-lifecycle-receipt-1.0",
        "milestone": "v38.0.0-file-lifecycle",
        "execution_status": "completed",
        "platform": "qemu-i686",
        "claim": "bounded flat-/data persistent BogFS lifecycle proof",
        "base_image_sha256": hashlib.sha256(BASE_IMAGE.read_bytes()).hexdigest(),
        "written_image_sha256": hashlib.sha256(WRITTEN_IMAGE.read_bytes()).hexdigest(),
        "boot1_mount": mounts1[0],
        "accepted_mutations": accepted,
        "rejected_operations": rejected,
        "boot1_final_listing": lists1[-1],
        "boot2_mount": mounts2[0],
        "boot2_listing": lists2[-1],
        "reboot_verification": reboot,
        "active_disk_state": disk,
        "corruption_evidence": corruptions,
        "two_boot_lifecycle_persistence_proven": True,
        "flat_data_only": True,
        "rename_implemented": False,
        "disk_loaded_apps": False,
        "posix_filesystem": False,
        "physical_hardware_support": False,
        "boot1_serial_sha256": hashlib.sha256(BOOT1_LOG.read_bytes()).hexdigest(),
        "boot2_serial_sha256": hashlib.sha256(BOOT2_LOG.read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")
    print("v38 File Lifecycle PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"v38 File Lifecycle evaluator FAILED: {exc}")
        sys.exit(1)
