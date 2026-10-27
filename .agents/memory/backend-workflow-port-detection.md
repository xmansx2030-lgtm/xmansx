---
name: Backend workflow port detection
description: A Replit console workflow may fail its port check when a backend binds only to loopback.
---

For console workflows that wait on a backend port, bind the server to
`0.0.0.0`, even if an in-workspace frontend proxy connects to `127.0.0.1`.

**Why:** The Replit workflow port detector did not recognize a Django server
bound only to loopback, despite the server reporting that it had started. The
same command with a network bind passed the workflow check.

**How to apply:** When a backend workflow reports a port timeout, inspect its
listening address before assuming the application crashed or changing ports.