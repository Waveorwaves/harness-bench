"""Turning side-by-side picks into a ranking, and measuring how far two judges agree."""

import math
import random

ANCHOR_GAMES = 1.0  # each item also "plays" this many games against an average opponent, winning half


def bradley_terry(comparisons, items, rounds=200, start=None):
    """Strengths under the Bradley-Terry model, scaled so their geometric mean is 1.

    comparisons: (first, second, score) with score 1 if first won, 0 if second won, 0.5 for a tie.
    The anchor games keep the estimate finite for an item that won or lost everything.
    """
    wins = dict.fromkeys(items, ANCHOR_GAMES / 2)
    games = {}
    for first, second, score in comparisons:
        wins[first] += score
        wins[second] += 1 - score
        for one, other in ((first, second), (second, first)):
            games.setdefault(one, {}).setdefault(other, 0)
            games[one][other] += 1
    strength = dict(start) if start else dict.fromkeys(items, 1.0)
    for _ in range(rounds):
        updated = {}
        for item in items:
            exposure = ANCHOR_GAMES / (strength[item] + 1.0)
            exposure += sum(count / (strength[item] + strength[other]) for other, count in games.get(item, {}).items())
            updated[item] = wins[item] / exposure
        mean = math.exp(sum(math.log(value) for value in updated.values()) / len(updated))
        strength = {item: value / mean for item, value in updated.items()}
    return strength


def rating(strength):
    """An Elo-style number: 1500 is average and 400 points is a tenfold gap in odds."""
    return 1500 + 400 * math.log10(strength)


def rank(comparisons, items, resamples=1000, seed=0):
    """Ratings with 95% bootstrap intervals (picks resampled with replacement), best first."""
    items = list(items)
    point = bradley_terry(comparisons, items)
    rng = random.Random(seed)
    draws = {item: [] for item in items}
    for _ in range(resamples if comparisons else 0):
        sample = rng.choices(comparisons, k=len(comparisons))
        # Starting from the overall fit, a resample settles in far fewer rounds.
        for item, value in bradley_terry(sample, items, rounds=120, start=point).items():
            draws[item].append(rating(value))
    table = []
    for item in items:
        played = [(score if first == item else 1 - score) for first, second, score in comparisons if item in (first, second)]
        ordered = sorted(draws[item])
        table.append({
            "item": item, "rating": rating(point[item]), "games": len(played),
            "win_share": sum(played) / len(played) if played else None,
            "low": ordered[int(0.025 * len(ordered))] if ordered else None,
            "high": ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))] if ordered else None,
        })
    return sorted(table, key=lambda row: -row["rating"])


def agreement(first, second):
    """Raw agreement and Cohen's kappa over the pairs both judges answered.

    first, second: {pair id: "left" | "right" | "tie"}.
    Kappa corrects for the agreement two judges would reach by chance given how often each
    uses each answer: 0 is chance level, 1 is perfect, None means it cannot be computed.
    """
    shared = sorted(set(first) & set(second))
    if not shared:
        return {"pairs": 0, "agreement": None, "kappa": None}
    observed = sum(first[pair] == second[pair] for pair in shared) / len(shared)
    expected = sum((sum(first[pair] == answer for pair in shared) / len(shared))
                   * (sum(second[pair] == answer for pair in shared) / len(shared))
                   for answer in ("left", "right", "tie"))
    # If both judges gave one and the same answer every time, chance agreement is total and kappa is undefined.
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    return {"pairs": len(shared), "agreement": observed, "kappa": kappa}
