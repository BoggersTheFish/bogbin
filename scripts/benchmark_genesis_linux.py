"""Bounded normal-user Linux observations; no cache dropping, tuning, raw disks or GPU load.
Timing includes language/runtime overhead. This is a baseline seed, not a Linux/BogOS comparison.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import statistics
import subprocess
import tempfile
import time


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def summary(values):
    ordered=sorted(values)
    return dict(samples=values,unit="ns",n=len(values),median=statistics.median(values),
                p95=ordered[math.ceil(.95*len(values))-1],p99=ordered[math.ceil(.99*len(values))-1],
                max=max(values),tail_scope="sample distribution; small n, not a production tail estimate")


def capture(argv):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
        return dict(argv=argv,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
    except (OSError,subprocess.TimeoutExpired) as e:
        return dict(argv=argv,unavailable=str(e))


def measure(fn, samples=9):
    fn() # warmup
    values=[]
    for _ in range(samples):
        start=time.perf_counter_ns();fn();values.append(time.perf_counter_ns()-start)
    return summary(values)


def run(output):
    start=time.monotonic()
    output.parent.mkdir(parents=True,exist_ok=True)
    before=resource.getrusage(resource.RUSAGE_SELF)
    size=4*1024*1024
    data=b"BogOS Genesis baseline\n"*(size//22+1)
    data=data[:size]
    digest=hashlib.sha256(data).digest()
    def cpu():
        for _ in range(4):
            require(hashlib.sha256(data).digest()==digest,"hash mismatch")
    libc=ctypes.CDLL(None)
    src=ctypes.create_string_buffer(data);dst=ctypes.create_string_buffer(size)
    libc.memmove.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
    def memory():
        for _ in range(16):
            libc.memmove(dst,src,size)
    results=dict(cpu_sha256_16MiB=measure(cpu),libc_memmove_64MiB=measure(memory))
    require(dst.raw==data,"copy mismatch")
    if platform.machine()=="x86_64":
        # Linux x86-64 syscall 39 = getpid. ctypes, Python loop and syscall overhead included.
        libc.syscall.restype=ctypes.c_long
        def syscall():
            for _ in range(2000):
                require(libc.syscall(ctypes.c_long(39))==os.getpid(),"syscall mismatch")
        results["getpid_2000_ctypes_and_python"]=measure(syscall)
    with tempfile.TemporaryDirectory(prefix="genesis-bench-",dir=output.parent) as d:
        path=Path(d)/"scratch.dat"
        with path.open("w+b",buffering=0) as f:
            def write_sync():
                f.seek(0);require(f.write(data)==size,"short write");os.fsync(f.fileno())
            results["buffered_write_fsync_4MiB"]=measure(write_sync)
            def cached_read():
                f.seek(0);require(hashlib.sha256(f.read()).digest()==digest,"read mismatch")
            results["cached_read_and_hash_4MiB"]=measure(cached_read)
        if shutil.which("gcc"):
            source=Path(d)/"tiny.c";binary=Path(d)/"tiny"
            source.write_text("#include <stdio.h>\nint main(void){puts(\"genesis-ok\");return 0;}\n")
            def compile_tiny():
                subprocess.run(["gcc","-O2",str(source),"-o",str(binary)],check=True,capture_output=True,timeout=10)
            results["gcc_tiny_compile_link"]=measure(compile_tiny,5)
            require(subprocess.check_output([str(binary)],timeout=3)==b"genesis-ok\n","compiled output mismatch")
    jitter=[]
    for _ in range(32):
        t=time.perf_counter_ns();time.sleep(.001);jitter.append(max(0,time.perf_counter_ns()-t-1_000_000))
    results["sleep_1ms_overshoot"]=summary(jitter)
    after=resource.getrusage(resource.RUSAGE_SELF)
    report=dict(format="genesis-linux-seed-v1",timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        platform=platform.platform(),python=platform.python_version(),cpus=os.cpu_count(),
        affinity=sorted(os.sched_getaffinity(0)),load=os.getloadavg(),
        metadata=[capture(c) for c in [["lscpu"],["free","-b"],["lsblk","-o","NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL"],
          ["lspci","-nn"],["gcc","--version"],["nvidia-smi","--query-gpu=name,memory.total","--format=csv,noheader"]]],
        results=results,seconds=time.monotonic()-start,
        resources=dict(user_seconds=after.ru_utime-before.ru_utime,system_seconds=after.ru_stime-before.ru_stime,
                       maxrss_kib=after.ru_maxrss,voluntary_switches=after.ru_nvcsw-before.ru_nvcsw,
                       involuntary_switches=after.ru_nivcsw-before.ru_nivcsw),
        gpu_ai_workload="not run: common isolated workload/backend not established",
        limitations=["single normal-user desktop run", "warm caches, no cache dropping", "runtime overhead included",
                     "tiny compilation only", "no multicore stress or GUI input latency", "no OS superiority inference"])
    output.write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("artifacts/genesis-linux/results.json"))
    args=parser.parse_args()
    report=run(args.output)
    print(json.dumps({"output":str(args.output),"seconds":report["seconds"],"resources":report["resources"]}))
