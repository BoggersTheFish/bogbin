"""Bounded, read-only QEMU validation of v41 storage; retains raw positive/negative logs.

No claims about applying mutations in the kernel or recovering file-content snapshots.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from make_v40_genesis_workspace_root_image import make_v41_journal_persisted_image
from make_v38_file_lifecycle_image import make_manifest, make_superblock, MANIFEST_SECTORS, SUPERBLOCK_A
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kernel/tools"))
from gen_v40_workspace_vectors import journal_entry_bytes


def h(data):
    return hashlib.sha256(data).digest()


def fixture(case):
    # Intentionally independent, arbitrary roots: no output may hardcode a fixture root.
    roots = [h(b"genesis-a"), h(b"created-b"), h(b"edited-c")]
    entries = []
    head = bytes(32)
    transitions = [(roots[0], roots[1], h(b"create")),
                   (roots[1], roots[2], h(b"edit")),
                   (roots[2], roots[1], h(b"v41-rollback-op"))]
    for i, (old, new, op) in enumerate(transitions):
        seq = i + 1
        prev = head
        if case == "nonzero_anchor" and i == 0:
            prev = h(b"not-genesis")
        if case == "broken_link" and i == 1:
            prev = bytes(32)
        if case == "wrong_sequence" and i == 1:
            seq = 9
        if case == "root_discontinuity" and i == 1:
            old = h(b"unrelated")
        if case == "unknown_rollback_target" and i == 2:
            new = h(b"never-seen")
        e = bytearray(journal_entry_bytes(seq, prev, op, old, new, h(b"verifier"), True))
        if case == "invalid_boolean" and i == 1:
            e[179] = 2
        if case == "unknown_receipt_version" and i == 1:
            e[47:51] = (2).to_bytes(4, "little")
        if case == "root_after_mismatch" and i == 1:
            e[-32:] = h(b"inconsistent")
        if case == "rejected_mutation" and i == 1:
            e[179] = 0
        head = h(e)
        entries.append(bytes(e))
    final = entries[-1][-32:]
    if case == "genesis_workspace_mismatch":
        final = h(b"wrong-workspace")
    if case == "wrong_head":
        head = h(b"wrong-head")
    if case == "entry_trailing_byte":
        entries[1] += b"\0"
    if case == "empty_journal":
        # No entries and a nonzero head must never produce a success marker.
        entries = []
    return final, entries, head


def mutate_storage(image, case):
    data = bytearray(image.read_bytes())
    manifest = data[8*512:(8+MANIFEST_SECTORS)*512]
    records = [bytes(manifest[64+i*128:64+(i+1)*128]) for i in range(int.from_bytes(manifest[12:16],"little"))]
    index = next(i for i,r in enumerate(records) if r[:64].split(b"\0")[0] == b"/ledger/journal")
    record = bytearray(records[index])
    length = int.from_bytes(record[68:72],"little")
    lba = int.from_bytes(record[72:76],"little")
    if case in {"absent_journal_record", "invalid_genesis_without_journal"}:
        records.pop(index)
        if case == "invalid_genesis_without_journal":
            gi = next(i for i,r in enumerate(records) if r[:64].split(b"\0")[0] == b"/system/genesis_root")
            gr = bytearray(records[gi])
            goff = int.from_bytes(gr[72:76],"little")*512
            data[goff+17:goff+21] = (2).to_bytes(4,"little")
            glen = int.from_bytes(gr[68:72],"little")
            gr[80:112] = h(data[goff:goff+glen])
            records[gi] = bytes(gr)
    elif case == "journal_tombstone":
        record[76:80] = (3).to_bytes(4,"little")
        records[index] = bytes(record)
    elif case == "journal_span_out_of_bounds":
        record[72:76] = (int.from_bytes(manifest[16:20],"little")-1).to_bytes(4,"little")
        records[index] = bytes(record)
    elif case == "journal_nonzero_padding":
        data[lba*512+length] = 1
    elif case == "journal_content_corruption":
        data[lba*512+20] ^= 1
    else:
        return
    manifest = make_manifest(1,int.from_bytes(manifest[16:20],"little"),int.from_bytes(manifest[20:24],"little"),records)
    data[8*512:(8+MANIFEST_SECTORS)*512] = manifest
    sb,_,_ = make_superblock(1,8,manifest)
    data[SUPERBLOCK_A*512:(SUPERBLOCK_A+1)*512] = sb
    image.write_bytes(data)


def run_case(kernel, directory, case):
    final, entries, head = fixture(case)
    image = directory / (("positive" if case == "positive_reboot" else case) + ".img")
    log = directory / (case + ".serial")
    if case != "positive_reboot":
        make_v41_journal_persisted_image(image, final, entries, head)
        mutate_storage(image,case)
    before = h(image.read_bytes()).hex()
    if log.exists():
        log.unlink()
    command = ["qemu-system-i386", "-kernel", str(kernel), "-serial", "file:"+str(log),
               "-display", "none", "-monitor", "none", "-no-reboot", "-no-shutdown",
               "-drive", f"file={image},format=raw,if=ide,index=0,media=disk"]
    start = time.monotonic()
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as proc:
        try:
            while time.monotonic()-start < 15:
                if log.exists() and b"BOGOS_V38_INVARIANTS_END" in log.read_bytes():
                    break
                if proc.poll() is not None:
                    break
                time.sleep(.02)
        finally:
            proc.terminate()
            try:
                _, stderr = proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, stderr = proc.communicate(timeout=3)
    raw = log.read_bytes() if log.exists() else b""
    text = raw.decode(errors="replace")
    success = ("V41_JOURNAL_LOADED count=3 verify_chain=true" in text and
               "FINAL_ROOT_AFTER="+final.hex() in text and
               "ROLLBACK_PRESENT_IN_HISTORY=true" in text)
    rejected = "V41_JOURNAL_REJECTED reason=validation_failed" in text
    mount = text.split("BOGOS_V38_MOUNT_BEGIN\n")[-1].split("BOGOS_V38_MOUNT_END")[0]
    storage_rejected = "STATUS=rejected\nREJECT_REASON=no_valid_root" in mount
    # Semantic negatives retain valid outer storage checksums and reach the journal validator.
    passed = (success and not rejected) if case.startswith("positive") else (rejected and "verify_chain=true" not in text)
    if case in {"journal_span_out_of_bounds", "journal_nonzero_padding", "journal_content_corruption"}:
        passed = storage_rejected and "verify_chain=true" not in text
    passed = passed and before == h(image.read_bytes()).hex() and "BOGOS_V38_INVARIANTS_END" in text
    return dict(case=case, passed=passed, success=success, rejected=rejected,
                seconds=round(time.monotonic()-start,4), image_sha256=before,
                serial_sha256=h(raw).hex(), stderr=stderr.decode(errors="replace"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=ROOT/"kernel/target/i686-unknown-linux-musl/debug/bogk-kernel")
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/genesis-journal")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.kernel.is_file():
        parser.error("build the i686 kernel first")
    cases = ["positive", "positive_reboot", "nonzero_anchor", "broken_link", "wrong_sequence",
             "root_discontinuity", "unknown_rollback_target", "invalid_boolean", "unknown_receipt_version",
             "root_after_mismatch", "rejected_mutation", "genesis_workspace_mismatch", "wrong_head",
             "entry_trailing_byte", "empty_journal", "absent_journal_record",
             "journal_span_out_of_bounds", "journal_nonzero_padding", "journal_content_corruption", "journal_tombstone", "invalid_genesis_without_journal"]
    rows = []
    for case in cases:
        row = run_case(args.kernel.resolve(), args.output.resolve(), case)
        rows.append(row)
        print(case, "PASS" if row["passed"] else "FAIL", flush=True)
    report = dict(format="genesis-journal-evidence-v1", kernel_sha256=h(args.kernel.read_bytes()).hex(),
                  cases=rows, passed=all(r["passed"] for r in rows),
                  scope="read-only structural validation of host-built storage; no snapshot recovery proof")
    (args.output/"results.json").write_text(json.dumps(report, indent=2)+"\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
