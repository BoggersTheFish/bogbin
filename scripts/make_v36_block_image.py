import argparse
import hashlib
import json
from pathlib import Path


SECTOR_SIZE = 512
SECTOR_COUNT = 8192
FIXTURES = {
    64: "BOGOS-V36-VERIFIED-READ-SECTOR",
    65: "BOGOS-V36-WRITE-BEFORE",
    66: "BOGOS-V36-CORRUPT-SECTOR",
}


def sector(label):
    data = label.encode("ascii") + b"\n"
    return data + bytes(SECTOR_SIZE - len(data))


def make_image(output):
    image = bytearray(SECTOR_SIZE * SECTOR_COUNT)
    manifest = {}
    for lba, label in FIXTURES.items():
        payload = sector(label)
        start = lba * SECTOR_SIZE
        image[start : start + SECTOR_SIZE] = payload
        manifest[str(lba)] = {
            "label": label,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {
        "format": "BOGOS-v36-block-image-manifest-1.0",
        "sector_size": SECTOR_SIZE,
        "sector_count": SECTOR_COUNT,
        "writable_first": 64,
        "writable_last": 127,
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "fixtures": manifest,
    }


def main():
    parser = argparse.ArgumentParser(description="Build the deterministic v36 QEMU block image")
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
