#!/usr/bin/env python3
"""
Regression + coverage tests for context_graph.py.

Run with:  python3 -m unittest discover -s tests -v
(stdlib unittest only — no pytest/install step needed.)

Several tests here exist specifically because the previous draft of this
tool shipped without any tests at all, and four independent bugs reached
"done" as a result: a stray-paren syntax error, a dropped-output bug, an
export/import format mismatch, and a silently-ignored --max-words flag.
Each has a named regression test below so none of them can come back
unnoticed.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import context_graph as cg  # noqa: E402


class AxonTreeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = Path(self._tmpdir.name) / "graph.json"
        self.graph = cg.load_graph(self.store)

    def tearDown(self):
        self._tmpdir.cleanup()


class TestBasicMutation(AxonTreeTestCase):
    def test_add_and_list_node(self):
        node_id = cg.add_node(self.graph, "goal", "Ship it", "root goal", importance=3)
        self.assertIn(node_id, self.graph["nodes"])
        self.assertEqual(self.graph["nodes"][node_id]["type"], "goal")
        self.assertEqual(self.graph["nodes"][node_id]["tier"], "hot")

    def test_add_node_rejects_unknown_type(self):
        with self.assertRaises(cg.AxonError):
            cg.add_node(self.graph, "not_a_real_type", "x", "y")

    def test_add_edge_requires_existing_nodes(self):
        a = cg.add_node(self.graph, "goal", "A", "")
        with self.assertRaises(cg.AxonError):
            cg.add_edge(self.graph, a, "missing_node_id", "supports")

    def test_resolve_missing_id_raises_clean_axon_error_not_keyerror(self):
        # Regression: the original resolve_node() did a raw dict lookup and
        # crashed with an unhandled KeyError on a bad/typo'd id.
        with self.assertRaises(cg.AxonError):
            cg.resolve_node(self.graph, "doesnotexist")

    def test_confirm_only_applies_to_assumptions(self):
        fact_id = cg.add_node(self.graph, "fact", "F", "")
        with self.assertRaises(cg.AxonError):
            cg.confirm_node(self.graph, fact_id)

    def test_confirm_flips_assumption_flag(self):
        a = cg.add_node(self.graph, "assumption", "A", "")
        self.assertFalse(self.graph["nodes"][a]["confirmed"])
        cg.confirm_node(self.graph, a, True)
        self.assertTrue(self.graph["nodes"][a]["confirmed"])


class TestRoundTrip(AxonTreeTestCase):
    """Regression tests for the export/import format mismatch: the previous
    draft's default export produced a tree-drawing format that the import
    regex (written for an older flat format) could never match, so
    export -> import always silently produced zero nodes."""

    def _seed(self):
        cg.add_node(self.graph, "goal", "Ship AXON TREE", "root goal", importance=3)
        cg.add_node(self.graph, "assumption", "Py 3.11+", "unconfirmed env belief")
        cg.add_node(self.graph, "decision", "Use JSON", "simplicity")
        cg.add_node(self.graph, "task", "Write tests", "none existed")
        cg.add_node(self.graph, "blocker", "No CI", "manual only")
        cg.add_node(self.graph, "mistake", "Shipped a bug", "stray paren")

    def test_flat_round_trip_preserves_all_types(self):
        self._seed()
        text = cg.export_block(self.graph, max_words=10**9, style="flat")
        fresh = cg._empty_graph()
        added = cg.import_block(fresh, text)
        self.assertEqual(len(added), 6)
        types = sorted(n["type"] for n in fresh["nodes"].values())
        self.assertEqual(types, sorted(["goal", "assumption", "decision", "task", "blocker", "mistake"]))

    def test_tree_round_trip_preserves_all_types(self):
        self._seed()
        text = cg.export_block(self.graph, max_words=10**9, style="tree")
        fresh = cg._empty_graph()
        added = cg.import_block(fresh, text)
        self.assertEqual(len(added), 6)
        types = sorted(n["type"] for n in fresh["nodes"].values())
        self.assertEqual(types, sorted(["goal", "assumption", "decision", "task", "blocker", "mistake"]))

    def test_assumption_type_specifically_survives_round_trip(self):
        # Regression: TAG_BY_TYPE/TYPE_BY_TAG once omitted "assumption",
        # so a re-imported assumption node silently became type "fact".
        a = cg.add_node(self.graph, "assumption", "Some guess", "detail")
        text = cg.export_block(self.graph, max_words=10**9, style="flat")
        fresh = cg._empty_graph()
        cg.import_block(fresh, text)
        reimported = next(n for n in fresh["nodes"].values() if n["label"] == "Some guess")
        self.assertEqual(reimported["type"], "assumption")

    def test_linked_to_survives_round_trip(self):
        goal = cg.add_node(self.graph, "goal", "G", "root", importance=3)
        cg.add_node(self.graph, "decision", "D", "detail", linked_to=goal)
        text = cg.export_block(self.graph, max_words=10**9, style="flat")
        fresh = cg._empty_graph()
        cg.import_block(fresh, text)
        d = next(n for n in fresh["nodes"].values() if n["label"] == "D")
        self.assertIsNotNone(d["linked_to"])

    def test_import_ignores_unrecognized_lines(self):
        added = cg.import_block(self.graph, "some random paragraph\nnot a tree line at all")
        self.assertEqual(added, [])


class TestBudgetEnforcement(AxonTreeTestCase):
    """Regression tests for the silently-ignored --max-words flag."""

    def test_max_words_is_actually_enforced(self):
        for i in range(10):
            cg.add_node(self.graph, "fact", f"Fact {i}", "some detail " * 5)
        full = cg.export_block(self.graph, max_words=10**9)
        limited = cg.export_block(self.graph, max_words=5)
        self.assertGreater(len(full.split()), len(limited.split()))

    def test_importance_3_never_cut_even_under_tiny_budget(self):
        cg.add_node(self.graph, "goal", "Critical goal", "must survive", importance=3)
        for i in range(10):
            cg.add_node(self.graph, "fact", f"Fact {i}", "filler detail " * 5, importance=1)
        text = cg.export_block(self.graph, max_words=1)
        self.assertIn("Critical goal", text)

    def test_fit_actually_shrinks_a_hot_heavy_graph(self):
        # Regression: fit_to_budget() never called compress(), so it could
        # only prune nodes already in the cold tier — on a graph that was
        # still mostly hot/warm (the common case) it could not shrink
        # anything at all.
        cg.add_node(self.graph, "goal", "Root", "root goal", importance=3)
        for i in range(25):
            cg.add_node(self.graph, "fact", f"Old fact {i}", "resolved detail " * 4, importance=1)
        before = cg.compute_stats(self.graph)["export_word_count"]
        cg.fit_to_budget(self.graph, max_words=60)
        after_stats = cg.compute_stats(self.graph)
        self.assertGreater(after_stats["by_tier"]["archived"], 0)
        self.assertLess(after_stats["export_word_count"], before)


class TestTiering(AxonTreeTestCase):
    def test_compress_demotes_lowest_importance_first(self):
        low = cg.add_node(self.graph, "fact", "Low", "x", importance=1)
        high = cg.add_node(self.graph, "fact", "High", "x", importance=3)
        for i in range(5):
            cg.add_node(self.graph, "fact", f"Filler {i}", "x", importance=2)
        cg.compress(self.graph, hot_limit=3, warm_limit=8)
        self.assertEqual(self.graph["nodes"][low]["tier"], "warm")
        self.assertEqual(self.graph["nodes"][high]["tier"], "hot")

    def test_prune_never_archives_importance_3(self):
        n = cg.add_node(self.graph, "fact", "Critical", "x", importance=3)
        self.graph["nodes"][n]["tier"] = "cold"
        cg.prune(self.graph, cold_max_keep=0)
        self.assertEqual(self.graph["nodes"][n]["tier"], "cold")


class TestStorage(AxonTreeTestCase):
    def test_load_missing_file_returns_empty_graph(self):
        g = cg.load_graph(self.store)
        self.assertEqual(g["nodes"], {})

    def test_save_then_load_round_trips(self):
        cg.add_node(self.graph, "goal", "G", "x")
        cg.save_graph(self.store, self.graph)
        reloaded = cg.load_graph(self.store)
        self.assertEqual(len(reloaded["nodes"]), 1)

    def test_save_creates_backup_on_second_write(self):
        cg.add_node(self.graph, "goal", "G", "x")
        cg.save_graph(self.store, self.graph)
        cg.add_node(self.graph, "goal", "G2", "y")
        cg.save_graph(self.store, self.graph)
        backup = self.store.with_suffix(".json.bak")
        self.assertTrue(backup.exists())

    def test_corrupted_store_recovers_from_backup(self):
        cg.add_node(self.graph, "goal", "G", "x")
        cg.save_graph(self.store, self.graph)
        cg.add_node(self.graph, "goal", "G2", "y")
        cg.save_graph(self.store, self.graph)  # now .bak has the 1-node version
        self.store.write_text("{ not valid json")
        recovered = cg.load_graph(self.store)  # should fall back to .bak, not raise
        self.assertEqual(len(recovered["nodes"]), 1)

    def test_corrupted_store_with_no_backup_raises_axon_error(self):
        self.store.write_text("{ not valid json")
        with self.assertRaises(cg.AxonError):
            cg.load_graph(self.store)


class TestValidate(AxonTreeTestCase):
    def test_clean_graph_has_no_problems(self):
        cg.add_node(self.graph, "goal", "G", "x")
        self.assertEqual(cg.validate_graph(self.graph), [])

    def test_dangling_linked_to_is_flagged(self):
        n = cg.add_node(self.graph, "fact", "F", "x")
        self.graph["nodes"][n]["linked_to"] = "ghost_id"
        problems = cg.validate_graph(self.graph)
        self.assertTrue(any("ghost_id" in p for p in problems))

    def test_duplicate_type_and_label_is_flagged(self):
        cg.add_node(self.graph, "fact", "Same label", "first version")
        cg.add_node(self.graph, "fact", "Same label", "second version")
        problems = cg.validate_graph(self.graph)
        self.assertTrue(any("duplicate" in p for p in problems))

    def test_archived_duplicates_are_not_flagged(self):
        a = cg.add_node(self.graph, "fact", "Same label", "first")
        self.graph["nodes"][a]["tier"] = "archived"
        cg.add_node(self.graph, "fact", "Same label", "second")
        self.assertEqual(cg.validate_graph(self.graph), [])


class TestCompactMode(AxonTreeTestCase):
    """Regression + coverage for the extra --compact compression pass:
    shorter tags, arrow-style links, a trimmed banner — while still
    round-tripping through import_block() exactly like the default style."""

    def test_compact_is_shorter_than_default(self):
        for i in range(6):
            cg.add_node(self.graph, "fact", f"Fact {i}", "some detail here")
        full = cg.export_block(self.graph, max_words=10**9, compact=False)
        compact = cg.export_block(self.graph, max_words=10**9, compact=True)
        self.assertLess(len(compact.split()), len(full.split()))

    def test_compact_flat_round_trip_preserves_type_and_link(self):
        goal = cg.add_node(self.graph, "goal", "G", "root", importance=3)
        cg.add_node(self.graph, "decision", "D", "detail", linked_to=goal)
        text = cg.export_block(self.graph, max_words=10**9, style="flat", compact=True)
        fresh = cg._empty_graph()
        cg.import_block(fresh, text)
        d = next(n for n in fresh["nodes"].values() if n["label"] == "D")
        self.assertEqual(d["type"], "decision")
        self.assertIsNotNone(d["linked_to"])

    def test_compact_tree_round_trip_preserves_type(self):
        cg.add_node(self.graph, "assumption", "A guess", "detail")
        text = cg.export_block(self.graph, max_words=10**9, style="tree", compact=True)
        fresh = cg._empty_graph()
        cg.import_block(fresh, text)
        self.assertEqual(len(fresh["nodes"]), 1)
        self.assertEqual(next(iter(fresh["nodes"].values()))["type"], "assumption")

    def test_confirmed_assumption_survives_text_round_trip(self):
        a = cg.add_node(self.graph, "assumption", "A", "detail")
        cg.confirm_node(self.graph, a, True)
        text = cg.export_block(self.graph, max_words=10**9)
        fresh = cg._empty_graph()
        cg.import_block(fresh, text)
        reimported = next(iter(fresh["nodes"].values()))
        self.assertTrue(reimported["confirmed"])

    def test_unconfirmed_assumption_stays_unconfirmed_after_round_trip(self):
        cg.add_node(self.graph, "assumption", "A", "detail")
        text = cg.export_block(self.graph, max_words=10**9)
        fresh = cg._empty_graph()
        cg.import_block(fresh, text)
        reimported = next(iter(fresh["nodes"].values()))
        self.assertFalse(reimported["confirmed"])

    def test_compress_cold_trim_is_configurable(self):
        n = cg.add_node(self.graph, "fact", "F", "one two three four five six seven eight", importance=1)
        for i in range(10):
            cg.add_node(self.graph, "fact", f"Filler {i}", "x", importance=2)
        cg.compress(self.graph, hot_limit=1, warm_limit=1, cold_trim_words=3)
        self.assertLessEqual(len(self.graph["nodes"][n]["summary"].split()), 4)  # 3 words + "…"


if __name__ == "__main__":
    unittest.main()
