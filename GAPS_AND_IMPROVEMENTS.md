# Gaps & Improvements

## Part 1 — Gaps in long LLM <-> user conversations generally

The four this project already targeted, restated:

| Gap | What goes wrong | How AXON TREE addresses it |
|---|---|---|
| Semantic drift | Meaning shifts turn over turn until the model's picture of the goal quietly diverges from what the user actually meant | Every leaf traces back to one ROOT GOAL node; a decision that doesn't serve it is visibly out of place instead of buried in turn order |
| Assumption blindness | The model treats its own inferred guesses the same as user-stated facts | Dedicated `assumption` type, kept separate from `fact` until explicitly `confirm`ed |
| Redundancy loop | The same explanation or decision gets re-derived because earlier state wasn't retained in a usable form | `resolve`/`compress`/`prune` retire settled state instead of leaving it to be re-read (or re-explained) every time |
| Implicit constraint gap | A constraint stated once early on ("no third-party analytics") isn't necessarily still weighted the same after a dozen turns | `importance=3` / CRITICAL branch — never auto-demoted, never cut by a word budget |

Four more worth adding, not yet targeted by anything in this project:

- **Recency bias / lost-in-the-middle.** Models attend more to the most
  recent turns (and the very start) of a long context; a fact stated in
  the middle can be technically "in context" and still get under-weighted.
  A tree helps mechanically here — every leaf has equal structural
  standing regardless of when it was said, unlike a transcript where
  position *is* an implicit weighting.
- **Silent goal substitution.** Over a long session, the model can start
  optimizing for whatever sub-task is currently being discussed and lose
  the thread back to the actual root goal it was supposed to serve. The
  ROOT GOAL node existing at all helps only if something actually checks
  new decisions against it — worth stating as an explicit habit ("does
  this still serve ROOT?") rather than assuming the tree's mere presence
  enforces it.
- **Correction non-persistence.** A user correction ("no, Postgres, not
  MySQL") is one turn in a long transcript; nothing marks it as
  authoritative, so the model can drift back to the original wrong
  assumption later, especially past a context truncation boundary.
  Suggested convention (not currently enforced by the code, to keep the
  CLI surface small): log corrections as `type=mistake`,
  `importance=3` — that combination is never auto-demoted and never
  auto-cut, which a plain re-statement wouldn't be.
- **No confidence/provenance tracking on facts.** A "fact" node doesn't
  currently distinguish "the user told me this" from "I concluded this
  and never had it checked." The `assumption` + `confirmed` fields cover
  the second half of this now; the first half (tagging *stated* facts
  with where they came from) is what the existing `source` field is for,
  and it's under-used in practice — worth making a habit of filling it in
  (`--source "user, turn 12"` / `--source "auth.py:84"`), not just adding
  more fields for it.

## Part 2 — Gaps that remain in this tool specifically, after this rebuild

Fixed bugs are in `CHANGELOG.md`. What's still genuinely open:

- **Free-text ambiguity in labels.** A label containing `": "` can confuse
  either parser (the first `": "` is taken as the label/summary
  boundary). `add_node()` now warns when this happens, but doesn't
  block it — a different delimiter choice would close this fully at the
  cost of making the plain-text format less naturally readable. Not
  fixed by design; flagged instead.
- **`confirmed` doesn't round-trip through text export.** It lives in the
  JSON store but isn't written into the flat/tree text format, so a
  pasted-and-reimported assumption always comes back unconfirmed even if
  it was verified before. Would need a compact in-line marker (e.g. a
  `[confirmed]` suffix) — deferred rather than adding format complexity
  without being asked to.
- **The benchmark is illustrative, not a real eval.** `benchmark.py`
  compares hand-written before/after pairs with one shared token
  estimator — reproducible, but not a substitute for a real blinded study
  measuring actual model behavior with vs. without this skill loaded, on
  real conversations. That would be the honest next step if the
  percentage itself needs to hold up under scrutiny rather than serve as
  a directional illustration.
- **No schema migration path beyond one version bump.** `schema_version`
  exists now and upgrades v1 -> v2 in place, but there's no general
  migration framework — a v3 would need its own one-off upgrade function
  written by hand, same as this one was.
- **Locking is advisory, not a hard guarantee.** The lock file stops the
  common case (two terminals, same project, same moment) but an advisory
  lock can't stop a process that doesn't check for it (e.g. a script
  editing `graph.json` directly instead of going through this CLI).

## Part 3 — Suggestions, roughly in priority order

1. **Make correction-logging an explicit habit, not just a convention in
   a doc.** Whether that becomes a CLI flag (`--correction`, which forces
   `type=mistake, importance=3`) or stays a documented pattern is a real
   product choice — a flag is more foolproof, a convention keeps the CLI
   surface smaller. Leaning toward the flag if this keeps getting missed
   in practice.
2. **Write the five worked examples for real.** Referenced by the
   published repo's `SKILL.md` but never actually shipped anywhere. One
   per task type (code project, research, creative, general conversation,
   security/pentest) the way the reference was originally structured
   would make Deep-mode sessions much easier to get right on the first
   try instead of extrapolating from the single compact example included
   here.
3. **A real evaluation, when it's worth the cost.** Take a handful of
   actual long conversations, run them with and without the skill loaded,
   and measure the model's answer quality on questions about earlier
   state (not just token count) — the thing this project is actually
   trying to protect against is wrong/forgotten state, and token count is
   a proxy for that, not the target itself.
4. **A `stats` field for stale unconfirmed assumptions** — e.g., oldest
   unconfirmed `assumption` node's age — so a long-running project
   surfaces "you never actually confirmed this" instead of it sitting
   quietly forever.
5. **Consider an opt-in strict serialization** (e.g. JSON Lines) for
   users who'd rather trade human-readability for zero label-parsing
   ambiguity — additive, not a replacement for the plain-text format that
   makes this pasteable into any chat in the first place.

## Note on sourcing

Reviewing the previous draft's citations: the "Contextual Feature Drift in
Large Language Models" (OSF Preprints) and "H-MEM: Hierarchical Memory for
High-Efficiency Long-Term Reasoning" (arXiv) references are real papers,
but neither was actually cited anywhere in the body text — they sat
unused in a list. A third reference, a specific "6.6x" statistic
attributed to a Reddit post, didn't turn up in a search and is treated
here as unverified rather than repeated. Worth noting: H-MEM in
particular uses dense vector embeddings and is evaluated against the
LoCoMo benchmark — a materially more rigorous, empirically-measured
approach than this project's manually-edited text tree, and a reasonable
thing to actually benchmark against (not just cite) if this project's
compression claims need to hold up next to it.
