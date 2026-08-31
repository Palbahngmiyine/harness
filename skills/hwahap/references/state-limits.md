# Hwahap state limits

## Limits

The validator detects structural inconsistency, stale agent profiles, changed
locked contracts, invalid transitions, and unsupported review histories. It
does not create a cryptographic trust boundary, prove reviewer independence,
or prove true parallel execution. The snapshot depends on Git's binary object
store and exact diff bytes; it cannot prevent a mutation after a file/object
was read. Installer exact-six checks describe the observed snapshot only, and
the lstat/unlink cleanup check has a race window. Rollback is best-effort and
cannot guarantee recovery across a crash or non-durable disk write. Sol must
spawn both reviewers before waiting, retain distinct thread IDs, recompute the
snapshot, and rerun validation before claiming completion.

Dependency trust root: state and report load only the exact sibling scripts from
the frozen script directory through a directory file descriptor. They require a
regular, readable file owned by root or the current user, reject group/world
writes, bound the file size, verify descriptor identity before and after reading,
and compare a pinned SHA-256 before executing verified bytes. State verifies
the redaction engine, agent installer, and report generator first; the report
generator independently verifies the redaction engine. These
pins are static and are not refreshed during a command; changing a dependency
requires a reviewed update of the pin graph. This protects the loader boundary,
but cannot prove the host file system or Git object store remains unchanged
after the read, and cannot make rollback durable across a crash.
