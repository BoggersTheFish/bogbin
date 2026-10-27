//! Same ownership transitions, optional per-transition checkpoint. Linux host microbenchmark only.
use bogk_core::bkc::{Authority,ResourceState};
use std::{hint::black_box,time::Instant};
fn trial(checkpoint_each: bool, iterations: usize) -> (f64,[u8;32]) {
    let mut state=ResourceState::<64>::new(1).unwrap();
    let mut caps:[Option<Authority>;64]=[None;64];
    for cap in caps.iter_mut() { *cap=Some(state.allocate(1).unwrap()); }
    let start=Instant::now();
    for i in 0..iterations {
        let index=i%64;
        let a=black_box(&mut state).transfer(1,black_box(caps[index].unwrap()),2).unwrap();
        if checkpoint_each {black_box(state.checkpoint());}
        caps[index]=Some(black_box(&mut state).transfer(2,black_box(a),1).unwrap());
        if checkpoint_each {black_box(state.checkpoint());}
    }
    let ns=start.elapsed().as_nanos() as f64/(iterations*2) as f64;
    (ns,state.checkpoint())
}
fn main() {
    const ITERATIONS:usize=512;
    let mut fast=Vec::new();let mut hashed=Vec::new();
    for i in 0..23 {
        let (a,b)=if i%2==0 {(trial(false,ITERATIONS),trial(true,ITERATIONS))}
            else {let b=trial(true,ITERATIONS);let a=trial(false,ITERATIONS);(a,b)};
        assert_eq!(a.1,b.1,"measurement paths must produce identical state");
        if i>1 {fast.push(a.0);hashed.push(b.0);}
    }
    println!("{{\"format\":\"bkc-host-bench-v1\",\"resources\":64,\"transitions_per_sample\":{},\"warmup_pairs\":2,\"samples\":21,\"state_bytes\":{},\"fast_ns_per_transition\":{:?},\"checkpoint_each_ns_per_transition\":{:?},\"final_state_equality\":true,\"scope\":\"host function and optional O(N) checkpoint cost, not BogOS versus Linux\"}}",ITERATIONS*2,std::mem::size_of::<ResourceState<64>>(),fast,hashed);
}
