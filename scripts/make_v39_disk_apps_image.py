import argparse
import hashlib
import json
from pathlib import Path

from make_v38_file_lifecycle_image import (
    DATA_START_LBA,
    MANIFEST_A,
    MANIFEST_SECTORS,
    MAX_RECORDS,
    RECORD_SIZE,
    SECTOR_COUNT,
    SECTOR_SIZE,
    SUPERBLOCK_A,
    TYPE_DIRECTORY,
    TYPE_FILE,
    listing_hash,
    make_record,
    write_sector,
)
from pack_v39_bogapp import pack_app


HELLO_CODE = bytes.fromhex("b80600000031dbcd80")


def sha256(data):
    return hashlib.sha256(data).digest()


def root_hash(generation, manifest_lba, manifest_hash):
    return sha256(b"BOGROOT39" + generation.to_bytes(4, "little") + manifest_lba.to_bytes(4, "little") + manifest_hash)


def make_manifest(records, next_free_lba, next_lifecycle_id):
    manifest = bytearray(SECTOR_SIZE * MANIFEST_SECTORS)
    manifest[0:8] = b"BOGMAN39"
    manifest[8:12] = (1).to_bytes(4, "little")
    manifest[12:16] = len(records).to_bytes(4, "little")
    manifest[16:20] = next_free_lba.to_bytes(4, "little")
    manifest[20:24] = next_lifecycle_id.to_bytes(4, "little")
    manifest[24:56] = listing_hash(records)
    for index, record in enumerate(records):
        start = 64 + index * RECORD_SIZE
        manifest[start : start + RECORD_SIZE] = record
    return bytes(manifest)


def make_superblock(manifest):
    manifest_hash = sha256(manifest)
    root = root_hash(1, MANIFEST_A, manifest_hash)
    superblock = bytearray(SECTOR_SIZE)
    superblock[0:8] = b"BOGFS39\0"
    superblock[8:12] = (3).to_bytes(4, "little")
    superblock[12:16] = (1).to_bytes(4, "little")
    superblock[16:20] = MANIFEST_A.to_bytes(4, "little")
    superblock[20:24] = MANIFEST_SECTORS.to_bytes(4, "little")
    superblock[24:56] = manifest_hash
    superblock[56:88] = root
    superblock[88:120] = sha256(superblock[0:88])
    return bytes(superblock), manifest_hash, root


def app_fixtures():
    valid = pack_app(HELLO_CODE, "hello", "2.0.0")
    bad_magic = bytearray(valid)
    bad_magic[0] ^= 1
    bad_code_hash = bytearray(valid)
    bad_code_hash[96] ^= 1
    bad_code_hash[128:160] = sha256(bad_code_hash[0:128])
    bad_capability = bytearray(valid)
    bad_capability[32:36] = (0x80000000).to_bytes(4, "little")
    bad_capability[128:160] = sha256(bad_capability[0:128])
    return {
        "/apps/bad-capability.bogapp": bytes(bad_capability),
        "/apps/bad-code-hash.bogapp": bytes(bad_code_hash),
        "/apps/bad-magic.bogapp": bytes(bad_magic),
        "/apps/hello.bogapp": valid,
    }


def make_image(output):
    image = bytearray(SECTOR_SIZE * SECTOR_COUNT)
    write_sector(image, 0, b"BOGV39IMG" + bytes(SECTOR_SIZE - 9))
    records = []
    lifecycle_id = 1
    for path in ["/apps", "/data", "/receipts", "/system"]:
        records.append(make_record(path, TYPE_DIRECTORY, lifecycle_id))
        lifecycle_id += 1
    fixtures = app_fixtures()
    data_lba = DATA_START_LBA
    fixture_metadata = {}
    for path, content in sorted(fixtures.items()):
        assert len(content) <= SECTOR_SIZE
        write_sector(image, data_lba, content + bytes(SECTOR_SIZE - len(content)))
        records.append(make_record(path, TYPE_FILE, lifecycle_id, content=content, data_lba=data_lba))
        fixture_metadata[path] = {
            "length": len(content),
            "lba": data_lba,
            "file_sha256": sha256(content).hex(),
        }
        lifecycle_id += 1
        data_lba += 1
    records.sort(key=lambda record: record[0:64])
    assert len(records) == MAX_RECORDS
    manifest = make_manifest(records, data_lba, lifecycle_id)
    for index in range(MANIFEST_SECTORS):
        write_sector(image, MANIFEST_A + index, manifest[index * SECTOR_SIZE : (index + 1) * SECTOR_SIZE])
    superblock, manifest_hash, root = make_superblock(manifest)
    write_sector(image, SUPERBLOCK_A, superblock)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {
        "format": "BOGOS-v39-disk-apps-image-1.0",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "generation": 1,
        "root_sha256": root.hex(),
        "manifest_sha256": manifest_hash.hex(),
        "fixtures": fixture_metadata,
    }


def main():
    parser = argparse.ArgumentParser(description="Build deterministic v39 persistent disk-app image")
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    metadata = make_image(args.output)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
