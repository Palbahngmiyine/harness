// Conformance probes, not a compiler-enforced purity system.
// Cell and Drop below are intentional, legal impurity counterexamples.
#![forbid(unsafe_code)]
use std::cell::Cell;

fn add_value(left: u32, right: u32) -> Option<u32> {
    left.checked_add(right)
}

fn call_fn<F: Fn() -> u32>(callback: &F) -> u32 {
    callback()
}

struct EffectfulDrop<'a>(&'a Cell<u32>);

impl Drop for EffectfulDrop<'_> {
    fn drop(&mut self) {
        self.0.set(99);
    }
}

fn main() {
    let input = 12;
    assert_eq!(add_value(input, 5), Some(17));
    assert_eq!(input, 12);
    assert_eq!(add_value(u32::MAX, 0), Some(u32::MAX));
    assert_eq!(add_value(u32::MAX, 1), None);
    let cell = Cell::new(0);
    let not_pure = || {
        cell.set(cell.get() + 1);
        cell.get()
    };
    assert_eq!(call_fn(&not_pure), 1);
    assert_eq!(call_fn(&not_pure), 2);
    let observed = Cell::new(0);
    drop(EffectfulDrop(&observed));
    assert_eq!(observed.get(), 99);
    println!("PASS: Rust value contracts and legal impurity counterexamples");
}
