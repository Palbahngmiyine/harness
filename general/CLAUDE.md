# Claude Code entry point

Before working under this package, read [AGENTS.md](AGENTS.md) and follow its common contract. Load the affected language profiles and verification mode as directed by GOV-004; Go work requires [the Go profile](profiles/go.md), and cgo also requires the C profile.

English is normative; [the Korean common contract](AGENTS.ko.md) and [Korean Go profile](profiles/go.ko.md) mirror it. This entry point does not maintain a second testing policy. Prefer the simplest implementation that satisfies the common semantic and verification obligations; simplicity never waives required checks.

For installation or migration from the former Go-only files, follow the [package guide](README.md). Preserve relative paths and the consuming project's existing policy. A link alone does not establish that its target was loaded.
