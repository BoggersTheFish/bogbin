"""SMT proof about the BKC generation rule, NOT verification of compiled Rust.

Assumptions: unsigned 64-bit generations, checked increment, stale token epoch
<= current epoch, a domain is never reused while any prior handle can exist, no rollback of authority epochs.
The adapter's identity, mapping destruction and synchronization are not proved.
"""
import json
import z3


def require(condition):
    if not condition:
        raise RuntimeError("generation theorem or negative control failed")


def check():
    current, stale, future = z3.BitVecs("current stale future", 64)
    maximum = z3.BitVecVal(2**64-1,64)
    accepted = [z3.ULE(stale,current), z3.ULT(current,maximum)]
    # A checked accepted transition increments. Any subsequent non-wrapping state
    # has at least that generation, hence cannot match any prior token.
    solver = z3.Solver()
    solver.add(*accepted, future == current+1, future == stale)
    step=solver.check()
    require(step == z3.unsat)
    solver2 = z3.Solver()
    solver2.add(*accepted,z3.UGE(future,current+1),future == stale)
    later=solver2.check()
    require(later == z3.unsat)
    # Negative control: wrapping makes epoch zero usable again after UINT64_MAX.
    control = z3.Solver()
    control.add(current == maximum, stale == 0, future == current+1, future == stale)
    negative=control.check()
    require(negative == z3.sat)
    return dict(z3_version=z3.get_version_string(), checked_step=str(step),
                nonwrapping_future=str(later), wrapping_negative_control=str(negative),
                control={str(v):str(control.model()[v]) for v in [current,stale,future]},
                scope="bitvector model theorem; Rust refinement and hardware semantics unproved")


if __name__ == "__main__":
    print(json.dumps(check(),indent=2))
