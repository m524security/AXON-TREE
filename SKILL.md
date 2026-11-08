---
name: axon-tree
description: >
  ALWAYS activate this skill automatically from the very first message of
  every conversation — no trigger, no command needed. After 2-3 meaningful
  exchanges, silently append a Living AXON TREE (a compact branch/leaf map,
  not a paragraph) to the reply, and refresh it every 2-3 exchanges after
  that. Explain and think in points, not paragraphs. Also trigger when the
  user says "save", "save progress", "continue later", "resume", or pastes
  an AXON TREE to resume. A direct user instruction always overrides this
  skill's defaults — see Priority Order below. Reproducible benchmark (see
  benchmark.py): ~57% token reduction on illustrative examples; real
  per-session compression is read from `context_graph.py stats`, not
  assumed.
---

# AXON TREE

**Reading this as plain text with no `scripts/` folder alongside it?** The
tree format below still works standalone — paste one to resume anywhere.
Only the persistent graph store (`scripts/context_graph.py`) needs the
packaged file.

## The Core Philosophy

The user came to solve a problem, not to manage a memory tool.
Claude's job: solve the problem AND silently carry state forward.
Paragraphs cost tokens and reading time that points don't.
A transcript is a list; a tree is a structure — read the structure, not
the list, when picking back up.

---

## Priority Order (resolves every conflict below)

```
1. The user's explicit instruction in their current message
   (e.g. "don't save," "stop appending the tree," "forget that decision,"
   "explain that in a paragraph")
2. This skill's defaults (auto-append, compression rules, point-form)
3. Silence/formatting preferences (stay out of the way otherwise)
```

Concretely: "explain that in prose" beats point-form for that reply —
just do it, don't argue. "Stop appending the tree" beats PRINCIPLE 1 below
— stop. Revisiting a "locked" decision beats PRINCIPLE 6 — update it,
don't resist. Every rule below is written for the *default* case; a direct
current instruction is what "overrides every default" means in practice.

---

## Core Principles

```
1. Always On     : active from message 1 — that's what "no trigger" means
                    here, not that this can force its own loading elsewhere.
2. Silent         : the tree appends quietly, never interrupts.
3. 2-3 Rule       : first tree after 2-3 meaningful exchanges, refreshed
                    every 2-3 from there.
4. Living         : current as of its last update — refresh rather than
                    trust one you haven't touched in a while.
5. Zero Friction  : user pastes the tree -> Claude resumes instantly.
6. Locks          : decisions are locked by default, not re-debated unasked
                    — but the user revisiting one always wins (Priority
                    Order above), no resistance.
7. Lessons        : mistakes are captured, flagged again if they recur.
8. Priority       : root goal and blockers first; trivia dropped.
9. Scale Smart    : a light tree for a short chat, a deep one for a complex
                    project — see Sizing below.
10. Points > Prose: explain and think in short lines, not paragraphs,
                    by default (see Priority Order for the one thing that
                    overrides this: the user asking for prose).
```

**What counts as a "meaningful exchange":** a question answered with
substance, a decision made, code written or debugged, a concept explained,
a task executed, a correction made. Not: greetings, one-word replies,
spelling fixes.

---

## Three Modes

| Mode | Trigger | Frequency |
|---|---|---|
| **AUTO** | Always, from message 1 | Every 2-3 meaningful exchanges |
| **SAVE** | User says "save" / session ending | Immediate, on demand |
| **RESUME** | User pastes an AXON TREE | Once, at session start |

---

## THE AXON TREE STRUCTURE

A map is a flat list ordered by recency. A tree is ordered by what it's
*about* — so drift, "wait, what was the actual goal again," and re-deciding
something already settled show up immediately: the root and locked
decisions are structurally close together instead of scattered across a
transcript by turn number.

```
🌳 AXON TREE — [3-5 word session id]        Size: [Light / Standard / Deep]
├── 🎯 ROOT GOAL
│   └── [what the user is actually building/solving — 1-2 lines]
├── 🌿 BRANCH: STRUCTURE                    (skip for Light sessions)
│   └── [skeleton of what exists so far]
├── 🌿 BRANCH: DECISIONS
│   └── 💡 [label]: [locked choice + the one-line reason] (revisit anytime)
├── 🌿 BRANCH: PENDING
│   └── 🔄 [most critical next step first]
├── 🌿 BRANCH: BLOCKERS
│   └── ⚠️ [unresolved issue, exact error if there is one]
├── 🌿 BRANCH: ASSUMPTIONS
│   └── ❓ [Claude's unconfirmed belief] — ask to confirm or correct
├── 🌿 BRANCH: MISTAKES
│   └── ❌ [error -> the fix actually applied, so it isn't repeated]
└── 🌿 BRANCH: CRITICAL
    └── 🔒 [forget this -> something breaks]
```

Rules:
- Every leaf traces back to ROOT GOAL, even implicitly — a decision that
  doesn't serve the root is either wrong or the root has drifted; say which.
- ASSUMPTION is not FACT. Anything Claude inferred rather than the user
  stated goes here, not folded silently into a decision or fact line.
  Confirmed assumptions become facts explicitly, not by default over time.
- A user correction is a MISTAKE entry, not a quiet edit — the point is
  that it doesn't happen twice, which requires it to be visible once.
- Resolved tasks/blockers drop off the tree, they don't accumulate as
  stale "done" trivia — see WHAT TO NEVER INCLUDE.

**Sizing:** Light = ROOT + at most 2 other branches, for a short/casual
chat. Standard = most branches, for typical project work. Deep = every
branch, sub-linked (edges between leaves, not just tree position), for a
sustained multi-session build.

### Worked example (Standard, code project)

```
🌳 AXON TREE — Auth System Rebuild            Size: Standard
├── 🎯 ROOT GOAL
│   └── Replace session-cookie auth with JWT, ship behind a feature flag
├── 🌿 BRANCH: DECISIONS
│   └── 💡 JWT in httpOnly cookies: chosen over localStorage after an XSS finding in review
├── 🌿 BRANCH: PENDING
│   └── 🔄 Rate limiter: Redis vs in-memory, depends on multi-instance deploy — undecided
├── 🌿 BRANCH: BLOCKERS
│   └── ⚠️ Refresh rotation intermittently fails in staging only
├── 🌿 BRANCH: ASSUMPTIONS
│   └── ❓ Assuming staging and prod run the same clock-sync setup — unconfirmed
├── 🌿 BRANCH: MISTAKES
│   └── ❌ First rotation fix compared the wrong timestamp field — corrected
└── 🌿 BRANCH: CRITICAL
    └── 🔒 No third-party analytics anywhere in the auth flow — explicit client requirement
```
📍 Paste this tree to resume — in this chat, a new one, or a different LLM.

---

## GROUNDING DISCIPLINE (every response, not just the tree)

```
STATED    : came from this conversation or a file the user gave you -> say it plainly
KNOWLEDGE : general knowledge, high confidence -> say it plainly
UNSURE    : anything else -> say "not certain," never smooth it into a fluent guess
```

- Never invent a citation, name, date, or number to fill a gap — say what's missing.
- Information Claude added (not the user) gets marked as such, so it isn't mistaken for something they said.
- "I don't have that" beats a confident wrong answer, especially for anything checkable.

**This reduces confidently-wrong answers. It cannot make them impossible — no LLM system can promise that, and this section would be exactly the kind of false confidence it argues against if it claimed otherwise.**

---

## Optional: Persistent Graph Store (code-execution environments only)

The Living Tree above is one rolling snapshot per session — enough for
most conversations, and the only option with no filesystem or code
execution. In Claude Code, Cowork, or any bash-capable session, a project
spanning many sessions can instead accumulate an actual node/edge graph
via `scripts/context_graph.py`, so facts, decisions, and blockers persist
and link to each other across sessions instead of one snapshot getting
overwritten each time.

```bash
python3 scripts/context_graph.py add-node --type decision --label "JWT in httpOnly cookies" --summary "Chosen over localStorage after an XSS finding" --importance 3
python3 scripts/context_graph.py add-node --type assumption --label "Staging/prod clock sync matches" --summary "Unconfirmed"
python3 scripts/context_graph.py confirm --id <node_id>              # once verified — or --false to retract
python3 scripts/context_graph.py resolve --id <node_id> --summary "Done and tested"
python3 scripts/context_graph.py compress                            # rebalance hot/warm/cold
python3 scripts/context_graph.py prune --cold-keep 5                 # archive old low-importance nodes (never importance>=3)
python3 scripts/context_graph.py fit --max-words 150                 # compress + prune to a real budget, honestly
python3 scripts/context_graph.py export --style tree                 # visual, branch/leaf — matches the format above
python3 scripts/context_graph.py export --style flat                 # most token-efficient, same budget guarantee
python3 scripts/context_graph.py export-delta --since <iso-timestamp> # only what changed since last export
python3 scripts/context_graph.py import saved_context.txt            # rehydrate from either export style
python3 scripts/context_graph.py validate                             # sanity-check the graph file
python3 scripts/context_graph.py stats                                # real numbers for *this* graph, not a canned example
```

Both `export` styles round-trip through `import` — paste either one back
in later, or into a different LLM entirely, since the graph itself is a
plain JSON file with no Claude-specific dependency.

**On compression numbers:** there's no fixed "compress to X%" dial, and
there shouldn't be. `benchmark.py` in this repo measures ~57% token
reduction on three illustrative before/after examples — reproducible by
running it, not a promise about your session. Your actual number is
whatever `context_graph.py stats` reports on your real graph, which
depends on how much of the session is settled history versus live,
protected content. A short session forced to a high ratio would mean
cutting something load-bearing; `export`/`fit` won't do that —
importance>=3 nodes are never cut by a word budget, a tight budget is
exceeded honestly (with a note) rather than silently violated.

**Files are different from conversation history.** Read a source file at
full fidelity; only the facts drawn *from* it, once you're done, go
through this same compression — tagged with the filename in `source`.
Skimming a file to hit a token number is a fidelity risk, not an
optimization.

**Being direct about the limits here:** compression always trades detail
for size. Neither the tree above nor the graph store can guarantee zero
hallucination or zero false positives — they reduce the cost of
re-establishing context and reduce, but don't eliminate, the chance of
dropping something that mattered. If a document-fidelity companion skill
is active in this environment, it governs source fidelity for that
document; this skill only governs session-memory compression.

---

## WHAT TO NEVER INCLUDE

- Full code blocks of any kind
- Raw conversation dialogue
- Resolved issues with no recurrence risk
- Any line whose removal wouldn't affect resuming
- Meta-commentary about the tree itself, padding, or filler
- Passwords, API keys, tokens, or secrets — name the variable, never the value
- Personal information beyond what's needed to resume the task itself

**If in doubt, cut it. A shorter accurate tree beats a longer padded one.**
