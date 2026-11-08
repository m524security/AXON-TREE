# Changelog

This rebuild draws on two prior versions that had diverged from each
other: the published repo (`context-barrier`, tag `v2.0.0`) and a local
draft (`axon_tree_optimization_v2.zip`) that had started adding new ideas
on top of it. Worth knowing up front: **the draft was a regression from
the published repo**, not an advance on it — it introduced a syntax error,
broke the export/import round trip, and broke the `--max-words` budget
that the published repo already had working correctly. This version keeps
what the published repo got right, fixes what neither version got right,
and adds the new ideas the draft was reaching for, implemented so they
don't reintroduce the same breaks.

## Fixed (present in one or both prior versions)

- **Syntax error, draft only.** `context_graph.py:182` had a stray `)`
  that made the entire file fail to parse — every command crashed. Gone;
  the whole file now compiles and every command was actually run as part
  of rebuilding this.
- **Dropped output, draft only.** `_tier_section()` built a line per node
  but never appended it to the output — `export-delta` produced section
  headers with no content underneath. Fixed; single shared `_render_leaf()`
  helper now backs every export path so this can't happen silently again.
- **Export/import format mismatch, draft only.** The draft's default
  export switched to a tree-drawing visual format, but `import` still
  only understood the old flat format — running `export` then `import`
  always reported "Imported 0 node(s)." `import_block()` now understands
  both styles (verified with round-trip tests for each).
- **`--max-words` silently ignored, draft only.** `export_tree()` accepted
  the parameter and never used it. Both export styles now share one
  budget-enforcing selection step, and it's covered by a regression test.
- **`assumption` node type didn't survive re-import, draft only.**
  `TAG_BY_TYPE`/`TYPE_BY_TAG` never had an `assumption` entry, so a
  re-imported assumption silently became a `fact`. Fixed at the root: the
  tree format's branch header carries the *full* type name, not a lossy
  abbreviation, so this class of bug can't recur for any future type
  either.
- **`fit` couldn't shrink a hot/warm-heavy graph, both versions.**
  `fit_to_budget()` never called `compress()`, so it could only prune
  nodes already sitting in the `cold` tier — on a graph that hadn't been
  compressed yet (the common case), it did nothing and printed a
  misleading "protected content" excuse. It now compresses first; tested
  on a 26-node graph where it now legitimately archives 13 nodes instead
  of doing nothing.
- **Unhandled `KeyError` on a bad node id, both versions.** `resolve`
  (and anything else looking up a node by id) crashed with a raw
  traceback on a typo'd id. Every lookup now goes through one helper that
  raises a clean, catchable error with a useful message.
- **No atomic writes / no backup, both versions.** A process killed
  mid-save could corrupt the only copy of the graph. Saves now write to a
  temp file and `os.replace()` it in, and keep one backup generation;
  `load` recovers from the backup automatically if the main file is
  corrupted, with a printed warning either way.
- **No concurrency guard, both versions.** Two processes writing the same
  store could silently clobber each other. Added a simple, portable
  advisory lock (stale-lock detection included, so a crashed process
  can't deadlock a future run).
- **Packaging pointed at files that didn't exist, both versions.** Both
  versions' docs told the reader to run `scripts/context_graph.py`, but
  neither actually shipped a `scripts/` folder. `context_graph.py` now
  actually lives there.
- **Two different, disagreeing token-count heuristics, draft only.**
  `context_graph.py` and `benchmark.py` each had their own estimator.
  `benchmark.py` now imports the one in `context_graph.py` instead of
  re-implementing it.
- **Numbers that didn't match their own supporting code, draft only.**
  The draft's `SKILL.md` claimed 60% / 85% reduction; running its own
  `benchmark.py` actually produced 57.1% / 48.6%. This version's numbers
  (see `README.md`) are copied directly from a benchmark run, not
  hand-typed, so they can't drift out of sync with the code again.
- **Zero tests, both versions.** Added 23 stdlib `unittest` tests. Several
  are named regression tests for the exact bugs above, specifically so
  they can't come back unnoticed.
- **`__pycache__` committed to git, published repo only.** Added
  `.gitignore`.

## Added (new ideas from the draft, re-implemented)

- **`assumption` node type**, with a `confirmed` field and a new `confirm`
  command to flip it — kept from the draft's intent, fixed so it actually
  survives a round trip (see above), and extended so it's explicitly
  verifiable rather than just present.
- **`linked_to`**, so a node can point at the root goal or another node it
  bridges to — validated on write (must reference a real node) and
  carried through both export styles and both import parsers.
- **Visual tree export** (`export --style tree`), matching the branch/leaf
  notation now used in the in-chat `SKILL.md` template too, so the
  chat-only mode and the code-execution mode render the same way instead
  of being two unrelated formats.
- **`validate` command** — checks node types, tiers, and `linked_to` /
  edge references for dangling ids; read-only.

## Also new in this version

- `Priority Order` in `SKILL.md` is now the first thing after the
  philosophy section (it was present but easy to miss in the published
  repo, and absent from the draft) — a direct user instruction always
  overrides the skill's defaults, stated before any of the defaults
  themselves are.

## Renamed

- `context-barrier` -> `axon-tree` throughout (skill `name:`, headers,
  export banners, CLI help text).
- `skill.md` -> `SKILL.md`, matching the packaging convention this is
  meant to be loaded under.

## Deliberately scoped out of this pass

- The published repo's `SKILL.md` referenced five full worked examples
  under `references/` and a companion document-fidelity skill ("ZERON").
  Neither file ever actually shipped in the repo. This version keeps one
  compact worked example inline and a one-line mention that a fidelity
  companion skill (if present) is out of scope here, rather than
  reproducing content that didn't exist to begin with — worth writing for
  real in a follow-up if the worked-example bank is something you want
  back.
- A live, blinded LLM-vs-LLM evaluation of the token savings (as opposed
  to the illustrative, reproducible-but-not-scientific `benchmark.py`
  comparison) — flagged as future work in `GAPS_AND_IMPROVEMENTS.md`.
