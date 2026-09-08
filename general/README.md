# Reusable project guidance

This Markdown package combines one functional-programming contract, shared verification rules, and language-specific profiles. It is project guidance, not a skill or an executable test suite.

| Entry or profile | English | 한국어 |
| --- | --- | --- |
| Common contract | [AGENTS.md](AGENTS.md) | [AGENTS.ko.md](AGENTS.ko.md) |
| Claude Code entry | [CLAUDE.md](CLAUDE.md), which directs the reader to the common contract | Uses the same paired documents |
| C | [C profile](profiles/c.md) | [C 프로파일](profiles/c.ko.md) |
| Rust | [Rust profile](profiles/rust.md) | [Rust 프로파일](profiles/rust.ko.md) |
| Go | [Go profile](profiles/go.md) | [Go 프로파일](profiles/go.ko.md) |

Read the common contract first, then the profiles selected by GOV-004 and the relevant [verification mode](fp/verification.md). For cgo, both Go and C apply. Other languages use the common rules without inheriting these languages' guarantees.

## Use in another project

Keep the relative layout of the entry documents, applicable profiles, `fp/`, `evals/`, and `references/`, including the local dependencies selected documents require. Merge an explicit instruction to read the package's actual entry path into the consuming project's existing root guidance, preserving unrelated policy. Copying one entry file alone leaves required dependencies behind. Per-run review reports and work diaries are not repository artifacts; report necessary results in the task response or PR description. Follow GOV-005 when adapting paths and checking actual client loading.

## Migration from the former Go directory

The former top-level `golang/AGENTS.md` and `golang/CLAUDE.md` are replaced by the common entry points above plus `profiles/go.md`; there is no separate Go-only instruction package. Update references in consuming projects to the installed entry path, preserve local customizations, and remove old duplicate guidance only after the new documents are available. This repository change does not edit existing installations.

Shared testing requirements live in `fp/verification.md`; Go's table-driven tests, fakes, cleanup hooks, race checks, and fuzzing distinctions live in GO-011–014.
