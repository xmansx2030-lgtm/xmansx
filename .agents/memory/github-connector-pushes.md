---
name: GitHub connector pushes
description: How to keep the local branch consistent when GitHub OAuth authorizes API calls but not native Git pushes.
---

An attached GitHub connector can authorize REST operations without authorizing `git push` over an HTTPS remote. If native push is rejected, avoid credential prompts and use the authenticated GitHub API without force-updating the branch.

**Why:** API-created commits may have different identifiers from equivalent local commits. Leaving the local branch at its original commit after the API updates the remote causes unnecessary history divergence.

**How to apply:** Confirm the remote tip has not advanced; preserve a fast-forward commit chain, compare each resulting file-tree hash to its local counterpart, and align the local branch only when the working tree is clean and the final trees are identical.