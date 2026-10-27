"""Run bounded checks in a disposable source copy; preserve old checked-in receipts.

Invoke from the repository root with cargo, binutils, QEMU and Python available.
The container recipe supplies the native dependencies. --historical adds known
failing legacy application evaluators; the summary returns nonzero on ANY failure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
HISTORICAL=["evaluate_bogkernel_boot","evaluate_v26_ts_lang","evaluate_v26_negative",
 "evaluate_v27_process_model","evaluate_v28_scheduler","evaluate_v29_context_switch",
 "evaluate_v30_preemptive_scheduler","evaluate_v31_verified_paging","evaluate_v32_dynamic_loader",
 "evaluate_v33_syscall_abi","evaluate_v34_ipc","evaluate_v35_writable_bogfs",
 "evaluate_v35_1_writable_bogfs_audit","evaluate_v36_block_device","evaluate_v37_persistent_bogfs",
 "evaluate_v38_file_lifecycle","evaluate_v39_disk_loaded_apps"]


def execute(argv,cwd,log,timeout):
    start=time.monotonic()
    with log.open("w") as f:
        with subprocess.Popen(argv,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True) as p:
            try:
                rc=p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGKILL);p.wait()
                rc=124
    return dict(argv=argv,exit_code=rc,seconds=round(time.monotonic()-start,3),
                log=log.name,sha256=hashlib.sha256(log.read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"artifacts/genesis-regressions")
    parser.add_argument("--historical",action="store_true")
    parser.add_argument("--python",action="store_true",help="run full Python suite (can take 15 minutes)")
    args=parser.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix="genesis-check-") as directory:
        work=Path(directory)/"source"
        shutil.copytree(ROOT,work,ignore=shutil.ignore_patterns(".git","target",".cargo-cache",".genesis-runs","genesis-*","*.img","__pycache__"))
        commands=[("core",["cargo","test","--locked","-p","bogk-core"],"kernel",90),
          ("kernel",["cargo","build","--locked","-p","bogk-kernel","--target","i686-unknown-linux-musl"],"kernel",90),
          ("vectors",["python3","tools/gen_v40_workspace_vectors.py","--check"],"kernel",15)]
        commands.append(("canonical_vectors",["python3","kernel/tools/gen_genesis_canonical_vectors.py","--check"],".",15))
        names=HISTORICAL if args.historical else ["evaluate_v36_block_device","evaluate_v37_persistent_bogfs","evaluate_v38_file_lifecycle"]
        commands.extend((name,["python3","scripts/"+name+".py"],".",90) for name in names)
        commands.append(("journal",["python3","scripts/evaluate_genesis_journal.py","--output",str(args.output/"journal")],".",330))
        if args.python:commands.append(("python",["python3","-m","unittest","discover","-v"],".",1200))
        for name,argv,cwd,limit in commands:
            started=time.time()
            row=execute(argv,work/cwd,args.output/(name+".log"),limit)
            rawdir=args.output/"serial"/name
            for raw in (work/"artifacts").glob("*.log"):
                if raw.stat().st_mtime >= started:
                    rawdir.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(raw,rawdir/raw.name)
            rows.append(dict(name=name,**row));print(name,row["exit_code"],flush=True)
            (args.output/"results.json").write_text(json.dumps(dict(passed=all(r["exit_code"]==0 for r in rows),checks=rows),indent=2)+"\n")
        # Preserve only new raw evidence; historical checked-in receipts in ROOT were never touched.
        (args.output/"environment.json").write_text(json.dumps({tool:subprocess.run(cmd,capture_output=True,text=True).stdout for tool,cmd in {
            "rustc":["rustc","--version"],"cargo":["cargo","--version"],"qemu":["qemu-system-i386","--version"]}.items()},indent=2)+"\n")
    return 0 if all(r["exit_code"]==0 for r in rows) else 1


if __name__=="__main__":
    raise SystemExit(main())
