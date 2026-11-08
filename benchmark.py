#!/usr/bin/env python3
"""
benchmark.py — illustrative token-count comparison for AXON TREE.

WHAT THIS IS: a same-author, hand-written "before" and "after" pair for a
few common scenarios, token-counted with the SAME estimator
context_graph.py uses (imported, not re-implemented — the previous draft
had two different, silently-disagreeing token heuristics; this repo has
exactly one).

WHAT THIS IS NOT: a blinded study, a real LLM eval, or proof that any given
conversation compresses by these exact percentages. Two people writing the
same two examples would get different numbers. Real compression on a real
session depends entirely on how much of that session is resolved history
versus live, protected (importance>=3) content — see fit_to_budget() and
its docstring. Treat the percentages below as "plausible, reproducible
from this file," not "guaranteed."

Run: python3 benchmark.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from context_graph import word_estimate_tokens  # noqa: E402  (single shared estimator)

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))

    TOKENIZER_LABEL = "tiktoken (cl100k_base) — exact"
except Exception:
    # Covers "not installed" (ImportError) as well as "installed but its
    # BPE data file couldn't be fetched/cached" (network-restricted
    # sandboxes, offline machines, etc.) — either way, fall back rather
    # than let an optional accuracy upgrade crash the whole script.
    count_tokens = word_estimate_tokens
    TOKENIZER_LABEL = "word-count heuristic (~1.3 tok/word) — approximate, tiktoken unavailable"


SCENARIOS = [
    {
        "name": "Explaining a concept (JWT auth)",
        "before": (
            "JSON Web Tokens, or JWTs, are a way of representing claims "
            "between two parties in a compact and self-contained manner. "
            "When a user logs in successfully, the server generates a "
            "signed token containing the user's identity and some "
            "metadata, and sends it back to the client. The client then "
            "stores this token, typically in local storage or a cookie, "
            "and includes it in the Authorization header of every "
            "subsequent request. The server can then verify the "
            "signature of the token without needing to look anything up "
            "in a database, which makes this approach highly scalable "
            "for distributed systems. However, because JWTs are usually "
            "stateless, revoking a token before it naturally expires is "
            "difficult, which is why many systems use short expiry times "
            "combined with a separate refresh token that can be revoked "
            "server-side."
        ),
        "after": (
            "- JWT = signed token proving identity, sent after login\n"
            "- Client stores it, sends it in the Authorization header\n"
            "- Server verifies the signature, no DB lookup needed\n"
            "- Good for scaling; hard to revoke early (stateless)\n"
            "- Fix: short expiry + separate, server-revocable refresh token"
        ),
    },
    {
        "name": "Resuming a coding session",
        "before": (
            "Okay so earlier we were working on the authentication system "
            "and we had decided to go with JWTs stored in httpOnly cookies "
            "instead of localStorage because of an XSS concern that came "
            "up during review. Then we ran into a bug where the refresh "
            "token wasn't rotating properly, which turned out to be "
            "because we were comparing the wrong timestamp field, and we "
            "fixed that. After that we started on the rate limiter but "
            "hadn't finished it yet, and there's still an open question "
            "about whether to use Redis or an in-memory store for it "
            "given that this might run across multiple server instances. "
            "We also need to remember that the client specifically asked "
            "for no third-party analytics scripts anywhere in the auth "
            "flow."
        ),
        "after": (
            "## AXON TREE — Context Map (flat)\n"
            "### Active\n"
            "- (BLOCKER) Rate limiter store: Redis vs in-memory — depends on multi-instance deployment\n"
            "### Established\n"
            "- (DECISION) JWT in httpOnly cookies: chosen over localStorage after an XSS review finding\n"
            "- (PREFERENCE) No third-party analytics in auth flow: explicit client requirement\n"
            "- (MISTAKE) Refresh token rotation bug: was comparing the wrong timestamp field — fixed\n"
        ),
    },
    {
        "name": "Summarizing a code review",
        "before": (
            "I looked through the pull request and overall the approach "
            "is reasonable, but I found a few issues worth raising. First, "
            "the new caching layer doesn't invalidate entries when the "
            "underlying record is deleted, only when it's updated, so "
            "stale reads are possible after a delete. Second, there's a "
            "N+1 query happening in the loop that builds the response "
            "payload, which will get slow as the dataset grows. Third, "
            "the new environment variable isn't documented anywhere in "
            "the README, so whoever deploys this next won't know it's "
            "required. None of these are blocking, but I'd want at least "
            "the cache invalidation issue fixed before this goes out."
        ),
        "after": (
            "- (BLOCKER) Cache not invalidated on delete: only handles updates, stale reads possible\n"
            "- (TASK) Fix N+1 query: response-builder loop, will slow down as data grows\n"
            "- (TASK) Document new env var: missing from README\n"
            "- (DECISION) Ship gate: cache invalidation fix required; other two are follow-ups"
        ),
    },
]


def run() -> None:
    print("=== AXON TREE TOKEN BENCHMARK ===")
    print(f"Tokenizer: {TOKENIZER_LABEL}\n")

    totals_before = totals_after = 0
    for s in SCENARIOS:
        before_tok = count_tokens(s["before"])
        after_tok = count_tokens(s["after"])
        reduction = 100 * (1 - after_tok / before_tok)
        totals_before += before_tok
        totals_after += after_tok
        print(f"--- {s['name']} ---")
        print(f"  Before : ~{before_tok:>4} tokens")
        print(f"  After  : ~{after_tok:>4} tokens")
        print(f"  Reduction: {reduction:.1f}%\n")

    overall = 100 * (1 - totals_after / totals_before)
    print("=== OVERALL (all scenarios combined) ===")
    print(f"  Before : ~{totals_before} tokens")
    print(f"  After  : ~{totals_after} tokens")
    print(f"  Reduction: {overall:.1f}%")
    print(
        "\nNOTE: these three examples are illustrative, not a scientific "
        "study — see the module docstring. Real per-session compression "
        "is reported by `context_graph.py stats` on your actual graph, "
        "which reflects your real content, not a canned example."
    )


if __name__ == "__main__":
    run()
