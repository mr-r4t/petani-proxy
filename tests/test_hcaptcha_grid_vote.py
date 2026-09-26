"""Regression tests for the hCaptcha numbered-grid solver.

Background — the reported "hunt stops at the image" bug:
    On a multi-select challenge ("click on things that make their own light")
    a SINGLE vision model was unreliable in BOTH directions:

      * the fast model under-selected  -> [0]     (missed a real lamp)
      * reasoning models over-selected -> [0,1,6] / [0,1,8]

    hCaptcha rejects either answer, reloads the challenge, and the solve loop
    repeats — which the user saw as "stuck on the image".

Fix: a per-cell `N: yes`/`N: no` table prompt (grounds every tile) plus
multi-model consensus in KeyPool.ask_vote (cancels both error directions).

These tests are network-free: ask_vote is exercised with a stubbed
`_call_model`, so they pin the *voting logic* and the *parser*, not the models.
"""
import os
import sys
import unittest

_SOLVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "captcha-solver")
if _SOLVER not in sys.path:
    sys.path.insert(0, _SOLVER)

from hcaptcha.image_solve import _parse_cells          # noqa: E402
from common.mistral import KeyPool                      # noqa: E402


class TestParseCells(unittest.TestCase):
    """The parser must read the new per-cell table, and stay backward-compatible."""

    def test_per_cell_table(self):
        txt = ("0: yes\n1: yes\n2: no\n3: no\n4: no\n"
               "5: no\n6: no\n7: no\n8: no\nANSWER: 0,1")
        self.assertEqual(_parse_cells(txt, 9), [0, 1])

    def test_table_without_answer_line(self):
        self.assertEqual(_parse_cells("0: yes\n1: yes\n2: no", 9), [0, 1])

    def test_yes_in_prose_is_ignored(self):
        # A stray "yes" in prose must not leak in: only line-anchored `N: yes`.
        txt = "There is a yes here.\n0: yes\n1: yes\n2: no\nANSWER: 0,1"
        self.assertEqual(_parse_cells(txt, 9), [0, 1])

    def test_none_table(self):
        self.assertEqual(_parse_cells("0: no\n1: no\nANSWER: none", 9), [])

    def test_legacy_freeform_still_works(self):
        self.assertEqual(_parse_cells("blah\nanswer: 0,1", 9), [0, 1])

    def test_reasoning_only_returns_empty(self):
        self.assertEqual(_parse_cells("I think cell 3 maybe?", 9), [])

    def test_empty(self):
        self.assertEqual(_parse_cells("", 9), [])


class TestConsensusVote(unittest.TestCase):
    """ask_vote must cancel both under- and over-selection via quorum."""

    def _pool(self):
        # KeyPool() hits the key file/gateway only to read metadata; the network
        # is never used because _call_model is replaced below.
        pool = KeyPool(os.path.join(_SOLVER, "common", "apikey.txt"))
        pool.models = ["fast", "mid", "strong"]
        return pool

    def test_quorum_drops_over_selected_cell(self):
        """fast under-selects [0], two models add the spurious 6 -> keep {0,1}."""
        pool = self._pool()
        replies = {
            "fast":   "0: yes\n1: no\n6: no\nANSWER: 0",
            "mid":    "0: yes\n1: yes\n6: yes\nANSWER: 0,1,6",
            "strong": "0: yes\n1: yes\n6: no\nANSWER: 0,1",
        }
        pool._call_model = lambda img, p, m, mk, t, mt: replies[m]
        out = pool.ask_vote("x", "p", lambda t: _parse_cells(t, 9),
                            models=list(replies), quorum=2)
        self.assertEqual(out["cells"], [0, 1])

    def test_fallback_when_no_quorum(self):
        """All models disagree -> fall back to the strongest non-empty pick."""
        pool = self._pool()
        replies = {
            "fast":   "0: yes\nANSWER: 0",
            "mid":    "1: yes\nANSWER: 1",
            "strong": "2: yes\nANSWER: 2",
        }
        pool._call_model = lambda img, p, m, mk, t, mt: replies[m]
        out = pool.ask_vote("x", "p", lambda t: _parse_cells(t, 9),
                            models=list(replies), quorum=2)
        self.assertEqual(out["cells"], [2])          # strongest model wins

    def test_all_empty_returns_empty(self):
        pool = self._pool()
        pool._call_model = lambda img, p, m, mk, t, mt: ""
        out = pool.ask_vote("x", "p", lambda t: _parse_cells(t, 9),
                            models=["a", "b"], quorum=2)
        self.assertEqual(out["cells"], [])


if __name__ == "__main__":
    unittest.main()
