---
name: Sandbox shell output
description: Delimiter normalization observed in CodeExecution shell callback results.
---

The CodeExecution `shellExec` callback can strip tabs and represent line endings as CRLF in returned output. Treat its text as display-oriented rather than byte-exact.

**Why:** Parsing `git diff --name-status` by tab in that callback yielded joined status-and-path strings, and splitting newline-separated commit IDs left carriage returns on intermediate entries.

**How to apply:** When processing command output in CodeExecution, use a machine-readable format that survives normalization or explicitly handle normalized delimiters and CRLF. Verify parsed identifiers before mutating a remote.