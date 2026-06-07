# Bog v7.0.0 Threat Model

## Security Claim

Bog is a user-space verification and policy system for workspace operations. BogK is a **user-space kernel contract for verified workspace operations**. It is not a host kernel, container runtime, or syscall sandbox.

A completed receipt is evidence that the named Bog checks completed for the exact hashes, signatures, manifests, policies, and delegated receipts recorded in it.

## What Bog Defends Against

- Corrupted or tampered `.bog`, `.bogpk`, archive objects, archive manifests, package bundles, and installed package trees.
- Structurally invalid archive manifests, package receipts, app manifests, decoded BOGPK metadata, and kernel receipts.
- Unsigned packages or packages signed outside the workspace trust store when signature enforcement is enabled.
- Missing, cyclic, corrupted, or untrusted declared package dependencies.
- App files whose hashes do not match `bog_app.json`.
- App package mutation detected before, during, or after a verified run.
- Runtime writes visible in the app runtime directory but not declared by app policy.
- BogK requests for unknown apps, unknown mounts, unsafe paths, or undeclared writes.

## What Bog Does Not Defend Against

- A malicious native process escaping Bog policy through host syscalls, subprocesses, network access, ptrace, kernel exploits, or writes outside paths Bog observes.
- A compromised host OS, Python runtime, Bog implementation, cryptographic library, private signing key, or trusted-key store.
- Rollback, freshness, revocation, transparency-log, or remote-registry attacks.
- Confidentiality, denial of service, resource exhaustion, or side channels.
- The truth of human claims. Bog proves bytes, signatures, declared checks, and receipt linkage, not intent, legality, or safety.

Runtime policy is not sandboxing. Post-run write checks can reject and prove an undeclared write occurred, but cannot guarantee prevention at the host-kernel boundary.

## Trust Assumptions

- SHA-256 and Ed25519 behave as specified.
- Trusted public keys in `.bogos/trust/` are provisioned correctly and private keys in `.bogos/keys/` remain private.
- The host, Python interpreter, dependencies, and Bog code execute faithfully.
- Verifiers receive the complete artifacts referenced by a receipt.

## What Counts As Proof

A Bog proof is a reproducible verification result, not a bare receipt file. Proof requires:

1. Relevant JSON documents validate against the published schemas.
2. Referenced bytes reconstruct and match every recorded SHA-256 and tree hash.
3. Required package signatures verify against a trusted Ed25519 key.
4. Every declared dependency independently passes package, archive, tree, and signature verification.
5. Delegated receipts are present and completed for every claimed layer.
6. The final receipt is completed, names its checks, and hashes its evidence chain.

`scripts/evaluate_signed_dependency_demo.py` is the v7.0.0 reference proof loop. It emits `artifacts/signed_dependency_proof_receipt.json`.

## Verification Boundary

Bog receipts prove only the checks represented in their format. They do not inherit stronger properties from words such as "kernel", "policy", "verified", or "signed". Consumers must inspect the receipt format, execution status, failures, signatures, hashes, dependencies, and delegated evidence.
