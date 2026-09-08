# C functional programming profile

Canonical English. [한국어](c.ko.md). Apply with [common rules](../AGENTS.md) and [verification](../fp/verification.md). Evidence: [sources](../references/functional-programming.md).

Scope: this is prose policy. Implementation and executable-verification obligations below apply when changing actual C/Rust software. Editing this profile alone uses CHK-014 document review; no example code or runner belongs in this package.

## Semantic model and representation

**C-001** Keep the semantic core as value-to-value transformations with explicit tagged success/error results. Prefer value structs for small data and private implementation types for representation-sensitive data. A C `typedef` is not a distinct validated type; hide or validate every construction path. Keep tag/payload validity explicit and reject untrusted tags before selecting payloads.

**C-002** `const T *` constrains access through that view; it does not prove deep immutability, exclusive ownership, or absence of changes through other aliases. Document pointer extent, initialization, alignment, lifetime, and who can mutate referenced storage. Establish race-free access before taking a snapshot: copying concurrently mutated non-atomic storage is not safe. Use ownership transfer or synchronization at ingress, and state how multi-field snapshots remain coherent; atomic fields alone do not establish a coherent snapshot. Reject unstable borrowed state as a pure input.

**C-003** Pure APIs return new values and never change caller-observable input/output storage. A conventional output-buffer API is a writing boundary, not a pure function. For large results, separate pure size/plan computation from an admitted construction kernel and publish only a completed immutable result. Document capacity errors, overlap rules, failure atomicity, and ownership transfer.

**C-004** Admit local counters, scratch buffers, and in-place algorithms only under FP-007; keep the immutable reference specification separate. Allocation, custom allocators, deallocation, and failure callbacks require explicit contracts. Never call an opaque mutating routine pure because its pointer is private. Exclude pointer identity and allocator state from domain decisions; make resource failure behavior explicit.

## Effects and defined behavior

**C-005** Core dependencies must exclude global/thread-local state, `errno`, locale, floating-point environment changes, volatile/MMIO, clocks, I/O, and effectful callbacks. Immutable tables are allowed. Snapshot external inputs in adapters. Function pointers need effect and lifetime contracts; a callback parameter is not an effect system. GCC `pure`/`const` attributes are optimizer promises, not proof tools or portable purity types.

**C-006** Select and record the actual C language version, compiler flags, target widths, and extension policy. Avoid undefined behavior before claiming equational reasoning: signed overflow, invalid shifts/division, out-of-bounds pointer arithmetic, use-after-free, uninitialized reads, misalignment, and invalid effective-type access. Define wrapping/saturating/checked arithmetic deliberately; unsigned wrapping alone is not a domain specification.

**C-007** `restrict` is an aliasing contract with obligations, not an ownership verifier. State separation requirements and enforce them at a trustworthy caller; do not add `restrict` merely to make a function look functional. Portable C cannot validate an arbitrary pointer's lifetime or extent from its numeric value. Malformed byte input must be rejected safely within an established valid memory region.

**C-008** Compare and serialize semantic fields, not arbitrary struct bytes or padding. Specify endianness, integer ranges, tag encoding, and string/byte length. Do not cast untrusted wire bytes to a struct or pass a C enum as a validated Rust enum. Treat NaN, signed zero, locale, and floating-point evaluation options as explicit domain concerns where relevant.

**C-009** Expected failures use a tag with an error payload; all public outputs are initialized according to the tag contract. Production validation must not disappear under `NDEBUG`; `assert` is insufficient for a required runtime check. Internal unreachable cases fail loudly but never use undefined behavior as an error handler.

## Resources and verification

**C-010** Give each allocation, file, lock, and process one documented owner and cleanup path in the adapter. Specify partial-acquisition and cleanup-failure behavior. Do not use `longjmp` or asynchronous interruption across owned resources without a separately verified cleanup design. Test allocation/I/O failure at the first, Nth, and every call as applicable.

**C-011** Use include/call dependency checks plus compiler warnings and static analysis; simple symbol scans are incomplete for macros, indirect calls, inline code, and dynamic linking. Verify legal negative examples (`const` alias mutation, global reads) as well as accepted value functions. A compiler accepting a negative example is expected evidence that the language does not enforce purity.

**C-012** For deductive verification use ACSL/Frama-C where the project supports it: specify preconditions, result relation, read dependencies, write frame, separation, loop invariant, and decreasing variant. `assigns \nothing` alone does not exclude reading a mutable global or prove termination. Record memory model, callee assumptions, runtime-error obligations, discharged goals, and unknown/timeouts; annotations and partial discharge are not a proof of the whole program.

**C-013** Test debug, optimized, and actual release builds; required checks must survive `NDEBUG`. Run supported address/undefined/race/memory/leak analyses in compatible separate builds, noting instrumentation coverage and runtime limitations. Compare admitted kernels against a simple pure model and test valid alias arrangements, boundary arithmetic, cancellation, and recovery. Do not execute undefined behavior in a normal test and interpret a non-crash as correctness.

**C-014** At C/Rust boundaries require the two profiles together. Specify lengths, nullability, ownership/deallocator pairing, aliasing, lifetime, calling convention, alignment, thread/callback behavior, and error/unwind policy. Translate external errors into domain values; never transfer a mutable handle into the semantic core. Run the actual cross-language boundary tests when changing the consuming software; this prose profile is not execution evidence.
