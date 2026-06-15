import argparse
import hashlib
import json
from pathlib import Path


SECTOR_SIZE = 512
SECTOR_COUNT = 8192
MANIFEST_SECTORS = 8
SUPERBLOCK_A = 1
SUPERBLOCK_B = 2
MANIFEST_A = 8
MANIFEST_B = 16
DATA_START_LBA = 64
MAX_RECORDS = 8
RECORD_SIZE = 128
TYPE_FILE = 1
TYPE_DIRECTORY = 2
TYPE_TOMBSTONE = 3

SEED_FILES = {
    "/data/delete.txt": b"V38-DELETE-ME",
    "/data/keep.txt": b"V38-KEEP",
}


def sha256(data):
    return hashlib.sha256(data).digest()


def root_hash(generation, manifest_lba, manifest_hash):
    return sha256(b"BOGROOT38" + generation.to_bytes(4, "little") + manifest_lba.to_bytes(4, "little") + manifest_hash)


def make_record(path, entry_type, lifecycle_id, version=1, content=b"", data_lba=0):
    record = bytearray(RECORD_SIZE)
    encoded = path.encode("ascii")
    record[0 : len(encoded)] = encoded
    record[len(encoded)] = 0
    record[64:68] = version.to_bytes(4, "little")
    record[68:72] = len(content).to_bytes(4, "little")
    record[72:76] = data_lba.to_bytes(4, "little")
    record[76:80] = entry_type.to_bytes(4, "little")
    if entry_type == TYPE_FILE:
        record[80:112] = sha256(content)
    record[112:116] = lifecycle_id.to_bytes(4, "little")
    record[116:120] = (1).to_bytes(4, "little")
    return bytes(record)


def listing_hash(records):
    return sha256(b"".join(records))


def make_manifest(generation, next_free_lba, next_lifecycle_id, records):
    manifest = bytearray(SECTOR_SIZE * MANIFEST_SECTORS)
    manifest[0:8] = b"BOGMAN38"
    manifest[8:12] = generation.to_bytes(4, "little")
    manifest[12:16] = len(records).to_bytes(4, "little")
    manifest[16:20] = next_free_lba.to_bytes(4, "little")
    manifest[20:24] = next_lifecycle_id.to_bytes(4, "little")
    manifest[24:56] = listing_hash(records)
    for index, record in enumerate(records):
        start = 64 + index * RECORD_SIZE
        manifest[start : start + RECORD_SIZE] = record
    return bytes(manifest)


def make_superblock(generation, manifest_lba, manifest):
    manifest_hash = sha256(manifest)
    root = root_hash(generation, manifest_lba, manifest_hash)
    superblock = bytearray(SECTOR_SIZE)
    superblock[0:8] = b"BOGFS38\0"
    superblock[8:12] = (2).to_bytes(4, "little")
    superblock[12:16] = generation.to_bytes(4, "little")
    superblock[16:20] = manifest_lba.to_bytes(4, "little")
    superblock[20:24] = MANIFEST_SECTORS.to_bytes(4, "little")
    superblock[24:56] = manifest_hash
    superblock[56:88] = root
    superblock[88:120] = sha256(superblock[0:88])
    return bytes(superblock), manifest_hash, root


def write_sector(image, lba, content):
    assert len(content) == SECTOR_SIZE
    image[lba * SECTOR_SIZE : (lba + 1) * SECTOR_SIZE] = content


def make_image(output):
    image = bytearray(SECTOR_SIZE * SECTOR_COUNT)
    write_sector(image, 0, b"BOGV38IMG" + bytes(SECTOR_SIZE - 9))
    records = []
    lifecycle_id = 1
    for path in ["/apps", "/data", "/receipts", "/system"]:
        records.append(make_record(path, TYPE_DIRECTORY, lifecycle_id))
        lifecycle_id += 1
    data_lba = DATA_START_LBA
    for path, content in sorted(SEED_FILES.items()):
        write_sector(image, data_lba, content + bytes(SECTOR_SIZE - len(content)))
        records.append(make_record(path, TYPE_FILE, lifecycle_id, content=content, data_lba=data_lba))
        lifecycle_id += 1
        data_lba += 1
    records.sort(key=lambda record: record[0:64])
    manifest = make_manifest(1, data_lba, lifecycle_id, records)
    for index in range(MANIFEST_SECTORS):
        write_sector(image, MANIFEST_A + index, manifest[index * SECTOR_SIZE : (index + 1) * SECTOR_SIZE])
    superblock, manifest_hash, root = make_superblock(1, MANIFEST_A, manifest)
    write_sector(image, SUPERBLOCK_A, superblock)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {
        "format": "BOGOS-v38-file-lifecycle-image-1.0",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "generation": 1,
        "record_count": len(records),
        "next_free_lba": data_lba,
        "next_lifecycle_id": lifecycle_id,
        "manifest_sha256": manifest_hash.hex(),
        "root_sha256": root.hex(),
    }


def main():
    parser = argparse.ArgumentParser(description="Build deterministic v38 lifecycle BogFS image")
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
