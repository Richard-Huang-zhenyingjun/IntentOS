# Known Issues

- Non-block objects (tool) fail at planning on follow-up commands — likely label-resolution or bin/tray routing doesn't handle the tool. Honest failure, invariant intact. This belongs with failure-handling work, not physics work.
- UX cleanup: when a per-object skip prompt and max-cycles escalation happen together, the current wording can ask two questions at once. Merge them into one clear prompt, e.g. explain what was skipped and ask only whether to keep going or leave it.
- Week 3 handoff quality: "leave it" currently acknowledges and ends, but should hand control back more responsibly with a clear state summary: what got done, what's left, where it is, and how the user can re-engage later.
- Wording polish: max-cycles handoff says "after 1 rounds"; pluralize as "1 round" / "N rounds".
