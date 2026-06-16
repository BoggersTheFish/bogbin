"""
v40 Phase D: make persistent BogFS image containing GenesisRoot as well-known object.

Reuses v38 manifest/record layout (BOGMAN38 / BOGFS38 format, no new superblock region).
Adds one well-known record: /system/genesis_root (protected, file-like content holding canonical GENROOTv1).
The content is the serialized GenesisRoot (from oracle or model); its hash is in the record.
Receipt chain survival is proven via the workspace_root_hash + last_operation_receipt inside GenesisRoot + replay in evaluator.

This is the smallest integration: genesis lives inside existing manifest records.
Kernel (v38+ parser) sees it on mount, validates hash + parses via bogk-core, emits receipt-visible pointers.
No kernel file manager; no new syscalls; ops/replay proven host-side via oracle for the proof.
"""

import hashlib
import json
from pathlib import Path

from make_v38_file_lifecycle_image import (
    SECTOR_SIZE,
    SECTOR_COUNT,
    MANIFEST_SECTORS,
    SUPERBLOCK_A,
    SUPERBLOCK_B,
    MAX_RECORDS,
    RECORD_SIZE,
    TYPE_FILE,
    TYPE_DIRECTORY,
    DATA_START_LBA,
    make_record,
    make_manifest,
    make_superblock,
    write_sector,
    root_hash as v38_root_hash,
    listing_hash,
)

# v40 well-known genesis record (inside existing manifest, under protected /system)
V40_GENESIS_PATH = "/system/genesis_root"
V40_GENESIS_TYPE = 4  # marker (stored as file content record for data_lba)
V40_GENESIS_MAX = 256

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"

# Sentinels match Rust/Python oracle for v40 Phase D
EMPTY_PACKAGE_REGISTRY_ROOT = bytes([0x01] * 32)
EMPTY_CAPABILITY_POLICY_ROOT = bytes([0x02] * 32)
EMPTY_LEDGER_ROOT = bytes([0x03] * 32)
EMPTY_APP_REGISTRY_ROOT = bytes([0x04] * 32)
EMPTY_VERIFIER_REGISTRY_ROOT = bytes([0x05] * 32)


def sha256(data):
    return hashlib.sha256(data).digest()


def genesis_root_bytes(workspace_root_hash: bytes, ledger_root: bytes = None, boot_claim: bytes = None) -> bytes:
    """Exact match to Rust GENROOTv1 + make_genesis_root. For v41.1, ledger_root is the journal head."""
    if ledger_root is None:
        ledger_root = EMPTY_LEDGER_ROOT
    if boot_claim is None:
        boot_claim = b"\0" * 32
    b = bytearray(b"GENROOTv1")
    b.extend(b"BOGGEN40")
    b.extend((1).to_bytes(4, "little"))
    b.extend(EMPTY_LEDGER_ROOT)  # kernel_receipt (sentinel for now)
    b.extend(workspace_root_hash)
    b.extend(EMPTY_PACKAGE_REGISTRY_ROOT)
    b.extend(EMPTY_CAPABILITY_POLICY_ROOT)
    b.extend(ledger_root)  # v41.1: actual journal head
    b.extend(EMPTY_APP_REGISTRY_ROOT)
    b.extend(EMPTY_VERIFIER_REGISTRY_ROOT)
    b.extend(boot_claim)
    return bytes(b)


def genesis_root_hash(workspace_root_hash: bytes, ledger_root: bytes = None) -> bytes:
    return sha256(genesis_root_bytes(workspace_root_hash, ledger_root))

# v41.1: journal blob under /ledger/journal : u32 count + (u16 len + JRNLv41 bytes)*
JOURNAL_BLOB_PATH = "/ledger/journal"
JOURNAL_BLOB_TYPE = TYPE_FILE

def build_journal_blob(entries: list) -> bytes:
    """Pack list of (seq, prev_head, receipt_op_hash, old_root, new_root, verifier, accepted) or use prebuilt bytes.
    For simplicity, accept list of canonical entry bytes, or build here.
    """
    out = bytearray()
    out.extend(len(entries).to_bytes(4, "little"))
    for ent in entries:
        if isinstance(ent, (bytes, bytearray)):
            entry_bytes = bytes(ent)
        else:
            # assume tuple for build
            # for now expect pre-serialized bytes from oracle
            entry_bytes = bytes(ent)
        out.extend(len(entry_bytes).to_bytes(2, "little"))
        out.extend(entry_bytes)
    return bytes(out)

def make_journal_record(journal_blob: bytes, data_lba: int, lifecycle_id: int):
    rec = bytearray(RECORD_SIZE)
    enc = JOURNAL_BLOB_PATH.encode("ascii")
    rec[0:len(enc)] = enc
    rec[len(enc)] = 0
    rec[64:68] = (1).to_bytes(4, "little")
    rec[68:72] = len(journal_blob).to_bytes(4, "little")
    rec[72:76] = data_lba.to_bytes(4, "little")
    rec[76:80] = JOURNAL_BLOB_TYPE.to_bytes(4, "little")
    rec[80:112] = sha256(journal_blob)
    rec[112:116] = lifecycle_id.to_bytes(4, "little")
    rec[116:120] = (1).to_bytes(4, "little")
    return bytes(rec), journal_blob, sha256(journal_blob)


def make_v40_genesis_record(workspace_root_hash: bytes, data_lba: int, lifecycle_id: int):
    """Genesis as a record (path + content hash of canonical bytes)."""
    content = genesis_root_bytes(workspace_root_hash)
    # Rebuild exact record (use v38 make_record then override hash field for full content)
    rec = bytearray(RECORD_SIZE)
    enc = V40_GENESIS_PATH.encode("ascii")
    rec[0:len(enc)] = enc
    rec[len(enc)] = 0
    rec[64:68] = (1).to_bytes(4, "little")  # version
    rec[68:72] = len(content).to_bytes(4, "little")
    rec[72:76] = data_lba.to_bytes(4, "little")
    rec[76:80] = V40_GENESIS_TYPE.to_bytes(4, "little")
    rec[80:112] = sha256(content)
    rec[112:116] = lifecycle_id.to_bytes(4, "little")
    rec[116:120] = (1).to_bytes(4, "little")
    return bytes(rec), content, sha256(content)


def make_v40_base_image(output: Path, initial_ws_root_hash: bytes):
    """Build base image with v38 dirs + genesis record (blank workspace)."""
    image = bytearray(SECTOR_SIZE * SECTOR_COUNT)
    write_sector(image, 0, b"BOGV38IMG" + bytes(SECTOR_SIZE - 9))  # reuse v38 img magic for parser compat

    records = []
    lifecycle_id = 1
    for p in ["/apps", "/data", "/receipts", "/system"]:
        records.append(make_record(p, TYPE_DIRECTORY, lifecycle_id))
        lifecycle_id += 1

    data_lba = DATA_START_LBA
    # seed a small data for compat
    seed = b"V40-BASE"
    write_sector(image, data_lba, seed + bytes(SECTOR_SIZE - len(seed)))
    records.append(make_record("/data/keep.txt", TYPE_FILE, lifecycle_id, content=seed, data_lba=data_lba))
    lifecycle_id += 1
    data_lba += 1

    # genesis record data
    gen_content = genesis_root_bytes(initial_ws_root_hash)
    gen_lba = data_lba
    write_sector(image, gen_lba, gen_content + bytes(SECTOR_SIZE - len(gen_content)))
    gen_rec, _, _ = make_v40_genesis_record(initial_ws_root_hash, gen_lba, lifecycle_id)
    records.append(gen_rec)
    lifecycle_id += 1
    data_lba += 1

    manifest = make_manifest(1, data_lba, lifecycle_id, records)
    for i in range(MANIFEST_SECTORS):
        write_sector(image, 8 + i, manifest[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE])
    sb, mhash, rhash = make_superblock(1, 8, manifest)
    write_sector(image, SUPERBLOCK_A, sb)

    # minimal alt super (empty for v38 compat)
    # leave B zero for fallback tests if needed

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {
        "image": str(output),
        "genesis_hash": sha256(gen_content).hex(),
        "workspace_root_hash": initial_ws_root_hash.hex(),
        "manifest_hash": mhash.hex(),
        "root_hash": rhash.hex(),
    }


# v41.1 dedicated support: persist journal entries as /ledger/journal blob + genesis with real ledger_root
def make_v41_journal_persisted_image(output: Path, final_ws_root_hash: bytes, journal_entries: list, final_ledger_head: bytes):
    """Build image with genesis record (with ledger=final_head) + /ledger/journal record containing packed entries.
    journal_entries: list of canonical JRNLv41 bytes (from oracle).
    """
    image = bytearray(SECTOR_SIZE * SECTOR_COUNT)
    write_sector(image, 0, b"BOGV38IMG" + bytes(SECTOR_SIZE - 9))

    records = []
    lifecycle_id = 1
    for p in ["/apps", "/data", "/receipts", "/system", "/ledger"]:
        records.append(make_record(p, TYPE_DIRECTORY, lifecycle_id))
        lifecycle_id += 1

    data_lba = DATA_START_LBA
    # small seed
    seed = b"V41-JRNL"
    write_sector(image, data_lba, seed + bytes(SECTOR_SIZE - len(seed)))
    records.append(make_record("/data/seed.txt", TYPE_FILE, lifecycle_id, content=seed, data_lba=data_lba))
    lifecycle_id += 1
    data_lba += 1

    # genesis with real ledger for v41.1
    gen_content = genesis_root_bytes(final_ws_root_hash, ledger_root=final_ledger_head)
    gen_lba = data_lba
    write_sector(image, gen_lba, gen_content + bytes(SECTOR_SIZE - len(gen_content)))
    # build rec with correct content hash (the gen_content with ledger)
    gen_rec = bytearray(RECORD_SIZE)
    enc = b"/system/genesis_root"
    gen_rec[0:len(enc)] = enc
    gen_rec[len(enc)] = 0
    gen_rec[64:68] = (1).to_bytes(4, "little")
    gen_rec[68:72] = len(gen_content).to_bytes(4, "little")
    gen_rec[72:76] = gen_lba.to_bytes(4, "little")
    gen_rec[76:80] = V40_GENESIS_TYPE.to_bytes(4, "little")
    gen_rec[80:112] = sha256(gen_content)
    gen_rec[112:116] = lifecycle_id.to_bytes(4, "little")
    gen_rec[116:120] = (1).to_bytes(4, "little")
    records.append(bytes(gen_rec))
    lifecycle_id += 1
    data_lba += 1

    # journal blob (may span sectors)
    jblob = build_journal_blob(journal_entries)
    j_lba = data_lba
    for off in range(0, len(jblob), SECTOR_SIZE):
        chunk = jblob[off:off+SECTOR_SIZE]
        chunk += b"\0" * (SECTOR_SIZE - len(chunk))
        write_sector(image, j_lba + (off // SECTOR_SIZE), chunk)
    jrec, _, _ = make_journal_record(jblob, j_lba, lifecycle_id)
    records.append(jrec)
    lifecycle_id += 1
    data_lba += (len(jblob) + SECTOR_SIZE - 1) // SECTOR_SIZE

    manifest = make_manifest(1, data_lba, lifecycle_id, records)
    for i in range(MANIFEST_SECTORS):
        write_sector(image, 8 + i, manifest[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE])
    sb, mhash, rhash = make_superblock(1, 8, manifest)
    write_sector(image, SUPERBLOCK_A, sb)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {
        "image": str(output),
        "genesis_hash": sha256(gen_content).hex(),
        "ledger_head": final_ledger_head.hex(),
        "workspace_root_hash": final_ws_root_hash.hex(),
        "journal_blob_hash": sha256(jblob).hex(),
        "manifest_hash": mhash.hex(),
        "root_hash": rhash.hex(),
    }


def update_genesis_in_image(base_image: Path, output: Path, new_ws_root_hash: bytes):
    """Take a base image, update ONLY the genesis record + recompute manifest/super roots (simulates 'commit' of new root)."""
    img = bytearray(base_image.read_bytes())
    # Find the genesis record in manifest (assume at known offset after seeds; scan by path)
    manifest_lba = 8
    manifest = bytearray()
    for i in range(MANIFEST_SECTORS):
        manifest.extend(img[(manifest_lba + i) * SECTOR_SIZE:(manifest_lba + i + 1) * SECTOR_SIZE])
    record_count = int.from_bytes(manifest[12:16], "little")
    gen_idx = None
    for i in range(record_count):
        off = 64 + i * RECORD_SIZE
        rec = manifest[off:off + RECORD_SIZE]
        plen = 0
        while plen < 64 and rec[plen] != 0:
            plen += 1
        if rec[:plen] == V40_GENESIS_PATH.encode("ascii"):
            gen_idx = i
            break
    if gen_idx is None:
        raise AssertionError("no genesis record in base image")

    # allocate new data lba (append)
    next_free = int.from_bytes(manifest[16:20], "little")
    gen_lba = next_free
    gen_content = genesis_root_bytes(new_ws_root_hash)
    write_sector(img, gen_lba, gen_content + bytes(SECTOR_SIZE - len(gen_content)))

    # update the record
    off = 64 + gen_idx * RECORD_SIZE
    rec = bytearray(manifest[off:off + RECORD_SIZE])
    rec[68:72] = len(gen_content).to_bytes(4, "little")
    rec[72:76] = gen_lba.to_bytes(4, "little")
    rec[80:112] = sha256(gen_content)
    manifest[off:off + RECORD_SIZE] = rec

    # update manifest header
    new_count = record_count  # same count
    next_free2 = gen_lba + 1
    manifest[16:20] = next_free2.to_bytes(4, "little")
    # listing hash
    listing = sha256(b"".join([manifest[64 + j * RECORD_SIZE:64 + (j + 1) * RECORD_SIZE] for j in range(new_count)]))
    manifest[24:56] = listing

    # write back manifest sectors
    for i in range(MANIFEST_SECTORS):
        write_sector(img, manifest_lba + i, manifest[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE])

    # new superblock (increment generation for alternate root proof)
    old_gen = int.from_bytes(manifest[8:12], "little")
    new_gen = old_gen + 1
    manifest[8:12] = new_gen.to_bytes(4, "little")
    # rewrite manifest first? already did
    sb, mhash, rhash = make_superblock(new_gen, manifest_lba, bytes(manifest))
    write_sector(img, SUPERBLOCK_B, sb)  # use alt slot for "commit"

    # also update primary? for two-boot, the evaluator will choose highest gen
    # but to match v38 alternate, leave A, write B with new

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(img)
    return {
        "image": str(output),
        "genesis_hash": sha256(gen_content).hex(),
        "workspace_root_hash": new_ws_root_hash.hex(),
        "generation": new_gen,
        "manifest_hash": mhash.hex(),
        "root_hash": rhash.hex(),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ARTIFACTS / "bogos_v40_genesis_base.img")
    ap.add_argument("--blank-ws", type=str, default="c6523f9cccf33ebbd6a40db755c2e4a6efee9d89e628bb3c720716f19bfaf8dc")
    args = ap.parse_args()
    ws0 = bytes.fromhex(args.blank_ws)
    info = make_v40_base_image(args.out, ws0)
    print(json.dumps(info, indent=2))