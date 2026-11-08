#!/usr/bin/env python3
"""
context_graph.py — AXON TREE's dependency-free node/edge memory graph.

Stores distilled facts, decisions, and tasks as a graph (not a transcript),
compresses older/low-importance nodes over time (hot -> warm -> cold), and
exports/imports a compact plain-text block that can be pasted into ANY
chat-based LLM (Claude, ChatGPT, Gemini, GLM, etc.) to restore context.

Storage: a single JSON file (default: ./.context_map/graph.json), written
atomically with a one-generation backup, plus a simple advisory lock so two
processes don't clobber the same store at once.

No dependencies beyond the Python 3 standard library — this is intentional,
so it runs the same way in a terminal, an IDE, Cowork, or any bash tool
without an install step.

This script does not call any LLM and does not claim to prevent
hallucination or guarantee correctness — it only stores and compresses
whatever it's given, faithfully. See "Being direct about the limits here"
in this script's parent SKILL.md for what it does and doesn't do.
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
DEFAULT_STORE = Path(".context_map/graph.json")

NODE_TYPES = {"goal", "decision", "fact", "task", "blocker", "preference", "mistake", "assumption"}
TIERS = ("hot", "warm", "cold", "archived")

TAG_BY_TYPE = {
    "decision": "DECISION",
    "blocker": "BLOCKER",
    "mistake": "MISTAKE",
    "goal": "GOAL",
    "task": "TASK",
    "preference": "PREFERENCE",
    "fact": "FACT",
    "assumption": "ASSUMPTION",
}
# Single-letter tags for --compact export. A second, shorter alphabet, not a
# replacement — full tags stay the default because they're what makes the
# format readable without this file open. Import accepts either.
TAG_SHORT_BY_TYPE = {
    "decision": "D",
    "blocker": "B",
    "mistake": "M",
    "goal": "G",
    "task": "T",
    "preference": "P",
    "fact": "F",
    "assumption": "A",
}
TYPE_BY_TAG = {v: k for k, v in TAG_BY_TYPE.items()}
for _type, _short in TAG_SHORT_BY_TYPE.items():
    TYPE_BY_TAG.setdefault(_short, _type)  # never overrides a full-word tag
CONFIRMED_MARK = " ✓"  # trailing marker so a confirmed assumption survives export -> import

EMOJI_BY_TYPE = {
    "goal": "🎯",
    "decision": "💡",
    "fact": "🍃",
    "task": "🔄",
    "blocker": "⚠️",
    "preference": "❤️",
    "mistake": "❌",
    "assumption": "❓",
}

# One format per export style. Both are understood by import_block().
# NOTE: a label containing ": " will confuse either parser (the first
# ": " is taken as the label/summary boundary) — add_node() warns on this.
FLAT_LINE_RE = re.compile(r"^-\s\((\w+)\)\s(.+?):\s(.+?)(?:\s\(Linked to:\s(.+?)\)|\s→(\S+))?$")
TREE_BRANCH_RE = re.compile(r"BRANCH:\s*(\w+)")
TREE_LEAF_RE = re.compile(r"^[\s│├└─]*[^\w#]*\s*(.+?):\s(.+?)(?:\s\(Linked to:\s(.+?)\)|\s→(\S+))?$")

_TIER_RANK = {"hot": 0, "warm": 1, "cold": 2, "archived": 3}


class AxonError(Exception):
    """User-facing error (bad id, corrupt file, bad type...). Caught at the
    CLI boundary in main() and printed cleanly instead of a raw traceback."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Storage: atomic writes, one-generation backup, portable advisory lock
# ---------------------------------------------------------------------------

def _empty_graph() -> dict:
    return {"schema_version": SCHEMA_VERSION, "nodes": {}, "edges": []}


def _upgrade_schema(graph: dict) -> dict:
    """Best-effort upgrade of graphs saved by an older schema. Only ever
    adds missing fields with safe defaults — never drops a node."""
    if graph.get("schema_version", 1) < 2:
        for n in graph.get("nodes", {}).values():
            n.setdefault("linked_to", None)
            n.setdefault("confirmed", None)
        graph["schema_version"] = 2
    return graph


def load_graph(path: Path) -> dict:
    if not path.exists():
        return _empty_graph()
    try:
        with open(path, "r") as f:
            graph = json.load(f)
    except json.JSONDecodeError as e:
        backup = path.with_suffix(path.suffix + ".bak")
        if backup.exists():
            with open(backup, "r") as f:
                graph = json.load(f)
            print(f"WARNING: {path} was corrupted ({e}); recovered from {backup}. "
                  f"The corrupted file was left on disk for inspection.", file=sys.stderr)
        else:
            raise AxonError(
                f"{path} is corrupted ({e}) and no backup ({backup}) exists. "
                f"Nothing was overwritten — fix or remove the file manually."
            )
    return _upgrade_schema(graph)


def save_graph(path: Path, graph: dict) -> None:
    """Atomic write: build the new content in a temp file, then os.replace()
    it over the target (atomic on POSIX and Windows) — a crash mid-write
    can never leave a half-written graph.json. Keeps one backup generation
    of whatever was on disk *before* this save, so a bad write is still
    recoverable from the prior good state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    graph["schema_version"] = SCHEMA_VERSION

    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            backup.write_bytes(path.read_bytes())
        except OSError:
            pass  # backup is best-effort; never block a save over it

    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump(graph, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextmanager
def locked_store(path: Path, timeout=10, stale_after=30):
    """Simple, portable advisory lock (no fcntl — stays POSIX+Windows
    portable) so two processes don't write the same store at once. Steals
    a lock older than `stale_after` seconds, assuming its holder crashed."""
    lock_path = path.parent / (path.name + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > stale_after:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.time() - start > timeout:
                raise AxonError(f"Could not acquire lock {lock_path} after {timeout}s — "
                                 f"another process may be using this store.")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Graph mutation
# ---------------------------------------------------------------------------

def _require_node(graph: dict, node_id: str) -> dict:
    node = graph["nodes"].get(node_id)
    if node is None:
        raise AxonError(f"No node with id '{node_id}'. Run 'list' to see valid ids.")
    return node


def add_node(graph, node_type, label, summary="", importance=2, source=None, linked_to=None) -> str:
    if node_type not in NODE_TYPES:
        raise AxonError(f"type must be one of {sorted(NODE_TYPES)}, got '{node_type}'")
    if importance not in (1, 2, 3):
        raise AxonError(f"importance must be 1, 2, or 3, got {importance!r}")
    if linked_to is not None and linked_to not in graph["nodes"]:
        raise AxonError(f"linked_to='{linked_to}' does not match any existing node id")
    if ": " in label:
        print(f"WARNING: label contains ': ' — this can confuse the plain-text "
              f"parser on import. Consider rewording: '{label}'", file=sys.stderr)
    node_id = uuid.uuid4().hex[:8]
    graph["nodes"][node_id] = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "summary": summary,
        "importance": importance,  # 1 (low) .. 3 (critical, never auto-demoted/cut)
        "tier": "hot",
        "created": _now(),
        "updated": _now(),
        "source": source,       # free text, e.g. "turn 12" or a filename
        "linked_to": linked_to,  # id of another node this one semantically bridges to
        "confirmed": False if node_type == "assumption" else None,
    }
    return node_id


def confirm_node(graph, node_id, confirmed=True) -> None:
    """Mark an assumption as verified (or explicitly un-verified). Only
    applies to type='assumption' — turns an open question into something
    checked instead of leaving it silently unresolved forever."""
    n = _require_node(graph, node_id)
    if n["type"] != "assumption":
        raise AxonError(f"'{node_id}' is type '{n['type']}', not 'assumption' — "
                         f"confirm only applies to assumptions.")
    n["confirmed"] = confirmed
    n["updated"] = _now()


def resolve_node(graph, node_id, resolution_summary=None, new_importance=1) -> None:
    """Mark a task/blocker as resolved: converts it to a low-importance
    'fact', eligible for cold/archive on the next compress()+prune()."""
    n = _require_node(graph, node_id)
    n["type"] = "fact"
    if resolution_summary is not None:
        n["summary"] = resolution_summary
    n["importance"] = new_importance
    n["tier"] = "warm"
    n["updated"] = _now()


def add_edge(graph, src, dst, relation) -> None:
    _require_node(graph, src)
    _require_node(graph, dst)
    graph["edges"].append({"from": src, "to": dst, "relation": relation})


def compress(graph, hot_limit=5, warm_limit=8, cold_trim_words=12) -> None:
    """Demote nodes hot -> warm -> cold as the graph grows. Only ever
    changes `tier` (and, on cold, trims `summary` to cold_trim_words) —
    never invents or rewrites underlying content. importance>=3 is never
    auto-demoted."""
    nodes = graph["nodes"]
    hot = sorted((n for n in nodes.values() if n["tier"] == "hot"),
                 key=lambda n: (n["importance"], n["updated"]))
    warm = [n for n in nodes.values() if n["tier"] == "warm"]

    while len(hot) > hot_limit:
        n = hot.pop(0)
        if n["importance"] >= 3:
            continue
        n["tier"] = "warm"
        n["updated"] = _now()
        warm.append(n)

    warm.sort(key=lambda n: (n["importance"], n["updated"]))
    while len(warm) > warm_limit:
        n = warm.pop(0)
        if n["importance"] >= 3:
            continue
        words = n["summary"].split()
        n["summary"] = " ".join(words[:cold_trim_words]) + ("…" if len(words) > cold_trim_words else "")
        n["tier"] = "cold"
        n["updated"] = _now()


def prune(graph, cold_max_keep=2) -> int:
    """Move the oldest, lowest-importance cold nodes to 'archived' once
    cold exceeds cold_max_keep. Nothing is deleted — archived nodes stay in
    the JSON file, just excluded from export_block(). importance>=3 is
    never archived. Returns the number of nodes archived by this call."""
    cold = sorted(
        (n for n in graph["nodes"].values() if n["tier"] == "cold" and n["importance"] < 3),
        key=lambda n: n["updated"],
    )
    archived = 0
    while len(cold) > max(cold_max_keep, 0):
        n = cold.pop(0)
        n["tier"] = "archived"
        n["updated"] = _now()
        archived += 1
    return archived


def fit_to_budget(graph, max_words, hot_limit=5, warm_limit=8, cold_keep_steps=(20, 10, 5, 2, 0), compact=False) -> tuple:
    """Prune progressively until the export fits max_words, or report
    honestly that it can't without cutting protected content.

    FIXED vs. the original: this now calls compress() first so hot/warm
    content actually gets pushed down into cold before pruning runs — the
    original only ever pruned nodes already sitting in the cold tier, so it
    could not shrink a graph that hadn't been compressed yet (the common
    case), and returned a misleading "protected content" excuse instead.
    """
    compress(graph, hot_limit=hot_limit, warm_limit=warm_limit)
    for keep in cold_keep_steps:
        prune(graph, cold_max_keep=keep)
        text = export_block(graph, max_words=10**9, compact=compact)
        if len(text.split()) <= max_words:
            return text, True
    return export_block(graph, max_words=max_words, compact=compact), False


# ---------------------------------------------------------------------------
# Export / import — one line-renderer shared by every path so "what export
# writes" and "what import expects" cannot drift apart again.
# ---------------------------------------------------------------------------

def _render_leaf(n: dict, compact: bool = False) -> tuple:
    if compact:
        tag = TAG_SHORT_BY_TYPE.get(n["type"], n["type"][:1].upper())
    else:
        tag = TAG_BY_TYPE.get(n["type"], n["type"].upper())
    src = f" [{n['source']}]" if n.get("source") else ""
    if n.get("linked_to"):
        linked = f" →{n['linked_to']}" if compact else f" (Linked to: {n['linked_to']})"
    else:
        linked = ""
    # A confirmed assumption carries a trailing mark so `confirmed` survives
    # a text export -> import round trip instead of only living in the JSON.
    mark = CONFIRMED_MARK if n["type"] == "assumption" and n.get("confirmed") else ""
    return tag, f"{n['label']}: {n['summary']}{src}{linked}{mark}"


def _tier_section(nodes, tier, title) -> str:
    items = [n for n in nodes if n["tier"] == tier]
    if not items:
        return ""
    items.sort(key=lambda n: -n["importance"])
    lines = [f"### {title}"]
    for n in items:
        tag, body = _render_leaf(n)
        lines.append(f"- ({tag}) {body}")
    return "\n".join(lines)


def _select_within_budget(nodes, max_words, line_fn):
    """Shared knapsack used by both export styles: importance>=3 nodes are
    always kept in full; importance<3 nodes are added back (highest
    importance / hottest tier first) while they still fit. `line_fn(n)`
    renders one node to its final text line for whichever style is asking.
    Returns (kept_nodes, dropped_count, used_words, hit_target)."""
    entries = [{"node": n, "importance": n["importance"],
                "tier_rank": _TIER_RANK.get(n["tier"], 9),
                "words": len(line_fn(n).split())} for n in nodes]

    full_words = sum(e["words"] for e in entries)
    if not entries or full_words <= max_words:
        return [e["node"] for e in entries], 0, full_words, True

    protected = [e for e in entries if e["importance"] >= 3]
    optional = sorted((e for e in entries if e["importance"] < 3),
                       key=lambda e: (-e["importance"], e["tier_rank"]))

    kept = list(protected)
    used = sum(e["words"] for e in protected)
    for e in optional:
        if used + e["words"] > max_words:
            continue
        kept.append(e)
        used += e["words"]

    dropped = len(entries) - len(kept)
    return [e["node"] for e in kept], dropped, used, used <= max_words


def export_flat(graph, max_words=400, compact=False) -> str:
    """Tier-grouped (Active/Established/Background) plain block — the most
    token-efficient style. This is the round-trip-guaranteed default.
    compact=True: single-letter tags, "→id" instead of "(Linked to: id)",
    a shorter banner — for when every extra token counts."""
    nodes = [n for n in graph["nodes"].values() if n["tier"] != "archived"]
    archived_count = sum(1 for n in graph["nodes"].values() if n["tier"] == "archived")
    tier_title = {"hot": "Active", "warm": "Established", "cold": "Background"}

    def line_fn(n):
        tag, body = _render_leaf(n, compact)
        return f"- ({tag}) {body}"

    kept, dropped, used, hit = _select_within_budget(nodes, max_words, line_fn)

    by_tier = {}
    for n in sorted(kept, key=lambda n: -n["importance"]):
        by_tier.setdefault(n["tier"], []).append(line_fn(n))
    parts = [f"### {tier_title[t]}\n" + "\n".join(by_tier[t]) for t in ("hot", "warm", "cold") if by_tier.get(t)]
    body = "\n\n".join(parts) if parts else "(graph is empty)"

    if archived_count:
        body += f"\n\n_{archived_count} archived._" if compact else \
            f"\n\n_{archived_count} older, resolved item(s) archived (not deleted — ask to see them if needed)._"
    if dropped:
        if compact:
            note = f"\n\n_{dropped} cut ({max_words}w budget)._"
        else:
            note = f"\n\n_{dropped} lower-priority item(s) cut to fit {max_words} words"
            if not hit:
                note += " — protected/critical items alone already exceed this budget, so they're shown in full rather than cut"
            note += "._"
        body += note

    if compact:
        header, footer = "## AXON TREE (flat)\n", "\n\n_Paste to resume._"
    else:
        header = "## AXON TREE — Context Map (flat)\n"
        footer = "\n\n_Paste this block as your first message in any LLM chat to resume._"
    return header + body + footer


def export_tree(graph, max_words=400, compact=False) -> str:
    """Branch/leaf visual grouped by type — easiest to skim at a glance.
    Carries the same word-budget guarantee as export_flat() and is
    round-trip-safe: import_block() understands this style too."""
    nodes = [n for n in graph["nodes"].values() if n["tier"] != "archived"]
    archived_count = sum(1 for n in graph["nodes"].values() if n["tier"] == "archived")

    def line_fn(n):
        emoji = EMOJI_BY_TYPE.get(n["type"], "🍃")
        _, body = _render_leaf(n, compact)
        return f"{emoji} {body}"

    kept, dropped, used, hit = _select_within_budget(nodes, max_words, line_fn)
    if compact:
        header, footer = "## AXON TREE (visual)\n", "\n\n_Paste to resume._"
    else:
        header = "## AXON TREE (Visual Export)\n"
        footer = "\n\n_Paste this tree to resume session with minimal token usage._"

    if not kept:
        return header + "🌳 AXON TREE: (empty)" + footer

    branches = {}
    for n in kept:
        branches.setdefault(n["type"].upper(), []).append(n)

    root = next((n for n in kept if n["type"] == "goal"), None)
    lines = ["🌳 AXON TREE MAP" + (f" [Root: {root['label']}]" if root else "")]
    branch_names = sorted(branches)
    for i, b in enumerate(branch_names):
        is_last_branch = i == len(branch_names) - 1
        lines.append(("└── " if is_last_branch else "├── ") + f"🌿 BRANCH: {b}")
        b_nodes = branches[b]
        for j, n in enumerate(b_nodes):
            indent = "    " if is_last_branch else "│   "
            leaf_prefix = "└── " if j == len(b_nodes) - 1 else "├── "
            lines.append(indent + leaf_prefix + line_fn(n))

    body = "\n".join(lines)
    if archived_count:
        body += f"\n\n_{archived_count} archived._" if compact else f"\n\n_{archived_count} older item(s) archived (not deleted)._"
    if dropped:
        if compact:
            note = f"\n\n_{dropped} cut ({max_words}w budget)._"
        else:
            note = f"\n\n_{dropped} lower-priority item(s) cut to fit {max_words} words"
            if not hit:
                note += " — protected/critical items alone already exceed this budget"
            note += "._"
        body += note
    return header + body + footer


def export_block(graph, max_words=400, style="flat", compact=False) -> str:
    """style='flat' (default, most token-efficient) or 'tree' (visual).
    compact=True shortens tags/links/banner further on top of either style.
    Both styles, compact or not, are accepted back by import_block()."""
    if style == "tree":
        return export_tree(graph, max_words, compact)
    return export_flat(graph, max_words, compact)


def export_delta(graph, since_iso: str, max_words=400) -> str:
    """Export only nodes created/updated after `since_iso`. NOTE: unlike
    export_block(), this truncates with a plain word-count cut, not the
    importance-protected knapsack — use `fit` instead if that guarantee
    matters for this call."""
    nodes = list(graph["nodes"].values())
    changed = [n for n in nodes if n["updated"] > since_iso]
    unchanged_count = len(nodes) - len(changed)

    sections = [
        _tier_section(changed, "hot", "Active"),
        _tier_section(changed, "warm", "Established"),
        _tier_section(changed, "cold", "Background"),
    ]
    body = "\n\n".join(s for s in sections if s)
    if not body:
        body = "(nothing changed since last export)"
    if unchanged_count:
        body += f"\n\n_{unchanged_count} item(s) unchanged since {since_iso} — not repeated here._"

    words = body.split()
    if len(words) > max_words:
        body = " ".join(words[:max_words])
        body += "\n\n_[truncated to the word budget — this does not protect importance>=3 lines the way export/fit do.]_"
    header = "## AXON TREE — Delta Export\n"
    footer = "\n\n_Paste alongside your last full map — only what changed is listed above._"
    return header + body + footer


def import_block(graph, text, default_tier="warm") -> list:
    """Parse a previously exported block — either style, compact or not —
    back into nodes. Only reconstructs lines that match a known shape;
    never infers or fills in missing detail."""
    added = []
    tier = default_tier
    current_branch_type = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        confirmed = line.endswith(CONFIRMED_MARK)
        if confirmed:
            line = line[: -len(CONFIRMED_MARK)]

        if line.startswith("### Active"):
            tier, current_branch_type = "hot", None
            continue
        if line.startswith("### Established"):
            tier, current_branch_type = "warm", None
            continue
        if line.startswith("### Background"):
            tier, current_branch_type = "cold", None
            continue

        branch_m = TREE_BRANCH_RE.search(line)
        if branch_m:
            raw = branch_m.group(1)
            current_branch_type = raw.lower() if raw.lower() in NODE_TYPES else TYPE_BY_TAG.get(raw, "fact")
            continue

        flat_m = FLAT_LINE_RE.match(line)
        if flat_m:
            tag, label, summary, linked_v, linked_c = flat_m.groups()
            node_type = TYPE_BY_TAG.get(tag, "fact")
            linked = linked_v or linked_c
        elif current_branch_type:
            leaf_m = TREE_LEAF_RE.match(line)
            if not leaf_m:
                continue
            label, summary, linked_v, linked_c = leaf_m.groups()
            node_type = current_branch_type
            linked = linked_v or linked_c
        else:
            continue

        node_id = add_node(graph, node_type, label, summary, importance=2, source="imported")
        if linked:
            graph["nodes"][node_id]["linked_to"] = linked
        if confirmed and node_type == "assumption":
            graph["nodes"][node_id]["confirmed"] = True
        graph["nodes"][node_id]["tier"] = tier
        added.append(node_id)

    return added


def word_estimate_tokens(text: str) -> int:
    # Rough heuristic only (~1.3 tokens/word for English) — not an exact
    # tokenizer. benchmark.py imports this exact function so the two
    # scripts in this repo can never quietly disagree about what a
    # "token" is the way two separate estimators once did.
    return int(len(text.split()) * 1.3)


def compute_stats(graph) -> dict:
    nodes = list(graph["nodes"].values())
    by_tier = {t: sum(1 for n in nodes if n["tier"] == t) for t in TIERS}
    block = export_block(graph, max_words=10**9)
    return {
        "total_nodes": len(nodes),
        "by_tier": by_tier,
        "edges": len(graph["edges"]),
        "unconfirmed_assumptions": sum(1 for n in nodes if n["type"] == "assumption" and not n.get("confirmed")),
        "export_word_count": len(block.split()),
        "export_token_estimate": word_estimate_tokens(block),
        "protected_nodes_importance_3": sum(1 for n in nodes if n["importance"] >= 3),
    }


def validate_graph(graph) -> list:
    """Sanity-check the graph; returns a list of problem strings (empty =
    clean). Read-only — never modifies anything. Duplicate (type, label)
    pairs are flagged, not merged — a human call, not an automatic one."""
    problems = []
    seen = {}
    for node_id, n in graph["nodes"].items():
        if n.get("type") not in NODE_TYPES:
            problems.append(f"node {node_id}: unknown type '{n.get('type')}'")
        if n.get("tier") not in TIERS:
            problems.append(f"node {node_id}: unknown tier '{n.get('tier')}'")
        linked = n.get("linked_to")
        if linked and linked not in graph["nodes"]:
            problems.append(f"node {node_id}: linked_to '{linked}' does not exist")
        if n.get("tier") != "archived":
            key = (n.get("type"), (n.get("label") or "").strip().lower())
            if key in seen:
                problems.append(f"node {node_id}: duplicate of {seen[key]} — same type+label, consider 'resolve' or removing one")
            else:
                seen[key] = node_id
    for e in graph["edges"]:
        if e["from"] not in graph["nodes"]:
            problems.append(f"edge {e['from']}->{e['to']}: '{e['from']}' does not exist")
        if e["to"] not in graph["nodes"]:
            problems.append(f"edge {e['from']}->{e['to']}: '{e['to']}' does not exist")
    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AXON TREE — portable node/edge context graph.")
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="Path to the JSON graph file.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create an empty graph file.")

    p = sub.add_parser("add-node", help="Add a node to the graph.")
    p.add_argument("--type", required=True, choices=sorted(NODE_TYPES))
    p.add_argument("--label", required=True)
    p.add_argument("--summary", default="")
    p.add_argument("--importance", type=int, default=2, choices=[1, 2, 3])
    p.add_argument("--source", default=None)
    p.add_argument("--linked-to", dest="linked_to", default=None, help="id of another node this one bridges to")

    p = sub.add_parser("confirm", help="Mark an assumption node as verified (or --false to un-verify).")
    p.add_argument("--id", required=True)
    p.add_argument("--false", dest="confirmed", action="store_false", default=True)

    p = sub.add_parser("resolve", help="Mark a task/blocker as resolved (becomes a low-importance, archivable fact).")
    p.add_argument("--id", required=True)
    p.add_argument("--summary", default=None)
    p.add_argument("--importance", type=int, default=1, choices=[1, 2, 3])

    p = sub.add_parser("add-edge", help="Link two existing nodes.")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--relation", required=True)

    p = sub.add_parser("compress", help="Rebalance hot/warm/cold tiers.")
    p.add_argument("--hot-limit", type=int, default=5)
    p.add_argument("--warm-limit", type=int, default=8)
    p.add_argument("--cold-trim", type=int, default=12, help="Max summary words kept once a node reaches cold tier.")

    p = sub.add_parser("prune", help="Archive old, low-importance cold nodes (never touches importance>=3).")
    p.add_argument("--cold-keep", type=int, default=2)

    p = sub.add_parser("fit", help="Compress + prune progressively until the export fits a word budget.")
    p.add_argument("--max-words", type=int, required=True)
    p.add_argument("--compact", action="store_true", help="Short tags/links/banner for maximum token savings.")

    p = sub.add_parser("export", help="Print a portable, pasteable text block.")
    p.add_argument("--max-words", type=int, default=400)
    p.add_argument("--style", choices=["flat", "tree"], default="flat")
    p.add_argument("--compact", action="store_true", help="Short tags/links/banner for maximum token savings.")

    p = sub.add_parser("export-delta", help="Print only what changed since a given timestamp.")
    p.add_argument("--since", required=True, help="ISO timestamp — export only nodes updated after this.")
    p.add_argument("--max-words", type=int, default=400)

    p = sub.add_parser("import", help="Rehydrate nodes from a previously exported block (either style).")
    p.add_argument("file")

    sub.add_parser("list", help="List all nodes with id, tier, and type.")
    sub.add_parser("stats", help="Print graph size and export-cost stats as JSON.")
    sub.add_parser("validate", help="Sanity-check the graph and report any problems.")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = Path(args.store)

    try:
        with locked_store(store):
            graph = load_graph(store)

            if args.command == "init":
                save_graph(store, graph)
                print(f"Initialized empty graph at {store}")

            elif args.command == "add-node":
                node_id = add_node(graph, args.type, args.label, args.summary, args.importance, args.source, args.linked_to)
                save_graph(store, graph)
                print(f"Added node {node_id} ({args.type}): {args.label}")

            elif args.command == "confirm":
                confirm_node(graph, args.id, args.confirmed)
                save_graph(store, graph)
                print(f"{'Confirmed' if args.confirmed else 'Un-confirmed'} assumption {args.id}")

            elif args.command == "resolve":
                resolve_node(graph, args.id, args.summary, args.importance)
                save_graph(store, graph)
                print(f"Resolved {args.id} — now a low-importance fact, eligible for archiving.")

            elif args.command == "add-edge":
                add_edge(graph, args.src, args.dst, args.relation)
                save_graph(store, graph)
                print(f"Linked {args.src} -> {args.dst} ({args.relation})")

            elif args.command == "compress":
                before = len(graph["nodes"])
                compress(graph, args.hot_limit, args.warm_limit, args.cold_trim)
                save_graph(store, graph)
                print(f"Compressed. {before} node(s) retained; tiers rebalanced hot/warm/cold.")

            elif args.command == "prune":
                archived = prune(graph, args.cold_keep)
                save_graph(store, graph)
                print(f"Archived {archived} node(s). Nothing deleted — still in {store}, just left out of exports.")

            elif args.command == "fit":
                text, hit_target = fit_to_budget(graph, args.max_words, compact=args.compact)
                save_graph(store, graph)
                if not hit_target:
                    print(f"NOTE: could not fit {args.max_words} words without cutting protected "
                          f"(importance>=3) content — showing the smallest safe version instead.\n")
                print(text)

            elif args.command == "export":
                print(export_block(graph, args.max_words, args.style, args.compact))

            elif args.command == "export-delta":
                print(export_delta(graph, args.since, args.max_words))

            elif args.command == "import":
                text = Path(args.file).read_text()
                added = import_block(graph, text)
                save_graph(store, graph)
                print(f"Imported {len(added)} node(s) from {args.file}")

            elif args.command == "list":
                for n in graph["nodes"].values():
                    print(f"[{n['tier']:4}] {n['id']}  ({n['type']})  {n['label']}")

            elif args.command == "stats":
                print(json.dumps(compute_stats(graph), indent=2))

            elif args.command == "validate":
                problems = validate_graph(graph)
                if problems:
                    print(f"{len(problems)} problem(s) found:")
                    for p in problems:
                        print(f"  - {p}")
                    sys.exit(1)
                print("OK — no problems found.")

    except AxonError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
