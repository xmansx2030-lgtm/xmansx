---
name: Published design source
description: Safe source selection when reviewing a published UI newer than the local checkout.
---

For published-portal design reviews, establish which source matches the requested site before deciding a feature is missing. Use an isolated, source-based preview when the matching source is newer than the current checkout; do not merge or replace the application just to produce a design comparison.

**Why:** A parent-portal review found a real published feature whose routes were absent from the older local checkout. Treating the checkout as authoritative would have produced an unrelated redesign or an unrequested broad update.

**How to apply:** Inspect the matching remote source non-destructively, retain the existing application and authentication, and clearly label synthetic protected-screen previews. A source review and a mockup are not a visual verification of the signed-in production experience.
