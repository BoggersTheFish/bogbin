//! BKC v0.1: bounded exclusive ownership with generation-bound authority.
//!
//! This is a reference machine, not the physical page allocator. The adapter must
//! authenticate principals, never reuse a domain ID while any old authority can exist, serialize access,
//! and destroy mappings before release/transfer. Checkpoints do not authenticate
//! their own origin. ResourceState deliberately cannot be cloned or deserialized.
use crate::sha256_standard;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Slot { owner: u32, generation: u64 }

/// Opaque within safe Rust. Copying a handle does not duplicate its resource.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Authority { domain: u64, resource: usize, generation: u64, owner: u32 }
impl Authority {
    pub fn resource(self) -> usize { self.resource }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResourceError { Domain, Principal, Capacity, Authority, Generation }

#[derive(Debug, PartialEq, Eq)]
pub struct ResourceState<const N: usize> { domain: u64, slots: [Slot; N] }
impl<const N: usize> ResourceState<N> {
    /// Trusted mint: domain is an incarnation, never reused while any earlier handle can exist.
    /// This precondition is enforced by the future kernel adapter, not this reference machine.
    pub fn new(domain: u64) -> Result<Self, ResourceError> {
        if domain == 0 || N == 0 { return Err(ResourceError::Domain); }
        Ok(Self { domain, slots: [Slot { owner: 0, generation: 0 }; N] })
    }
    /// Lowest reusable free resource; exhausted generations are never recycled.
    pub fn allocate(&mut self, owner: u32) -> Result<Authority, ResourceError> {
        if owner == 0 { return Err(ResourceError::Principal); }
        let resource = self.slots.iter().position(|s| s.owner == 0 && s.generation < u64::MAX)
            .ok_or(ResourceError::Capacity)?;
        self.slots[resource].owner = owner;
        self.slots[resource].generation += 1;
        Ok(self.authority(resource))
    }
    /// Validate all fallible conditions before changing any slot.
    pub fn transfer(&mut self, caller: u32, authority: Authority, target: u32) -> Result<Authority, ResourceError> {
        if target == 0 { return Err(ResourceError::Principal); }
        let next = self.next_generation(caller,authority)?;
        self.slots[authority.resource] = Slot { owner: target, generation: next };
        Ok(self.authority(authority.resource))
    }
    pub fn release(&mut self, caller: u32, authority: Authority) -> Result<(), ResourceError> {
        let next = self.next_generation(caller,authority)?;
        self.slots[authority.resource] = Slot { owner: 0, generation: next };
        Ok(())
    }
    fn authority(&self, resource: usize) -> Authority {
        let s=self.slots[resource];
        Authority { domain: self.domain, resource, generation: s.generation, owner: s.owner }
    }
    fn next_generation(&self, caller: u32, a: Authority) -> Result<u64, ResourceError> {
        let slot=self.slots.get(a.resource).ok_or(ResourceError::Authority)?;
        if caller == 0 || a.domain != self.domain || a.owner != caller
            || slot.owner != caller || slot.generation != a.generation
        { return Err(ResourceError::Authority); }
        slot.generation.checked_add(1).ok_or(ResourceError::Generation)
    }
    pub fn owner(&self, resource: usize) -> Option<u32> { self.slots.get(resource).map(|s|s.owner) }
    pub fn free_count(&self) -> usize { self.slots.iter().filter(|s|s.owner == 0).count() }
    /// Optional O(N) commitment. No hashing, allocation or I/O is performed by transitions.
    pub fn checkpoint(&self) -> [u8;32] {
        let mut header=[0u8;24];header[..8].copy_from_slice(b"BKCv0001");
        header[8..16].copy_from_slice(&self.domain.to_le_bytes());
        header[16..24].copy_from_slice(&(N as u64).to_le_bytes());
        let mut hash=sha256_standard(&header);
        for (index,slot) in self.slots.iter().enumerate() {
            let mut bytes=[0u8;52];bytes[..32].copy_from_slice(&hash);
            bytes[32..40].copy_from_slice(&(index as u64).to_le_bytes());
            bytes[40..44].copy_from_slice(&slot.owner.to_le_bytes());
            bytes[44..52].copy_from_slice(&slot.generation.to_le_bytes());
            hash=sha256_standard(&bytes);
        }
        hash
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ownership_is_conserved_and_exhaustion_does_not_mutate() {
        let mut s=ResourceState::<2>::new(1).unwrap();
        let a=s.allocate(1).unwrap();let b=s.allocate(2).unwrap();
        assert_eq!((s.free_count(),s.owner(a.resource()),s.owner(b.resource())),(0,Some(1),Some(2)));
        let before=s.checkpoint();
        assert_eq!(s.allocate(1),Err(ResourceError::Capacity));
        assert_eq!(s.checkpoint(),before);
        s.release(1,a).unwrap();assert_eq!(s.free_count(),1);
    }
    #[test]
    fn transfer_and_reallocation_reject_stale_or_foreign_authority_atomically() {
        let mut s=ResourceState::<1>::new(1).unwrap();
        let a=s.allocate(1).unwrap();let before=s.checkpoint();
        assert_eq!(s.transfer(2,a,2),Err(ResourceError::Authority));
        assert_eq!(s.checkpoint(),before);
        let b=s.transfer(1,a,2).unwrap();
        let c=s.transfer(2,b,1).unwrap();
        assert_eq!(s.release(1,a),Err(ResourceError::Authority));
        s.release(1,c).unwrap();let d=s.allocate(1).unwrap();
        assert_eq!(s.release(1,c),Err(ResourceError::Authority));
        assert!(s.release(1,d).is_ok());
    }
    #[test]
    fn invalid_principals_domains_and_handles_do_not_mutate() {
        assert!(ResourceState::<0>::new(1).is_err());
        assert!(ResourceState::<1>::new(0).is_err());
        let mut s=ResourceState::<1>::new(1).unwrap();
        let a=s.allocate(1).unwrap();let before=s.checkpoint();
        assert_eq!(s.allocate(0),Err(ResourceError::Principal));
        assert_eq!(s.transfer(1,a,0),Err(ResourceError::Principal));
        let mut bad=a;bad.domain=2;
        assert_eq!(s.release(1,bad),Err(ResourceError::Authority));
        bad=a;bad.resource=usize::MAX;
        assert_eq!(s.release(1,bad),Err(ResourceError::Authority));
        assert_eq!(s.checkpoint(),before);
    }
    #[test]
    fn domain_incarnations_reject_cross_state_handles_and_reuse_is_a_negative_control() {
        let mut old=ResourceState::<1>::new(41).unwrap();
        let stale=old.allocate(1).unwrap();
        drop(old);
        let mut fresh=ResourceState::<1>::new(42).unwrap();
        fresh.allocate(1).unwrap();
        let before=fresh.checkpoint();
        assert_eq!(fresh.release(1,stale),Err(ResourceError::Authority));
        assert_eq!(fresh.checkpoint(),before);
        // Violating the trusted-mint precondition does resurrect a handle. This
        // control records the boundary; no cross-incarnation safety is claimed.
        let mut reused=ResourceState::<1>::new(41).unwrap();
        reused.allocate(1).unwrap();
        assert!(reused.release(1,stale).is_ok());
    }
    #[test]
    fn generation_never_wraps_or_resurrects_authority() {
        let mut s=ResourceState::<1>::new(1).unwrap();
        s.slots[0].generation=u64::MAX-1;
        let a=s.allocate(1).unwrap();let before=s.checkpoint();
        assert_eq!(s.transfer(1,a,2),Err(ResourceError::Generation));
        assert_eq!(s.release(1,a),Err(ResourceError::Generation));
        assert_eq!(s.checkpoint(),before);
    }
    #[test]
    fn exhaustive_short_traces_preserve_accounting_and_rejection_state() {
        // 8^5 complete histories, replayed independently; includes saved stale tokens.
        for trace in 0u32..8u32.pow(5) {
            let mut s=ResourceState::<2>::new(1).unwrap();
            let mut tokens=[None;6];let mut count=0;let mut choices=trace;
            for _ in 0..5 {
                let action=choices%8;choices/=8;
                let before=s.checkpoint();
                let result=match action {
                    0|1=>s.allocate(action+1).map(Some),
                    _ if count==0=>s.allocate(0).map(Some),
                    _=>{
                        let token=tokens[if action%2==0 {0} else {count-1}].unwrap();
                        let caller=if action<5 {1} else {2};
                        if action%3==0 {s.release(caller,token).map(|_|None)}
                        else {s.transfer(caller,token,3-caller).map(Some)}
                    }
                };
                match result {
                    Ok(Some(token))=>{tokens[count]=Some(token);count+=1;},
                    Ok(None)=>{},
                    Err(_)=>assert_eq!(before,s.checkpoint()),
                }
                let owned=(0..2).filter(|i| s.owner(*i).unwrap()!=0).count();
                assert_eq!(s.free_count()+owned,2);
            }
        }
    }
}
