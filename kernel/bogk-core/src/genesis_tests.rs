use super::*;

fn receipt(old: u8, new: u8) -> WorkspaceReceipt {
    WorkspaceReceipt { receipt_version: 1, operation_hash: Hash32([9;32]),
        old_workspace_root: Hash32([old;32]), new_workspace_root: Hash32([new;32]),
        verifier_hash: Hash32([8;32]), accepted: true }
}
fn entry(seq: u64, prev: Hash32, old: u8, new: u8) -> WorkspaceJournalEntry {
    WorkspaceJournalEntry { seq, previous_journal_entry: prev,
        receipt: receipt(old,new), workspace_root_after: Hash32([new;32]) }
}
#[test]
fn genesis_roundtrip_preserves_distinct_fields_and_hashes_full_record() {
    let g=make_genesis_root(Hash32([0xa5;32]));
    let mut b=[0;277];
    assert_eq!(g.write_canonical(&mut b),Ok(277));
    assert_eq!(parse_genesis_root(&b),Ok(g));
    assert_eq!(g.compute_hash().0,sha256_standard(&b));
}
#[test]
fn genesis_parser_rejects_trailing_bytes_and_unknown_version() {
    let g=make_genesis_root(Hash32([1;32]));
    let mut b=[0;278];g.write_canonical(&mut b).unwrap();
    assert!(parse_genesis_root(&b).is_err());
    b[17]=2;
    assert!(parse_genesis_root(&b[..277]).is_err());
}
#[test]
fn journal_matches_python_canonical_seven_byte_tag() {
    let e=entry(1,Hash32::ZERO,1,2);
    let mut b=[0;256];let n=e.write_canonical(&mut b).unwrap();
    assert_eq!(n,212);
    assert_eq!(&b[..7],b"JRNLv41");
    assert_eq!(parse_journal_entry(&b[..n]),Ok(e));
    assert_eq!(e.compute_hash().0,sha256_standard(&b[..n]));
}
#[test]
fn journal_parser_rejects_noncanonical_records() {
    let e=entry(1,Hash32::ZERO,1,2);
    let mut b=[0;256];let n=e.write_canonical(&mut b).unwrap();
    assert!(parse_journal_entry(&b[..n-1]).is_err());
    assert!(parse_journal_entry(&b[..n+1]).is_err());
    b[7+8+32+4+128]=2;
    assert!(parse_journal_entry(&b[..n]).is_err());
    b[7+8+32+4+128]=1;b[7+8+32]=2;
    assert!(parse_journal_entry(&b[..n]).is_err());
}
#[test]
fn journal_rejects_rehashed_semantic_corruption() {
    let a=entry(1,Hash32::ZERO,1,2);
    let b=entry(2,a.compute_hash(),2,3);
    assert!(verify_journal_chain(b.compute_hash(),&[a,b]));
    for changed in [entry(1,Hash32([7;32]),1,2),entry(0,Hash32::ZERO,1,2)] {
        assert!(!verify_journal_chain(changed.compute_hash(),&[changed]));
    }
    for mut bad in [entry(3,a.compute_hash(),2,3),entry(2,a.compute_hash(),7,3),b] {
        // Each case below separately exercises a semantic invariant.
        if bad==b { bad.workspace_root_after=Hash32([4;32]); }
        assert!(!verify_journal_chain(bad.compute_hash(),&[a,bad]));
    }
    let mut bad=b;bad.receipt.accepted=false;
    assert!(!verify_journal_chain(bad.compute_hash(),&[a,bad]));
    let mut bad=b;bad.receipt.receipt_version=2;
    assert!(!verify_journal_chain(bad.compute_hash(),&[a,bad]));
    assert!(!verify_journal_chain(a.compute_hash(),&[b,a]));
    assert!(!verify_journal_chain(b.compute_hash(),&[b]));
}
#[test]
fn workspace_rollback_requires_a_materialized_snapshot() {
    let s=make_initial_workspace_state();
    let op=WorkspaceOperation {op_version:1,op_kind:WorkspaceOpKind::Rollback,
        old_workspace_root:s.root.compute_hash(),target_path_hash:Hash32::ZERO,
        input_content_hash:Hash32([99;32]),input_size_bytes:0,
        capability_hash:v40_write_cap_sentinel(),tool_receipt_hash:Hash32::ZERO};
    assert!(apply_workspace_operation(&s,&op,b"").is_err());
}

#[test]
fn journal_blob_requires_exact_framing_and_genesis_agreement() {
    let e=entry(1,Hash32::ZERO,1,2);
    let mut blob=[0u8;218];
    blob[..4].copy_from_slice(&1u32.to_le_bytes());
    blob[4..6].copy_from_slice(&212u16.to_le_bytes());
    e.write_canonical(&mut blob[6..]).unwrap();
    let summary=verify_workspace_journal_blob(&blob,e.compute_hash(),Hash32([2;32])).unwrap();
    assert_eq!(summary.count,1);
    assert!(!summary.rollback_present);
    assert!(verify_workspace_journal_blob(&blob,e.compute_hash(),Hash32([3;32])).is_err());
    assert!(verify_workspace_journal_blob(&blob[..217],e.compute_hash(),Hash32([2;32])).is_err());
    blob[..4].copy_from_slice(&0u32.to_le_bytes());
    assert!(verify_workspace_journal_blob(&blob,Hash32::ZERO,Hash32([2;32])).is_err());
}

#[test]
fn rollback_journal_target_must_have_appeared_in_history() {
    let a=entry(1,Hash32::ZERO,1,2);
    let (mut b,_,_)=create_rollback_journal_entry(a.compute_hash(),2,Hash32([2;32]),Hash32([1;32]),Hash32::ZERO);
    assert!(verify_journal_chain(b.compute_hash(),&[a,b]));
    b.receipt.new_workspace_root=Hash32([77;32]);b.workspace_root_after=Hash32([77;32]);
    assert!(!verify_journal_chain(b.compute_hash(),&[a,b]));
}

#[test]
fn canonical_records_match_independent_python_bytes_and_hashes() {
    let vectors:serde_json::Value=serde_json::from_str(include_str!("../../fixtures/genesis_canonical.json")).unwrap();
    fn hex(bytes:&[u8])->std::string::String {
        bytes.iter().map(|b|std::format!("{:02x}",b)).collect()
    }
    let mut bytes=[0u8;277];
    make_genesis_root(Hash32([165;32])).write_canonical(&mut bytes).unwrap();
    assert_eq!(hex(&bytes),vectors["genesis"]["hex"].as_str().unwrap());
    assert_eq!(hex(&sha256_standard(&bytes)),vectors["genesis"]["sha256"].as_str().unwrap());
    let n=entry(1,Hash32::ZERO,1,2).write_canonical(&mut bytes).unwrap();
    assert_eq!(hex(&bytes[..n]),vectors["journal"]["hex"].as_str().unwrap());
    assert_eq!(hex(&sha256_standard(&bytes[..n])),vectors["journal"]["sha256"].as_str().unwrap());
}
