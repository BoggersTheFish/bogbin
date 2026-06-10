SCALE = 1000

OPS = {
    "NOOP": 0x00,
    "HALT": 0x01,
    "CREATE_NODE": 0x02,
    "CREATE_EDGE": 0x03,
    "CREATE_CLAIM": 0x04,
    "ACTIVATE": 0x05,
    "PROPAGATE": 0x06,
    "DECAY": 0x07,
    "INTERFERE": 0x08,
    "COMPUTE_TENSION": 0x09,
    "VERIFY": 0x0A,
    "ACCEPT": 0x0B,
    "REJECT": 0x0C,
    "QUARANTINE": 0x0D,
    "LOG_RECEIPT": 0x0E,
    "EMIT_RECEIPT": 0x0F,

    # v0.2 generative storage opcodes
    "DECLARE_BASIS": 0x10,
    "LOAD_COEFFICIENTS": 0x11,
    "SYNTHESIZE": 0x12,
    "VERIFY_HASH": 0x13,
    "ACCEPT_DATA": 0x14,
    "STORE_RESIDUAL": 0x15,
    "APPLY_RESIDUAL": 0x16,
    "REJECT_DATA": 0x17,
}

OP_NAMES = {code: name for name, code in OPS.items()}

EDGE_TYPES = {
    "support": 1,
    "conflict": 2,
}

EDGE_TYPE_NAMES = {code: name for name, code in EDGE_TYPES.items()}
