"""Ranking maths on synthetic picks."""

import unittest

from harness_bench.ranking import agreement, bradley_terry, rank, rating


class BradleyTerryTests(unittest.TestCase):
    def test_equal_records_give_equal_strengths(self):
        strengths = bradley_terry([("a", "b", 1), ("b", "a", 1), ("a", "c", 0.5), ("b", "c", 0.5)], ["a", "b", "c"])
        self.assertAlmostEqual(strengths["a"], strengths["b"], places=6)
        self.assertAlmostEqual(rating(1.0), 1500)

    def test_recovers_a_known_order(self):
        # a beats b 8 of 10, b beats c 8 of 10, a beats c 9 of 10
        picks = ([("a", "b", 1)] * 8 + [("a", "b", 0)] * 2 + [("b", "c", 1)] * 8 + [("b", "c", 0)] * 2
                 + [("a", "c", 1)] * 9 + [("a", "c", 0)] * 1)
        table = rank(picks, ["c", "a", "b"], resamples=200)
        self.assertEqual([row["item"] for row in table], ["a", "b", "c"])
        self.assertTrue(all(row["low"] <= row["rating"] <= row["high"] for row in table))
        self.assertGreater(table[0]["low"], table[2]["high"])
        self.assertAlmostEqual(table[0]["win_share"], 17 / 20)

    def test_a_clean_sweep_stays_finite(self):
        table = rank([("a", "b", 1)] * 5, ["a", "b"], resamples=50)
        self.assertTrue(all(abs(row["rating"]) < 5000 for row in table))
        self.assertEqual(table[0]["item"], "a")

    def test_no_picks_gives_average_ratings_without_intervals(self):
        table = rank([], ["a", "b"])
        self.assertEqual([round(row["rating"]) for row in table], [1500, 1500])
        self.assertIsNone(table[0]["low"])

    def test_ties_count_half(self):
        strengths = bradley_terry([("a", "b", 0.5)] * 6, ["a", "b"])
        self.assertAlmostEqual(strengths["a"], strengths["b"], places=6)


class AgreementTests(unittest.TestCase):
    def test_identical_judges(self):
        picks = {"p1": "left", "p2": "right", "p3": "tie"}
        self.assertEqual(agreement(picks, picks), {"pairs": 3, "agreement": 1.0, "kappa": 1.0})

    def test_chance_level_is_zero(self):
        first = {"p1": "left", "p2": "left", "p3": "right", "p4": "right"}
        second = {"p1": "left", "p2": "right", "p3": "left", "p4": "right"}
        result = agreement(first, second)
        self.assertEqual(result["agreement"], 0.5)
        self.assertAlmostEqual(result["kappa"], 0.0)

    def test_kappa_is_undefined_when_both_judges_never_vary(self):
        constant = {"p1": "left", "p2": "left"}
        self.assertEqual(agreement(constant, constant), {"pairs": 2, "agreement": 1.0, "kappa": None})

    def test_only_shared_pairs_count(self):
        result = agreement({"p1": "left", "p2": "right"}, {"p2": "right", "p9": "tie"})
        self.assertEqual(result["pairs"], 1)
        self.assertEqual(agreement({"p1": "left"}, {"p2": "left"})["pairs"], 0)


if __name__ == "__main__":
    unittest.main()
