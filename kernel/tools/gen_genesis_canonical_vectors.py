"""Independent Python bytes/digests for the native GenesisRoot and JRNLv41 tests."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"kernel/tools"))
from make_v40_genesis_workspace_root_image import genesis_root_bytes
from gen_v40_workspace_vectors import journal_entry_bytes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"kernel/fixtures/genesis_canonical.json")
    args=parser.parse_args()
    vectors={"genesis":genesis_root_bytes(bytes([165])*32),
             "journal":journal_entry_bytes(1,bytes(32),bytes([9])*32,bytes([1])*32,bytes([2])*32,bytes([8])*32,True)}
    text=json.dumps({k:{"hex":v.hex(),"sha256":hashlib.sha256(v).hexdigest()} for k,v in vectors.items()},indent=2)+"\n"
    if args.check:
        if not args.output.exists() or args.output.read_text()!=text:
            print("canonical fixture mismatch",file=sys.stderr)
            return 1
        print("canonical Python fixtures match")
    else:
        args.output.write_text(text)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
