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
DATA_LBA = 64
PATH = b"/data/persist.bin"
INITIAL_DATA = b"V37-BASE"


def sha256(data):
    return hashlib.sha256(data).digest()


def root_hash(generation, manifest_lba, manifest_hash):
    canonical = b"BOGROOT37" + generation.to_bytes(4, "little") + manifest_lba.to_bytes(4, "little") + manifest_hash
    return sha256(canonical)


def make_manifest(generation, next_free_lba, data_lba, version, content):
    manifest = bytearray(SECTOR_SIZE * MANIFEST_SECTORS)
    manifest[0:8] = b"BOGMAN37"
    manifest[8:12] = generation.to_bytes(4, "little")
    manifest[12:16] = (1).to_bytes(4, "little")
    manifest[16:20] = next_free_lba.to_bytes(4, "little")

    record = memoryview(manifest)[64:192]
    record[0 : len(PATH)] = PATH
    record[len(PATH)] = 0
    record[64:68] = version.to_bytes(4, "little")
    record[68:72] = len(content).to_bytes(4, "little")
    record[72:76] = data_lba.to_bytes(4, "little")
    record[76:80] = (1).to_bytes(4, "little")
    record[80:112] = sha256(content)
    record[112:116] = (1).to_bytes(4, "little")
    return bytes(manifest)


def make_superblock(generation, manifest_lba, manifest):
    manifest_hash = sha256(manifest)
    root = root_hash(generation, manifest_lba, manifest_hash)
    superblock = bytearray(SECTOR_SIZE)
    superblock[0:8] = b"BOGFS37\0"
    superblock[8:12] = (1).to_bytes(4, "little")
    superblock[12:16] = generation.to_bytes(4, "little")
    superblock[16:20] = manifest_lba.to_bytes(4, "little")
    superblock[20:24] = MANIFEST_SECTORS.to_bytes(4, "little")
    superblock[24:56] = manifest_hash
    superblock[56:88] = root
    superblock[88:120] = sha256(superblock[0:88])
    return bytes(superblock), manifest_hash, root


def write_sector(image, lba, content):
    assert len(content) == SECTOR_SIZE
    start = lba * SECTOR_SIZE
    image[start : start + SECTOR_SIZE] = content


def make_image(output):
    image = bytearray(SECTOR_SIZE * SECTOR_COUNT)
    write_sector(image, 0, b"BOGV37IMG" + bytes(SECTOR_SIZE - 9))
    data_sector = INITIAL_DATA + bytes(SECTOR_SIZE - len(INITIAL_DATA))
    write_sector(image, DATA_LBA, data_sector)

    manifest = make_manifest(1, DATA_LBA + 1, DATA_LBA, 1, INITIAL_DATA)
    for index in range(MANIFEST_SECTORS):
        write_sector(image, MANIFEST_A + index, manifest[index * SECTOR_SIZE : (index + 1) * SECTOR_SIZE])
    superblock, manifest_hash, root = make_superblock(1, MANIFEST_A, manifest)
    write_sector(image, SUPERBLOCK_A, superblock)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {
        "format": "BOGOS-v37-persistent-bogfs-image-1.0",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "generation": 1,
        "active_superblock_lba": SUPERBLOCK_A,
        "manifest_lba": MANIFEST_A,
        "manifest_sha256": manifest_hash.hex(),
        "root_sha256": root.hex(),
        "file": {
            "path": PATH.decode(),
            "version": 1,
            "length": len(INITIAL_DATA),
            "data_lba": DATA_LBA,
            "content_sha256": sha256(INITIAL_DATA).hex(),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Build the deterministic v37 persistent BogFS image")
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest = make_image(args.output)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
