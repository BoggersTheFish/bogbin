# Bog v10.0.0 Threat Model

## Security Claim

Bog is a user-space verification and policy system for workspace operations. BogK is a **user-space kernel contract for verified workspace operations**. It is not a host kernel, container runtime, or syscall sandbox.

A completed receipt is evidence that the named Bog checks completed for the exact hashes, signatures, manifests, capabilities, policies, and delegated receipts recorded in it.

## What Bog Defends Against

- Corrupted or tampered `.bog`, `.bogpk`, archive objects, archive manifests, package bundles, and installed package trees.
- Structurally invalid archive manifests, package receipts, app manifests, decoded BOGPK metadata, and kernel receipts.
- Unsigned packages or packages signed outside the workspace trust store when signature enforcement is enabled.
- Missing, cyclic, corrupted, or untrusted declared package dependencies.
- App files whose hashes do not match `bog_app.json`.
- App package mutation detected before, during, or after a verified run.
- Runtime writes visible in the app runtime directory but not declared by app policy.
- BogK requests for unknown apps, unknown mounts, unsafe paths, or undeclared writes.
- Brokered Bog-native reads, writes, environment requests, and dependency requests outside the declared capability manifest. These are blocked before the broker performs access.
- Unsafe, escaping, or symlink-replaced broker read/write targets.
- Replay divergence in package/tree hashes, app policy, syscall sequence/evidence, brokered output hashes, or the final proof hash.
- Edited, deleted, inserted, or reordered Genesis session receipts through signed append-only ledger verification.
- Registry package metadata, signature, or bundle-content tampering and lockfile divergence.
- Genesis writable-state divergence through immutable objects, copy-on-write manifests, rollback roots, and session replay.
- Unauthorized BogCell I/O: the VM instruction set contains no raw filesystem, network, subprocess, or native-call operation.
- Portable-proof mutation through bundle file hashes plus signed registry, lockfile, package, ledger, final-receipt, state-root, and object verification.
- Unsafe AI/planner proposals: BogPilot proposals are untrusted candidates and receive no authority outside verified Bog actions.

## What Bog Does Not Defend Against

- A malicious native process escaping Bog policy through host syscalls, subprocesses, network access, ptrace, kernel exploits, or writes outside paths Bog observes.
- A compromised host OS, Python runtime, Bog implementation, cryptographic library, private signing key, or trusted-key store.
- Freshness, revocation, remote-transparency-log, or remote-registry transport attacks. Genesis provides a local signed transparency ledger and local signed registry.
- Confidentiality, denial of service, resource exhaustion, or side channels.
- The truth of human claims. Bog proves bytes, signatures, declared checks, and receipt linkage, not intent, legality, or safety.

Runtime policy is not sandboxing. Post-run write checks can reject and prove an undeclared write occurred, but cannot guarantee prevention at the host-kernel boundary.

Brokered mode is also not a host-kernel sandbox. It makes BogK the only **official** I/O path for Bog-native apps and blocks unauthorized broker requests before access. A malicious app can still attempt direct host syscalls; direct reads are not intercepted, and only observable raw runtime/package writes are rejected by the official process result.

## Trust Assumptions

- SHA-256 and Ed25519 behave as specified.
- Trusted public keys in `.bogos/trust/` are provisioned correctly and private keys in `.bogos/keys/` remain private.
- The host, Python interpreter, dependencies, and Bog code execute faithfully.
- Verifiers receive the complete artifacts referenced by a receipt.
- A third party either already trusts an included `.bogproof` public key or explicitly accepts it as a trust-on-first-proof anchor. Portable internal consistency does not establish an external real-world identity by itself.

## What Counts As Proof

A Bog proof is a reproducible verification result, not a bare receipt file. Proof requires:

1. Relevant JSON documents validate against the published schemas.
2. Referenced bytes reconstruct and match every recorded SHA-256 and tree hash.
3. Required package signatures verify against a trusted Ed25519 key.
4. Every declared dependency independently passes package, archive, tree, and signature verification.
5. Delegated receipts are present and completed for every claimed layer.
6. The final receipt is completed, names its checks, and hashes its evidence chain.
7. A brokered v8 replay confirms the same current package/tree/dependency/policy state, ordered syscall evidence, brokered output hashes, recorded process-output hashes, and final process proof hash.
8. A Genesis v9 replay confirms the signed ledger chain, registry, lockfile, installed packages, brokered process proofs, capability evidence, writable-state transitions, and final active state root.
9. A HyperGenesis v10 third-party verifier confirms the portable proof manifest, public trust keys, signed registry/lock/packages/ledger/final receipt, state objects, and replayed final root.

`scripts/evaluate_hypergenesis.py` is the v10.0.0 reference proof loop. It emits `artifacts/hypergenesis_receipt.json` and `artifacts/hypergenesis_session.bogproof`.

## Verification Boundary

Bog receipts prove only the checks represented in their format. They do not inherit stronger properties from words such as "kernel", "policy", "verified", or "signed". Consumers must inspect the receipt format, execution status, failures, signatures, hashes, dependencies, and delegated evidence.
