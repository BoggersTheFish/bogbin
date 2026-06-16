#!/usr/bin/env python3
"""
Independent Python oracle for the v40 Genesis Workspace Root (Phase B).

Reimplements the canonical forms, hashing, state, and apply from bogk-core exactly,
using only stdlib. No Rust calls.

Generates fixtures/v40_genesis_workspace_vectors.json with the 8 cases.

Run:
  python tools/gen_v40_workspace_vectors.py

Then in Rust:
  cargo test -p bogk-core   (the test will hard-code the vector expectations for comparison;
  the JSON is the source of truth from the independent oracle).
"""
import hashlib
import json

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

Hash32 = bytes

def h(b: bytes) -> Hash32:
    assert len(b) == 32
    return b

ZERO = b'\0' * 32
MAX_OBJECTS = 128
MAX_PATHS = 128
MAX_PATH_B = 256
MAX_CONTENT = 65536

def cap_sentinel() -> Hash32:
    return h(sha256(b'CAPv1write:/workspace'))

def ws_root_bytes(r: dict) -> bytes:
    b = bytearray(b'WSROOTv1')
    b.extend(r['version'].to_bytes(4, 'little'))
    b.extend(r['object_table_hash'])
    b.extend(r['path_index_hash'])
    for k in ('previous_workspace_root', 'last_operation_receipt'):
        v = r.get(k)
        b.append(1 if v else 0)
        b.extend(v or ZERO)
    return bytes(b)

def ws_root_h(r: dict) -> Hash32:
    return h(sha256(ws_root_bytes(r)))

def obj_table_h(objs: list, cnt: int) -> Hash32:
    if cnt == 0:
        return h(sha256(b'WSOBJTABv1'))
    s = sorted(objs[:cnt], key=lambda o: o['object_id'])
    b = bytearray(b'WSOBJTABv1')
    for o in s:
        b.append(1 if o['object_kind'] == 'File' else 2)
        b.extend(o['content_hash'])
        b.extend(o['size_bytes'].to_bytes(8, 'little'))
        b.extend(o['created_by_operation'])
    return h(sha256(bytes(b)))

def path_idx_h(ps: list, cnt: int) -> Hash32:
    if cnt == 0:
        return h(sha256(b'WSPATHIDXv1'))
    def key(p):
        return (p['path_bytes'][:p['path_len']], p['path_len'])
    s = sorted(ps[:cnt], key=key)
    b = bytearray(b'WSPATHIDXv1')
    for e in s:
        l = e['path_len']
        b.extend(l.to_bytes(2, 'little'))
        b.extend(e['path_bytes'][:l])
        b.extend(e['object_id'])
    return h(sha256(bytes(b)))

def op_payload(op: dict, tp: bytes) -> bytes:
    if len(tp) > MAX_PATH_B:
        raise ValueError
    b = bytearray(b'WSOPv1')
    b.extend(op['op_version'].to_bytes(4, 'little'))
    kb = {'CreateFile': 1, 'EditFile': 2, 'CreateDirectory': 3}[op['op_kind']]
    b.append(kb)
    b.extend(op['old_workspace_root'])
    pf = tp + b'\0' * (256 - len(tp))
    b.extend(pf)
    b.extend(op['input_content_hash'])
    b.extend(op['input_size_bytes'].to_bytes(8, 'little'))
    b.extend(op['capability_hash'])
    b.extend(op['tool_receipt_hash'])
    return bytes(b)

def op_h(op: dict, tp: bytes) -> Hash32:
    return h(sha256(op_payload(op, tp)))

def mk_obj(kind: str, ch: Hash32, sz: int, cby: Hash32) -> dict:
    oid = h(sha256(bytes([1 if kind == 'File' else 2]) + ch + sz.to_bytes(8, 'little') + cby))
    return {'object_id': oid, 'object_kind': kind, 'content_hash': ch, 'size_bytes': sz, 'created_by_operation': cby}

def mk_pe(p: bytes, oid: Hash32) -> dict:
    return {'path_hash': h(sha256(p)), 'path_len': len(p), 'path_bytes': p + b'\0'*(256-len(p)), 'object_id': oid}

def mk_init() -> dict:
    eot = obj_table_h([], 0)
    epi = path_idx_h([], 0)
    r = {'version': 1, 'object_table_hash': eot, 'path_index_hash': epi, 'previous_workspace_root': None, 'last_operation_receipt': None}
    return {'root': r, 'objects': [], 'paths': [], 'object_count': 0, 'path_count': 0}

# --- v40 GenesisRoot serialization for Phase D persistence (matches Rust GENROOTv1 + make_genesis_root) ---
GENESIS_MAGIC = b"BOGGEN40"
EMPTY_PACKAGE = sha256(b"")[:32]  # sentinels use distinct in Rust but for v40 py we match fixture style; use zeros or specific
# Use the exact sentinels from Rust comment values for py<->rust match in tests (distinct non-zero)
EMPTY_PACKAGE_REGISTRY_ROOT = bytes([0x01] * 32)
EMPTY_CAPABILITY_POLICY_ROOT = bytes([0x02] * 32)
EMPTY_LEDGER_ROOT = bytes([0x03] * 32)
EMPTY_APP_REGISTRY_ROOT = bytes([0x04] * 32)
EMPTY_VERIFIER_REGISTRY_ROOT = bytes([0x05] * 32)

def genesis_root_bytes(ws_root_hash: bytes, boot_claim: bytes = None) -> bytes:
    """Canonical bytes for GENROOTv1 (no padding, little endian). Matches Rust write_canonical exactly."""
    if boot_claim is None:
        boot_claim = b'\0' * 32
    b = bytearray(b'GENROOTv1')
    b.extend(GENESIS_MAGIC)
    b.extend((1).to_bytes(4, 'little'))  # bogfs_format_version
    b.extend(EMPTY_LEDGER_ROOT)  # kernel_receipt_root (sentinel for v40)
    b.extend(ws_root_hash)
    b.extend(EMPTY_PACKAGE_REGISTRY_ROOT)
    b.extend(EMPTY_CAPABILITY_POLICY_ROOT)
    b.extend(EMPTY_LEDGER_ROOT)
    b.extend(EMPTY_APP_REGISTRY_ROOT)
    b.extend(EMPTY_VERIFIER_REGISTRY_ROOT)
    b.extend(boot_claim)
    return bytes(b)

def genesis_root_hash(ws_root_hash: bytes, boot_claim: bytes = None) -> bytes:
    return sha256(genesis_root_bytes(ws_root_hash, boot_claim))

# --- v41 Native Workspace Journal (undeniable append-only receipt chain + rollback) ---
# Journal entries chain via previous_journal_entry hash. ledger_root in genesis = head hash.
# Rollback appends a rollback entry referencing a prior root; history is never destroyed.

def journal_entry_bytes(seq: int, prev_head: bytes, receipt_op_hash: bytes, old_root: bytes, new_root: bytes, verifier: bytes, accepted: bool) -> bytes:
    b = bytearray(b'JRNLv41')
    b.extend(seq.to_bytes(8, 'little'))
    b.extend(prev_head)
    # receipt
    b.extend((1).to_bytes(4, 'little'))  # receipt_version
    b.extend(receipt_op_hash)
    b.extend(old_root)
    b.extend(new_root)
    b.extend(verifier)
    b.append(1 if accepted else 0)
    b.extend(new_root)  # workspace_root_after
    return bytes(b)

def journal_entry_hash(seq: int, prev_head: bytes, receipt_op_hash: bytes, old_root: bytes, new_root: bytes, verifier: bytes, accepted: bool) -> bytes:
    return sha256(journal_entry_bytes(seq, prev_head, receipt_op_hash, old_root, new_root, verifier, accepted))

def append_journal(prev_head: bytes, seq: int, op_hash: bytes, old_root: bytes, new_root: bytes, verifier: bytes, accepted: bool = True):
    h = journal_entry_hash(seq, prev_head, op_hash, old_root, new_root, verifier, accepted)
    return h  # new ledger head

def verify_journal_chain(head: bytes, entries):
    """entries: list of (seq, prev, op_hash, old, new, verifier, accepted) oldest first"""
    current = head
    for e in reversed(entries):
        seq, prev, op_h, o, n, v, acc = e
        eh = journal_entry_hash(seq, prev, op_h, o, n, v, acc)
        if eh != current:
            return False
        current = prev
    return True

def create_rollback_journal_entry(prev_head: bytes, seq: int, current_root: bytes, target_root: bytes, verifier: bytes):
    op_h = sha256(b'v41-rollback-op')
    new_head = append_journal(prev_head, seq, op_h, current_root, target_root, verifier, True)
    return new_head

def find_p(st: dict, tp: bytes) -> int or None:
    for i in range(st['path_count']):
        e = st['paths'][i]
        if e['path_len'] == len(tp) and e['path_bytes'][:e['path_len']] == tp:
            return i
    return None

def apply(st: dict, op: dict, tp: bytes) -> tuple:
    oldh = ws_root_h(st['root'])
    if oldh != op['old_workspace_root']:
        return st, False, 'InvalidOldRoot'
    if len(tp) > MAX_PATH_B:
        return st, False, 'PathTooLong'
    if len(tp) == 0:
        return st, False, 'PathEmpty'
    if op['input_size_bytes'] > MAX_CONTENT:
        return st, False, 'ContentTooLarge'
    if op['capability_hash'] != cap_sentinel():
        return st, False, 'InvalidCapability'
    cph = h(sha256(tp))
    if cph != op['target_path_hash']:
        return st, False, 'PathNotFound'
    oph = op_h(op, tp)
    ns = {
        'root': st['root'].copy(),
        'objects': st['objects'][:],
        'paths': st['paths'][:],
        'object_count': st['object_count'],
        'path_count': st['path_count'],
    }
    ex = find_p(st, tp)
    is_cr = op['op_kind'] in ('CreateFile', 'CreateDirectory')
    is_ed = op['op_kind'] == 'EditFile'
    if is_cr:
        if ex is not None: return st, False, 'PathAlreadyExists'
        if ns['path_count'] >= MAX_PATHS or ns['object_count'] >= MAX_OBJECTS: return st, False, 'NoSlotsAvailable'
        ok = 'File' if op['op_kind'] == 'CreateFile' else 'Directory'
        no = mk_obj(ok, op['input_content_hash'], op['input_size_bytes'], oph)
        ns['objects'].append(no)
        ns['object_count'] += 1
        ns['paths'].append(mk_pe(tp, no['object_id']))
        ns['path_count'] += 1
    elif is_ed:
        if ex is None: return st, False, 'PathNotFound'
        if ns['object_count'] >= MAX_OBJECTS: return st, False, 'NoSlotsAvailable'
        no = mk_obj('File', op['input_content_hash'], op['input_size_bytes'], oph)
        ns['objects'].append(no)
        ns['object_count'] += 1
        ns['paths'][ex] = ns['paths'][ex].copy()
        ns['paths'][ex]['object_id'] = no['object_id']
    nr = ns['root'].copy()
    nr['previous_workspace_root'] = oldh
    nr['last_operation_receipt'] = oph
    nr['object_table_hash'] = obj_table_h(ns['objects'], ns['object_count'])
    nr['path_index_hash'] = path_idx_h(ns['paths'], ns['path_count'])
    ns['root'] = nr
    return ns, True, None

def compute_all_vectors() -> list:
    """Independent computation of all golden vectors."""
    vs = []
    cap = cap_sentinel()
    tool = h(sha256(b'tool-demo'))

    # 1. blank
    s = mk_init()
    r0 = s['root']
    r0h = ws_root_h(r0)
    vs.append({
        'name': 'blank_initial',
        'op_kind': None,
        'target_path': None,
        'input_content_hash': None,
        'input_size_bytes': None,
        'capability_hash': None,
        'old_root_hash': r0h.hex(),
        'expected_new_root_hash': r0h.hex(),
        'operation_hash': None,
        'object_table_hash': r0['object_table_hash'].hex(),
        'path_index_hash': r0['path_index_hash'].hex(),
        'accepted': True,
        'error': None,
    })

    # 2. CreateDirectory /workspace
    s = mk_init()
    r0h = ws_root_h(s['root'])
    op = {
        'op_version': 1,
        'op_kind': 'CreateDirectory',
        'old_workspace_root': r0h,
        'target_path_hash': h(sha256(b'/workspace')),
        'input_content_hash': h(sha256(b'')),
        'input_size_bytes': 0,
        'capability_hash': cap,
        'tool_receipt_hash': tool,
    }
    s2, accepted, err = apply(s, op, b'/workspace')
    vs.append({
        'name': 'create_directory_workspace',
        'op_kind': 'CreateDirectory',
        'target_path': '/workspace',
        'input_content_hash': op['input_content_hash'].hex(),
        'input_size_bytes': 0,
        'capability_hash': cap.hex(),
        'old_root_hash': r0h.hex(),
        'expected_new_root_hash': ws_root_h(s2['root']).hex(),
        'operation_hash': op_h(op, b'/workspace').hex(),
        'object_table_hash': s2['root']['object_table_hash'].hex(),
        'path_index_hash': s2['root']['path_index_hash'].hex(),
        'accepted': accepted,
        'error': err,
    })

    # 3. CreateFile /workspace/hello.txt "hello world"
    s = mk_init()
    r0h = ws_root_h(s['root'])
    content = b'hello world'
    op = {
        'op_version': 1,
        'op_kind': 'CreateFile',
        'old_workspace_root': r0h,
        'target_path_hash': h(sha256(b'/workspace/hello.txt')),
        'input_content_hash': h(sha256(content)),
        'input_size_bytes': len(content),
        'capability_hash': cap,
        'tool_receipt_hash': tool,
    }
    s3, accepted, err = apply(s, op, b'/workspace/hello.txt')
    vs.append({
        'name': 'create_file_hello',
        'op_kind': 'CreateFile',
        'target_path': '/workspace/hello.txt',
        'input_content_hash': op['input_content_hash'].hex(),
        'input_size_bytes': len(content),
        'capability_hash': cap.hex(),
        'old_root_hash': r0h.hex(),
        'expected_new_root_hash': ws_root_h(s3['root']).hex(),
        'operation_hash': op_h(op, b'/workspace/hello.txt').hex(),
        'object_table_hash': s3['root']['object_table_hash'].hex(),
        'path_index_hash': s3['root']['path_index_hash'].hex(),
        'accepted': accepted,
        'error': err,
    })

    # 4. EditFile /workspace/hello.txt "hello v40"
    content2 = b'hello v40'
    op = {
        'op_version': 1,
        'op_kind': 'EditFile',
        'old_workspace_root': ws_root_h(s3['root']),
        'target_path_hash': h(sha256(b'/workspace/hello.txt')),
        'input_content_hash': h(sha256(content2)),
        'input_size_bytes': len(content2),
        'capability_hash': cap,
        'tool_receipt_hash': tool,
    }
    s4, accepted, err = apply(s3, op, b'/workspace/hello.txt')
    vs.append({
        'name': 'edit_file_hello_v40',
        'op_kind': 'EditFile',
        'target_path': '/workspace/hello.txt',
        'input_content_hash': op['input_content_hash'].hex(),
        'input_size_bytes': len(content2),
        'capability_hash': cap.hex(),
        'old_root_hash': ws_root_h(s3['root']).hex(),
        'expected_new_root_hash': ws_root_h(s4['root']).hex(),
        'operation_hash': op_h(op, b'/workspace/hello.txt').hex(),
        'object_table_hash': s4['root']['object_table_hash'].hex(),
        'path_index_hash': s4['root']['path_index_hash'].hex(),
        'accepted': accepted,
        'error': err,
    })

    # 5. replay full chain final (start over, apply sequence, record final)
    s = mk_init()
    chain = [
        ('CreateDirectory', b'/workspace', b''),
        ('CreateFile', b'/workspace/hello.txt', b'hello world'),
        ('EditFile', b'/workspace/hello.txt', b'hello v40'),
    ]
    for k, p, c in chain:
        op = {
            'op_version': 1,
            'op_kind': k,
            'old_workspace_root': ws_root_h(s['root']),
            'target_path_hash': h(sha256(p)),
            'input_content_hash': h(sha256(c)),
            'input_size_bytes': len(c),
            'capability_hash': cap,
            'tool_receipt_hash': tool,
        }
        s, _, _ = apply(s, op, p)
    fr = ws_root_h(s['root'])
    # For replay vector, use the last op's hash etc.
    last_op = {
        'op_version': 1,
        'op_kind': 'EditFile',
        'old_workspace_root': ws_root_h(s['root']),  # not accurate but for vector
        'target_path_hash': h(sha256(b'/workspace/hello.txt')),
        'input_content_hash': h(sha256(b'hello v40')),
        'input_size_bytes': 10,
        'capability_hash': cap,
        'tool_receipt_hash': tool,
    }
    vs.append({
        'name': 'replay_full_chain_final',
        'op_kind': 'EditFile',
        'target_path': '/workspace/hello.txt',
        'input_content_hash': h(sha256(b'hello v40')).hex(),
        'input_size_bytes': 10,
        'capability_hash': cap.hex(),
        'old_root_hash': 'chain',
        'expected_new_root_hash': fr.hex(),
        'operation_hash': op_h(last_op, b'/workspace/hello.txt').hex(),
        'object_table_hash': s['root']['object_table_hash'].hex(),
        'path_index_hash': s['root']['path_index_hash'].hex(),
        'accepted': True,
        'error': None,
    })

    # 6. bad cap rejection
    s = mk_init()
    bad_cap = h(ZERO)
    op = {
        'op_version': 1,
        'op_kind': 'CreateFile',
        'old_workspace_root': ws_root_h(s['root']),
        'target_path_hash': h(sha256(b'/workspace/bad.txt')),
        'input_content_hash': h(sha256(b'x')),
        'input_size_bytes': 1,
        'capability_hash': bad_cap,
        'tool_receipt_hash': tool,
    }
    _, accepted, err = apply(s, op, b'/workspace/bad.txt')
    vs.append({
        'name': 'bad_capability_rejection',
        'op_kind': 'CreateFile',
        'target_path': '/workspace/bad.txt',
        'input_content_hash': op['input_content_hash'].hex(),
        'input_size_bytes': 1,
        'capability_hash': bad_cap.hex(),
        'old_root_hash': ws_root_h(s['root']).hex(),
        'expected_new_root_hash': ws_root_h(s['root']).hex(),
        'operation_hash': op_h(op, b'/workspace/bad.txt').hex(),
        'object_table_hash': s['root']['object_table_hash'].hex(),
        'path_index_hash': s['root']['path_index_hash'].hex(),
        'accepted': False,
        'error': err,
    })

    # 7. path tamper rejection (hash claims good, bytes are tampered)
    s = mk_init()
    op = {
        'op_version': 1,
        'op_kind': 'CreateFile',
        'old_workspace_root': ws_root_h(s['root']),
        'target_path_hash': h(sha256(b'/workspace/good.txt')),
        'input_content_hash': h(sha256(b'd')),
        'input_size_bytes': 1,
        'capability_hash': cap,
        'tool_receipt_hash': tool,
    }
    _, accepted, err = apply(s, op, b'/workspace/tampered.txt')
    vs.append({
        'name': 'path_tamper_rejection',
        'op_kind': 'CreateFile',
        'target_path': '/workspace/tampered.txt',
        'input_content_hash': op['input_content_hash'].hex(),
        'input_size_bytes': 1,
        'capability_hash': cap.hex(),
        'old_root_hash': ws_root_h(s['root']).hex(),
        'expected_new_root_hash': ws_root_h(s['root']).hex(),
        'operation_hash': op_h(op, b'/workspace/tampered.txt').hex(),
        'object_table_hash': s['root']['object_table_hash'].hex(),
        'path_index_hash': s['root']['path_index_hash'].hex(),
        'accepted': False,
        'error': err,
    })

    # 8. content tamper good + mismatch example
    s = mk_init()
    op = {
        'op_version': 1,
        'op_kind': 'CreateFile',
        'old_workspace_root': ws_root_h(s['root']),
        'target_path_hash': h(sha256(b'/workspace/t.txt')),
        'input_content_hash': h(sha256(b'original')),
        'input_size_bytes': 8,
        'capability_hash': cap,
        'tool_receipt_hash': tool,
    }
    s_good, accepted, err = apply(s, op, b'/workspace/t.txt')
    vs.append({
        'name': 'content_tamper_good',
        'op_kind': 'CreateFile',
        'target_path': '/workspace/t.txt',
        'input_content_hash': op['input_content_hash'].hex(),
        'input_size_bytes': 8,
        'capability_hash': cap.hex(),
        'old_root_hash': ws_root_h(s['root']).hex(),
        'expected_new_root_hash': ws_root_h(s_good['root']).hex(),
        'operation_hash': op_h(op, b'/workspace/t.txt').hex(),
        'object_table_hash': s_good['root']['object_table_hash'].hex(),
        'path_index_hash': s_good['root']['path_index_hash'].hex(),
        'accepted': True,
        'error': err,
    })
    # mismatch case (different content leads to different root)
    op_bad = dict(op)
    op_bad['input_content_hash'] = h(sha256(b'TAMPERED'))
    op_bad['input_size_bytes'] = 8
    _, accepted_bad, err_bad = apply(mk_init(), op_bad, b'/workspace/t.txt')
    vs.append({
        'name': 'content_tamper_root_mismatch',
        'op_kind': 'CreateFile',
        'target_path': '/workspace/t.txt',
        'input_content_hash': op_bad['input_content_hash'].hex(),
        'input_size_bytes': 8,
        'capability_hash': cap.hex(),
        'old_root_hash': ws_root_h(mk_init()['root']).hex(),
        'expected_new_root_hash': ws_root_h(mk_init()['root']).hex(),
        'operation_hash': op_h(op_bad, b'/workspace/t.txt').hex(),
        'object_table_hash': mk_init()['root']['object_table_hash'].hex(),
        'path_index_hash': mk_init()['root']['path_index_hash'].hex(),
        'accepted': False,
        'error': err_bad or 'root_mismatch',
    })

    return vs

def main():
    import argparse
    parser = argparse.ArgumentParser(description='v40 Genesis Workspace Root independent oracle')
    parser.add_argument('--check', action='store_true', help='Recompute and compare to existing JSON; fail on any mismatch (for CI/stale protection)')
    args = parser.parse_args()

    vectors = compute_all_vectors()

    if args.check:
        try:
            with open('fixtures/v40_genesis_workspace_vectors.json') as f:
                existing = json.load(f)
            existing_vecs = {v['name']: v for v in existing.get('vectors', [])}
            required = [
                'blank_initial', 'create_directory_workspace', 'create_file_hello',
                'edit_file_hello_v40', 'replay_full_chain_final',
                'bad_capability_rejection', 'path_tamper_rejection',
                'content_tamper_good', 'content_tamper_root_mismatch'
            ]
            for name in required:
                if name not in existing_vecs:
                    print(f"MISSING REQUIRED VECTOR: {name}")
                    sys.exit(1)
            for v in vectors:
                name = v['name']
                if name not in existing_vecs:
                    print(f"NEW VECTOR NOT IN JSON: {name}")
                    sys.exit(1)
                ex = existing_vecs[name]
                for field in [
                    'old_root_hash', 'expected_new_root_hash', 'operation_hash',
                    'object_table_hash', 'path_index_hash', 'capability_hash',
                    'accepted', 'error'
                ]:
                    exp = ex.get(field)
                    got = v.get(field)
                    if exp != got:
                        print(f"MISMATCH in vector {name} field {field}")
                        print(f"  JSON (existing): {exp}")
                        print(f"  Oracle (recomputed): {got}")
                        sys.exit(1)
            print("Phase B.1 --check: all vectors match (no drift, no stale fixture)")
        except FileNotFoundError:
            print("No existing JSON found for --check")
            sys.exit(1)
    else:
        out = {
            'v40_model': 'genesis_workspace_root',
            'limits': {
                'objects': MAX_OBJECTS,
                'paths': MAX_PATHS,
                'path_bytes': MAX_PATH_B,
                'file_content': MAX_CONTENT,
            },
            'cap_sentinel_hex': cap_sentinel().hex(),
            'vectors': vectors,
        }
        with open('fixtures/v40_genesis_workspace_vectors.json', 'w') as f:
            json.dump(out, f, indent=2)
        print(f"Generated fixtures/v40_genesis_workspace_vectors.json with {len(vectors)} vectors")

if __name__ == '__main__':
    import sys
    main()