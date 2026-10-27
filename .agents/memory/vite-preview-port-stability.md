---
name: Vite preview port stability
description: Preventing Vite hot restarts from silently moving the Replit preview off port 5000.
---

Pin the Replit preview's host and port using explicit Vite command-line flags
and `--strictPort`, rather than switching ports based on a runtime environment
variable in Vite's config.

**Why:** A Vite configuration reload during this setup restarted on its
non-Replit default port despite the initial launch opening port 5000. The
workflow still appeared to run, but the preview stopped responding.

**How to apply:** For a dual local-Docker/Replit frontend, leave the local
default alone and put Replit-only binding options in its workflow command.