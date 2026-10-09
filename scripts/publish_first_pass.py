"""Build the public write-up of the first pass in docs/first-pass/ from the recorded runs.

    python3 scripts/publish_first_pass.py

Every number in the write-up is computed here from runs/<plan>/results.jsonl, the plan and the judge's picks.
The only figures typed in are the subscription-limit readings under ALLOWANCE, which were read from the
providers' meters during the runs and noted at the time.

Writes README.md (to read on GitHub), index.html (the same report as a page), charts, every ship page with a
thumbnail, the interactive results page and the data. Raw transcripts are not copied: they stay in runs/.
"""

import collections
import html
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness_bench import core  # noqa: E402
from harness_bench.ranking import rank  # noqa: E402

PLAN = json.loads((ROOT / "runs/pilot-v1-plan.json").read_text())
BASE = ROOT / "runs" / PLAN["plan_id"][:16]
OUT = ROOT / "docs" / "first-pass"
CONFIG = PLAN["configuration"]
REPO = "https://github.com/Waveorwaves/harness-bench"
HERE = f"{REPO}/tree/main/docs/first-pass"     # folders are linked on GitHub: a static site has no folder listings

NAMES = {"codex": "Codex CLI", "pi": "Pi", "omp": "oh-my-pi", "opencode": "OpenCode", "hermes": "Hermes Agent",
         "devin": "Devin", "droid": "Droid", "codex-app": "Codex app", "capy": "Capy", "deepseek-harness": "DeepSeek Harness"}
HOW = {"codex-app": "by hand, on the Mac", "capy": "by hand, on the Mac"}
# What each harness was started with, beyond the model and effort. Taken from harness_bench/adapters.py.
SETTINGS = {
    "codex": "`codex exec --json --ephemeral --dangerously-bypass-approvals-and-sandbox`",
    "pi": "`pi -p --mode json --no-session`",
    "omp": "`omp -p --mode json --no-session --auto-approve`",
    "opencode": "`opencode run --format json --auto`",
    "hermes": "`hermes -z`",
    "devin": "`devin -p --permission-mode dangerous --respect-workspace-trust false`",
    "droid": "`droid exec -o json --skip-permissions-unsafe`",
    "deepseek-harness": "`dsh --profile headless --json` with `DSH_PERMISSION_MODE=danger-full-access`; gpt-6.1-sol declared in its settings",
    "codex-app": "the app as installed, with the user's own configuration; one new chat per task",
    "capy": "the app as installed; one new chat per task",
}
ROUTE = {"devin": "Devin plan", "droid": "Factory plan"}
MODELS = collections.OrderedDict([
    ("gpt-6-1-sol", "gpt-6.1-sol, medium effort"),
    ("deepseek-flash-high", "DeepSeek's API, high effort"),
    ("deepseek-v4-1-flash-plan", "DeepSeek V4.1 Flash as hosted by the harness's plan, high effort"),
    ("deepseek-flash", "DeepSeek's API, \"medium\" asked for (superseded)"),
])
SHORT = {"gpt-6-1-sol": "gpt-6.1-sol", "deepseek-flash-high": "DeepSeek API, high", "deepseek-v4-1-flash-plan": "DeepSeek on its plan",
         "deepseek-flash": "DeepSeek API, earlier run"}
SHIP = "pirate-ship-3d"
BRIEF = {"md-preview": "md", "kanban-undo": "kanban", "expenses-csv": "expenses", "checkout-refactor": "checkout", "bookmarks-tags": "bookmarks",
         "todo-app": "todo", "tabs-keyboard": "tabs", "log-report": "log", SHIP: "ship"}       # column heads for the per-task tables
WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
TASKS = collections.OrderedDict([
    ("md-preview", ("build from a spec", "Write a Markdown-subset renderer and a preview page to an exact specification")),
    ("kanban-undo", ("bug fix", "Fix two reported undo/redo faults in a small kanban board")),
    ("expenses-csv", ("feature", "Add CSV export and import to an expense tracker")),
    ("checkout-refactor", ("refactor", "Split one long pricing function into four modules without changing any result")),
    ("bookmarks-tags", ("feature across modules", "Add tags through validation, storage with a migration, search, import/export and view")),
    ("todo-app", ("interactive page", "Build a to-do list page, graded by really using it in a headless browser")),
    ("tabs-keyboard", ("accessibility fix", "Make a tabs widget work with the keyboard and screen readers, including a nested widget")),
    ("log-report", ("Python command-line feature", "Add bad-line handling, a time window, percentiles and JSON output to a log summariser")),
    (SHIP, ("open-ended 3D page", "One `index.html`: a real-time WebGL pirate ship on a moving ocean at sunset")),
])
# Readings of the providers' own limit meters, taken before and after the runs named. Whole points only.
ALLOWANCE = [
    ("ChatGPT/Codex subscription", "Codex app, nine tasks", "13 points of the 5-hour limit", "read after each task"),
    ("ChatGPT/Codex subscription", "Capy, nine tasks", "20 points of the 5-hour limit; 3 of the weekly limit",
     "read after each task; one more point went on an attempt that stalled and was run again"),
    ("ChatGPT/Codex subscription", "DeepSeek Harness, nine tasks", "12 points of the 5-hour limit; 2 of the weekly limit",
     "0% before, 12% after, in a fresh window"),
    ("Devin plan", "Devin, nine gpt-6.1-sol tasks and one attempt cut off at 15 minutes", "about 11 points of the daily limit; 5 of the weekly limit",
     "first reading came four minutes after the first run started"),
    ("Factory plan", "Droid, nine gpt-6.1-sol tasks, one attempt cut off at 15 minutes and nine plan-hosted DeepSeek tasks",
     "about 3 points of the weekly limit", "one reading, after all of them"),
]

# One palette for the page and the charts, each in a light and a dark form. `a` and `b` are the two series
# colours (also won and lost), `n` the neutral between them (tied). Chosen to stay apart for colour-blind readers.
PALETTES = {
    "paper": {
        "light": dict(page="#f8f7f3", surface="#ffffff", ink="#1c1c1a", muted="#5c5b56", line="#e3e1da", a="#2a78d6", b="#e58a1f", n="#c4c3bb", accent="#2a78d6"),
        "dark": dict(page="#10100f", surface="#1a1a19", ink="#f4f3ee", muted="#b3b2aa", line="#343431", a="#6aa6f0", b="#f0a44a", n="#55554f", accent="#7db2f5")},
    "indigo": {
        "light": dict(page="#f5f6f8", surface="#ffffff", ink="#1c1e26", muted="#6b7080", line="#e3e5ea", a="#4f6df5", b="#f2a23a", n="#c5c9d3", accent="#3f5be0"),
        "dark": dict(page="#101218", surface="#191c24", ink="#eef0f5", muted="#a3a8b8", line="#2c303a", a="#8195ff", b="#f5b75c", n="#4a4f5e", accent="#94a5ff")},
    "ink": {
        "light": dict(page="#ffffff", surface="#fafafa", ink="#111111", muted="#666666", line="#e4e4e4", a="#1a1a1a", b="#e4572e", n="#c9c9c9", accent="#c4401c"),
        "dark": dict(page="#111111", surface="#1a1a1a", ink="#f2f2f2", muted="#b0b0b0", line="#333333", a="#ededed", b="#ff7a50", n="#5a5a5a", accent="#ff8a65")},
    # Snow, ink and plum blossom.
    "plum": {
        "light": dict(page="#ffffff", surface="#fafafa", ink="#111111", muted="#666666", line="#e4e4e4", a="#1a1a1a", b="#d83f6a", n="#c9c9c9", accent="#c02a57"),
        "dark": dict(page="#111111", surface="#1a1a1a", ink="#f2f2f2", muted="#b0b0b0", line="#333333", a="#ededed", b="#ec6a8f", n="#4d4d4d", accent="#f58fae")},
    "harbour": {
        "light": dict(page="#f7f5f0", surface="#fffdf8", ink="#14213d", muted="#5b6475", line="#e4dfd3", a="#1d4e89", b="#f08a4b", n="#cbc6ba", accent="#1d4e89"),
        "dark": dict(page="#0e1420", surface="#161d2c", ink="#eef1f6", muted="#a7b0c2", line="#2a3347", a="#6ea8e6", b="#f6a56f", n="#47506a", accent="#8dbcf0")},
    "evergreen": {
        "light": dict(page="#f6f7f4", surface="#ffffff", ink="#17201b", muted="#5d675f", line="#e1e5dd", a="#1f7a5c", b="#d9a521", n="#c7ccc4", accent="#1a6b50"),
        "dark": dict(page="#0f1412", surface="#171d1a", ink="#eef3ef", muted="#a5b0a8", line="#2a332e", a="#4fbf97", b="#e9bd4b", n="#4b554f", accent="#6fd0ad")},
}
PALETTE = "plum"
# The page's typefaces. Each style names its web fonts (fetched from Google Fonts when the page is opened, with
# system faces to fall back on) and the few rules that differ. Charts are pictures and keep a system sans.
STYLES = {
    "editorial": dict(
        fonts="family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500",
        display='"Fraunces", "Iowan Old Style", Georgia, serif', body='"Source Serif 4", "Iowan Old Style", Georgia, serif',
        ui='"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif', mono='"IBM Plex Mono", ui-monospace, Menlo, monospace',
        css="body { font-size: 17.5px; line-height: 1.62; } h1 { font-weight: 600; letter-spacing: -0.018em; } h2, h3 { font-weight: 600; letter-spacing: -0.01em; } "
            ".stats strong { font-family: var(--f-display); font-weight: 500; }"),
    "song": dict(
        fonts="family=Noto+Serif+TC:wght@500;700&family=Noto+Serif:wght@400;600&family=Noto+Sans:wght@400;500;600&family=Noto+Sans+Mono:wght@400;500",
        display='"Noto Serif TC", "Noto Serif", "Songti SC", Georgia, serif', body='"Noto Serif", "Songti SC", Georgia, serif',
        ui='"Noto Sans", "Helvetica Neue", Arial, sans-serif', mono='"Noto Sans Mono", ui-monospace, Menlo, monospace',
        css="body { font-size: 16.5px; line-height: 1.72; } h1 { font-weight: 700; letter-spacing: 0; } h2, h3 { font-weight: 700; } "
            ".stats strong { font-family: var(--f-display); font-weight: 500; }"),
    "lab": dict(
        fonts="family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500",
        display='"Space Grotesk", "Helvetica Neue", Arial, sans-serif', body='"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
        ui='"IBM Plex Mono", ui-monospace, Menlo, monospace', mono='"IBM Plex Mono", ui-monospace, Menlo, monospace',
        css="body { font-size: 16px; line-height: 1.62; } h1 { font-weight: 600; letter-spacing: -0.035em; } h2, h3 { font-weight: 600; letter-spacing: -0.02em; } "
            "td { font-family: var(--f-body); } td.n { font-family: var(--f-mono); font-size: 13px; } .stats strong { font-family: var(--f-mono); font-weight: 500; } "
            "th, nav a, .stats span, .eyebrow { font-size: 12px; } th { letter-spacing: .03em; font-weight: 500; } th, td { padding-right: 16px; }"),
}
STYLE = "lab"
BLUE = ORANGE = GREY = INK = MUTED = LINE = SURFACE = PAPER = ""
FONT = "font-family=\"Helvetica Neue, Helvetica, Arial, sans-serif\""


def use(theme):
    """Point the chart colours at the chosen palette's light or dark form."""
    c = PALETTES[PALETTE][theme]
    globals().update(BLUE=c["a"], ORANGE=c["b"], GREY=c["n"], INK=c["ink"], MUTED=c["muted"], LINE=c["line"], SURFACE=c["surface"], PAPER=c["page"])


use("light")


# --- data ------------------------------------------------------------------------------------------------

def load():
    records = [json.loads(line) for line in (BASE / "results.jsonl").read_text().splitlines() if line.strip()]
    cells = collections.defaultdict(dict)
    for record in records:
        _, task, harness, model, _, repetition = record["run_id"].split(":")
        if repetition == "1":
            cells[(model, harness)][task] = record
    return records, cells


def known_sum(values):
    values = [value for value in values if value is not None]
    return sum(values), len(values)


def row(model, harness, runs, intervals):
    done = list(runs.values())
    ship = runs.get(SHIP)
    listed, listed_known = known_sum(r.get("list_price_usd") for r in done)
    own, own_known = known_sum(r.get("cost_usd") for r in done)
    seconds = sum(r["elapsed_seconds"] for r in done)
    tokens = {name: known_sum(r.get(field) for r in done) for name, field in (
        ("input", "input_tokens"), ("cached", "cached_input_tokens"), ("written", "cache_write_tokens"), ("output", "output_tokens"),
        ("turns", "turns"), ("tools", "tool_calls"))}
    passed = sum(r["status"] == "passed" for r in done)
    return {
        "model": model, "harness": harness, "name": NAMES[harness], "runs": len(done), "passed": passed,
        "failed": sum(r["status"] == "failed" for r in done), "stopped": sum(r["status"] == "timed_out" for r in done),
        "interval": intervals.get((model, harness)), "seconds": seconds,
        "median_seconds": statistics.median(r["elapsed_seconds"] for r in done),
        "ship_seconds": ship["elapsed_seconds"] if ship else None, "ship_status": ship["status"] if ship else None,
        "rest_seconds": seconds - (ship["elapsed_seconds"] if ship else 0),
        "list_usd": listed, "list_known": listed_known, "own_usd": own, "own_known": own_known,
        "own_floor": any(r.get("cost_usd_is_floor") for r in done),
        "per_pass": listed / passed if passed and listed_known == len(done) else None,
        "tokens": {name: total for name, (total, _) in tokens.items()}, "tokens_known": {name: count for name, (_, count) in tokens.items()},
    }


def judged(model):
    """One judge's picks for a model's ships: tallies, ratings and who beat whom. None where nothing was judged."""
    folder = BASE / "judging"
    key_file, picks_file = folder / f"{SHIP}.{model}.key.json", folder / f"picks-wave.{SHIP}.{model}.json"
    if not (key_file.is_file() and picks_file.is_file()):
        return None
    key, document = json.loads(key_file.read_text()), json.loads(picks_file.read_text())
    assert key["pairs_id"] == document["pairs_id"], "picks are for another set of pairs"
    picks = {pick["pair"]: pick["winner"] for pick in document["picks"]}
    who = {name: attempt["configuration"][0] for name, attempt in key["attempts"].items()}
    tally, against, games = collections.defaultdict(lambda: [0, 0, 0]), {}, []
    for pair in key["pairs"]:
        left, right, winner = who[pair["left"]], who[pair["right"]], picks[pair["id"]]
        games.append((left, right, {"left": 1, "right": 0, "tie": 0.5}[winner]))
        for mine, other, side in ((left, right, "left"), (right, left, "right")):
            result = 0 if winner == side else 1 if winner == "tie" else 2
            tally[mine][result] += 1
            against[(mine, other)] = "WTL"[result]
    ratings = {entry["item"]: entry for entry in rank(games, sorted(set(who.values())))}
    order = sorted(tally, key=lambda h: (-(tally[h][0] + tally[h][1] / 2), -tally[h][0], NAMES[h]))
    return {"pairs": len(key["pairs"]), "ties": sum(1 for winner in picks.values() if winner == "tie"), "judge": document.get("judge"),
            "tally": {h: tuple(tally[h]) for h in order}, "order": order, "against": against,
            "rating": {h: (ratings[h]["rating"], ratings[h]["low"], ratings[h]["high"]) for h in order}}


def failed_checks(record):
    out = []
    for path in sorted((ROOT / record["evidence_ref"] / "evaluation").glob("*.json")):
        try:
            checks = json.loads(path.read_text()).get("checks") or []
        except (OSError, ValueError):
            continue
        out += [str(check.get("name")) for check in checks if isinstance(check, dict) and check.get("passed") is False]
    return out


# --- small formatters -------------------------------------------------------------------------------------

def mins(seconds):
    return f"{seconds / 60:.1f} min"


def usd(value, digits=2):
    return f"${value:.{digits}f}"


def cost_cell(r):
    if r["list_known"] == r["runs"]:
        return usd(r["list_usd"])
    if r["list_known"]:
        return f"at least {usd(r['list_usd'])} ({r['list_known']} of {r['runs']} priced)"
    if r["own_known"]:
        return f"{'at least ' if r['own_floor'] or r['own_known'] < r['runs'] else ''}{usd(r['own_usd'])} (own figure)"
    return "unknown"


def millions(value, known, runs):
    if not known:
        return "—"
    return f"{value / 1e6:.2f}M" + ("" if known == runs else f" ({known} of {runs})")


def count_cell(value, known, runs):
    return "—" if not known else f"{value:,}" + ("" if known == runs else f" ({known} of {runs})")


def ship_cell(r):
    if r["ship_seconds"] is None:
        return "none"
    return "stopped at 60 min" if r["ship_status"] == "timed_out" and r["ship_seconds"] > 3000 else \
        "stopped at 15 min" if r["ship_status"] == "timed_out" else mins(r["ship_seconds"])


def word(number):
    return WORDS[number] if 0 <= number < len(WORDS) else str(number)


def shared_ranks(order, tally):
    """1, 1, 3 for a three-way list whose first two are level, written 1=, 1=, 3."""
    labels = []
    for index, harness in enumerate(order):
        first = next(i for i, other in enumerate(order) if tally[other] == tally[harness])
        level = sum(1 for other in order if tally[other] == tally[harness]) > 1
        labels.append(f"{first + 1}{'=' if level else ''}")
    return labels


def percent_range(interval):
    return "unknown" if not interval else f"{interval[0]:.0%} to {interval[1]:.0%}"


# --- charts -----------------------------------------------------------------------------------------------

def svg(width, height, body, label):
    return (f"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {width} {height}\" width=\"{width}\" height=\"{height}\" role=\"img\" "
            f"aria-label=\"{html.escape(label)}\" {FONT}>{body}</svg>\n")


def on_card(chart, pad=26):
    """The same chart on a light card with room around it, for places where the page behind it is not ours to choose."""
    width, height = (int(value) for value in re.search(r'viewBox="0 0 (\d+) (\d+)"', chart).groups())
    head, inner = chart[:chart.index(">") + 1], chart[chart.index(">") + 1:chart.rindex("</svg>")]
    head = head.replace(f'viewBox="0 0 {width} {height}"', f'viewBox="0 0 {width + 2 * pad} {height + 2 * pad}"')
    head = head.replace(f'width="{width}" height="{height}"', f'width="{width + 2 * pad}" height="{height + 2 * pad}"')
    return (f'{head}<rect x="0.5" y="0.5" width="{width + 2 * pad - 1}" height="{height + 2 * pad - 1}" rx="12" fill="{SURFACE}" stroke="{LINE}"/>'
            f'<g transform="translate({pad} {pad})">{inner}</g></svg>\n')


def text(x, y, value, size=14, fill=None, anchor="start", weight="400"):
    fill = fill or INK
    return f"<text x=\"{x:.1f}\" y=\"{y:.1f}\" font-size=\"{size}\" fill=\"{fill}\" text-anchor=\"{anchor}\" font-weight=\"{weight}\">{html.escape(str(value))}</text>"


def legend(x, y, entries):
    out = []
    for colour, label in entries:
        out.append(f"<rect x=\"{x}\" y=\"{y - 11}\" width=\"14\" height=\"14\" rx=\"3\" fill=\"{colour}\"/>" + text(x + 20, y + 1, label, 13, MUTED))
        x += 34 + 7.2 * len(label)
    return "".join(out)


def bars(title, rows, segments, scale, unit_label, note=None):
    """Horizontal stacked bars. rows: (label, [value per segment], text after the bar). segments: (colour, label)."""
    left, right, top, step = 150, 190, 70, 36
    width, height = 860, top + step * len(rows) + (36 if note else 6)
    span = width - left - right
    out = [text(0, 22, title, 16, INK, weight="600"), legend(0, 48, segments)]
    for index, (label, values, after) in enumerate(rows):
        y = top + index * step
        out.append(text(left - 14, y + 18, label, 14, INK, "end"))
        x = left
        for (colour, _), value in zip(segments, values):
            length = max(span * value / scale, 0)
            if length > 1.5:        # a hairline of the card shows between segments
                out.append(f"<rect x=\"{x:.1f}\" y=\"{y + 5}\" width=\"{length - 1.5:.1f}\" height=\"18\" rx=\"4\" fill=\"{colour}\"/>")
            x += length
        out.append(text(x + 8, y + 18, after, 13, MUTED))
    if note:
        out.append(text(0, height - 8, note, 12, MUTED))
    return svg(width, height, "".join(out), f"{title} ({unit_label})")


def time_chart(title, rows):
    ordered = sorted(rows, key=lambda r: r["seconds"])
    data = [(r["name"], [r["rest_seconds"] / 60, (r["ship_seconds"] or 0) / 60],
             f"{r['seconds'] / 60:.0f} min" + (" · ship stopped at 60" if r["ship_status"] == "timed_out" else "")) for r in ordered]
    scale = max(r["seconds"] for r in rows) / 60 * 1.02
    return bars(title, data, [(BLUE, "eight smaller tasks"), (ORANGE, "3D pirate ship")], scale, "minutes")


def ship_chart(title, result):
    data = [(NAMES[h], list(result["tally"][h]), "{}-{}-{}".format(*result["tally"][h])) for h in result["order"]]
    scale = sum(next(iter(result["tally"].values()))) * 1.02
    return bars(title, data, [(BLUE, "won"), (GREY, "tied"), (ORANGE, "lost")], scale, "pairs",
                note="Each ship met every other ship once. One judge, blind, completeness first.")


def scatter(rows, width=860, height=520, title="gpt-6.1-sol: nine tasks, every harness passed all nine", never_lost=(), pad=0):
    left, right, top, bottom = 60 + pad, 24 + pad, 92 + pad, 58 + pad
    xs = [r["seconds"] / 60 for r in rows]
    ys = [r["list_usd"] if r["list_known"] == r["runs"] else r["own_usd"] for r in rows]
    x0, x1 = 15, 45
    y0, y1 = 0.5, 2.0
    px = lambda v: left + (width - left - right) * (v - x0) / (x1 - x0)
    py = lambda v: height - bottom - (height - top - bottom) * (v - y0) / (y1 - y0)
    out = [text(pad, 22 + pad, title, 16, INK, weight="600"),
           legend(pad, 47 + pad, [(BLUE, "ship never lost a pair in blind judging"), (ORANGE, "ship lost at least one pair")])]
    for tick in (15, 20, 25, 30, 35, 40, 45):
        out.append(f"<line x1=\"{px(tick):.1f}\" y1=\"{top}\" x2=\"{px(tick):.1f}\" y2=\"{height - bottom}\" stroke=\"{LINE}\"/>" + text(px(tick), height - bottom + 20, tick, 12, MUTED, "middle"))
    for tick in (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0):
        out.append(f"<line x1=\"{left}\" y1=\"{py(tick):.1f}\" x2=\"{width - right}\" y2=\"{py(tick):.1f}\" stroke=\"{LINE}\"/>" + text(left - 10, py(tick) + 4, f"${tick:.2f}", 12, MUTED, "end"))
    out.append(text((left + width - right) / 2, height - 14 - pad, "Minutes for the nine tasks", 13, MUTED, "middle"))
    out.append(text(left, top - 12, "Cost at list price", 12, MUTED))
    # Labels sit to the right unless that would collide with a neighbour; these offsets were set by eye for this data.
    nudge = {"codex": (4, -13), "capy": (-10, -10), "opencode": (10, 17), "deepseek-harness": (-10, 17), "devin": (10, -8), "hermes": (10, -8), "omp": (-10, 20)}
    for r, x, y in zip(rows, xs, ys):
        own = r["list_known"] != r["runs"]
        colour = BLUE if r["harness"] in never_lost else ORANGE
        fill = SURFACE if own else colour
        out.append(f"<circle cx=\"{px(x):.1f}\" cy=\"{py(y):.1f}\" r=\"7.5\" fill=\"{fill}\" stroke=\"{colour if own else SURFACE}\" stroke-width=\"2.5\"/>")
        dx, dy = nudge.get(r["harness"], (10, 5))
        label = r["name"] + (" (its own figure, at least)" if own else "")
        out.append(text(px(x) + dx, py(y) + dy, label, 13, INK, "end" if dx < 0 else "start"))
    return svg(width, height, "".join(out), title)


def card(rows, never_lost):
    """A 1600 by 900 picture for sharing: the headline and the scatter."""
    chart = scatter(rows, 900, 620, "Time and cost for the nine tasks", never_lost, pad=26)
    inner = chart[chart.index(">") + 1:chart.rindex("</svg>")]
    fast, slow = min(r["seconds"] for r in rows) / 60, max(r["seconds"] for r in rows) / 60
    token_rows = [r for r in rows if r["tokens_known"]["input"] == r["runs"]]
    total = lambda r: (r["tokens"]["input"] + r["tokens"]["cached"] + r["tokens"]["written"] + r["tokens"]["output"]) / 1e6
    low, high = min(map(total, token_rows)), max(map(total, token_rows))
    lines = [("Same model,", 50, "700"), ("ten coding harnesses,", 50, "700"), ("nine tasks.", 50, "700"), ("", 18, "400"),
             ("All ten passed all nine.", 34, "600"), ("", 10, "400"),
             (f"They took {fast:.0f} to {slow:.0f} minutes", 29, "400"),
             (f"and {low:.2f}M to {high:.2f}M tokens.", 29, "400"), ("", 24, "400"),
             ("One run each. gpt-6.1-sol at medium effort,", 21, "400"), ("October 2026. Limits and data in the report.", 21, "400")]
    y, out = 150, []
    for value, size, weight in lines:
        if value:
            out.append(text(70, y, value, size, INK if size > 24 else MUTED, weight=weight))
        y += size * 1.32
    out.append(text(70, 840, "github.com/Waveorwaves/harness-bench", 24, ORANGE, weight="600"))
    body = "".join(out) + f"<g transform=\"translate(650 150)\"><rect width=\"900\" height=\"620\" rx=\"14\" fill=\"{SURFACE}\" stroke=\"{LINE}\"/>{inner}</g>"
    return (f"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 1600 900\" width=\"1600\" height=\"900\" {FONT}>"
            f"<rect width=\"1600\" height=\"900\" fill=\"{PAPER}\"/>{body}</svg>\n")


# --- one document, two renderings -------------------------------------------------------------------------

class Notes:
    """Numbered notes for one table. `mark` gives the marker to put beside a figure; the same note is numbered once."""

    def __init__(self, key):
        self.key, self.items = key, []

    def mark(self, note):
        if note not in self.items:
            self.items.append(note)
        number = self.items.index(note) + 1
        return f"{{^{number}:note-{self.key}-{number}}}"


MARK = re.compile(r"\{\^(\d+):([a-z0-9-]+)\}")


class Doc:
    def __init__(self):
        self.blocks = []

    def add(self, kind, *values):
        self.blocks.append((kind, *values))
        return self

    def h(self, level, title):
        return self.add("h", level, title)

    def p(self, *paragraphs):
        for paragraph in paragraphs:
            self.add("p", paragraph)
        return self

    def ul(self, *items):
        return self.add("ul", items)

    def table(self, head, rows, right=()):
        return self.add("table", head, rows, right)

    def img(self, source, alt):
        return self.add("img", source, alt)

    def note(self, value):
        return self.add("note", value)

    def details(self, summary, doc):
        return self.add("details", summary, doc)

    def gallery(self, items):
        return self.add("gallery", items)

    def code(self, value):
        return self.add("code", value)


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def inline(value):
    """**bold**, `code` and [text](url), on text that is otherwise shown as written."""
    value = html.escape(str(value), quote=False)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = MARK.sub(r'<sup class="fn"><a href="#\2">\1</a></sup>', value)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', value)


def markdown(doc):
    out = []
    for kind, *values in doc.blocks:
        if kind == "h":
            out.append("#" * values[0] + " " + values[1])
        elif kind == "p":
            out.append(values[0])
        elif kind == "ul":
            out.append("\n".join(f"- {item}" for item in values[0]))
        elif kind == "note":
            out.append("> " + values[0])
        elif kind == "markdown-only":
            out.append(values[0])
        elif kind in ("tiles", "nav"):
            continue        # page furniture; the text beside it says the same
        elif kind == "notes":
            out.append("\n".join(f"{number}. {note}" for number, note in enumerate(values[1], 1)))
        elif kind == "img":
            out.append(f"![{values[1]}]({values[0].replace('.svg', '-card.svg')})")
        elif kind == "code":
            out.append("```sh\n" + values[0] + "\n```")
        elif kind == "table":
            head, rows, right = values
            cell = lambda value: str(value).replace("|", "\\|")
            out.append("\n".join(["| " + " | ".join(head) + " |", "|" + "|".join("---:" if i in right else "---" for i in range(len(head))) + "|"]
                                 + ["| " + " | ".join(cell(value) for value in line) + " |" for line in rows]))
        elif kind == "details":
            out.append(f"**{values[0]}**\n\n{markdown(values[1])}")
        elif kind == "gallery":
            cells = [f"[![{caption}]({thumb})]({link}) {caption}" for thumb, link, caption in values[0]]
            lines = [cells[i:i + 3] for i in range(0, len(cells), 3)]
            out.append("\n".join(["| | | |", "|---|---|---|"] + ["| " + " | ".join(line + [""] * (3 - len(line))) + " |" for line in lines]))
    raised = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")      # plain characters: some viewers show HTML tags as text
    return MARK.sub(lambda match: match.group(1).translate(raised), "\n\n".join(out))


def to_html(doc, level_shift=0):
    out = []
    for kind, *values in doc.blocks:
        if kind == "h":
            level = values[0] + level_shift
            out.append(f"<h{level} id=\"{slug(values[1])}\">{inline(values[1])}</h{level}>")
        elif kind == "p":
            out.append(f"<p>{inline(values[0])}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in values[0]) + "</ul>")
        elif kind == "note":
            out.append(f"<p class=\"note\">{inline(values[0])}</p>")
        elif kind == "img":
            dark = values[0].replace(".svg", "-dark.svg")
            out.append(f"<figure><picture><source srcset=\"{dark}\" media=\"(prefers-color-scheme: dark)\">"
                       f"<img src=\"{values[0]}\" alt=\"{html.escape(values[1])}\" loading=\"lazy\"></picture></figure>")
        elif kind == "notes":
            out.append("<ol class=\"notes\">" + "".join(f"<li id=\"note-{values[0]}-{number}\">{inline(note)}</li>" for number, note in enumerate(values[1], 1)) + "</ol>")
        elif kind == "tiles":
            out.append("<div class=\"stats\">" + "".join(f"<div><strong>{inline(figure)}</strong><span>{inline(label)}</span></div>" for figure, label in values[0]) + "</div>")
        elif kind == "nav":
            out.append("<nav>" + "".join(f"<a href=\"#{slug(title)}\">{inline(short)}</a>" for short, title in values[0]) + "</nav>")
        elif kind == "code":
            out.append(f"<pre><code>{html.escape(values[0])}</code></pre>")
        elif kind == "table":
            head, rows, right = values
            side = lambda i: " class=\"n\"" if i in right else ""
            out.append("<div class=\"scroll\"><table><thead><tr>" + "".join(f"<th{side(i)}>{inline(value)}</th>" for i, value in enumerate(head)) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td{side(i)}>{inline(value)}</td>" for i, value in enumerate(line)) + "</tr>" for line in rows) + "</tbody></table></div>")
        elif kind == "details":
            out.append(f"<details><summary>{inline(values[0])}</summary>{to_html(values[1], level_shift)}</details>")
        elif kind == "gallery":
            out.append("<div class=\"gallery\">" + "".join(
                f"<a href=\"{link}\"><img src=\"{thumb}\" alt=\"{html.escape(caption)}\" loading=\"lazy\"><span>{inline(caption)}</span></a>" for thumb, link, caption in values[0]) + "</div>")
    return "\n".join(out)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness Bench: first pass</title>
<meta name="description" content="Ten coding harnesses, the same models, nine tasks, one run each: pass rates, time, tokens, cost and blind judging of a 3D task, with limits.">
<meta property="og:title" content="Harness Bench: ten coding harnesses, the same model, nine tasks">
<meta property="og:description" content="Pass rates, time, tokens, cost and blind judging of a 3D task. One run each, with the limits listed.">
<meta property="og:image" content="img/card.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?/*FONTS*/&display=swap">
<style>
/*VARS*/
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--page); color: var(--ink); font-family: var(--f-body); font-size: 17px; line-height: 1.6; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
main { max-width: 980px; margin: 0 auto; padding: 56px 24px 110px; }
h1, h2, h3 { font-family: var(--f-display); }
h1 { font-size: clamp(34px, 5.4vw, 54px); line-height: 1.06; margin: 14px 0 16px; max-width: 18ch; text-wrap: balance; }
h1 + p { font-family: var(--f-ui); color: var(--ink-2); font-size: 14px; margin: 0; max-width: none; }
h2 { font-size: 30px; line-height: 1.15; margin: 84px 0 14px; scroll-margin-top: 60px; }
h2::before { content: ""; display: block; width: 28px; height: 3px; background: var(--b); margin-bottom: 18px; }
h3 { font-size: 21px; line-height: 1.25; margin: 44px 0 8px; scroll-margin-top: 60px; }
h4 { font-family: var(--f-ui); font-size: 12px; font-weight: 600; margin: 30px 0 4px; color: var(--ink-2); text-transform: uppercase; letter-spacing: .09em; }
p, li { max-width: 66ch; }
ul { padding-left: 20px; }
li { margin: 7px 0; }
li::marker { color: var(--b); }
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 3px; }
strong { font-weight: 600; }
code { font-family: var(--f-mono); font-size: 0.82em; background: color-mix(in srgb, var(--ink) 6%, transparent); border-radius: 3px; padding: 1px 4px; }
pre { border-top: 1px solid var(--ink); border-bottom: 1px solid var(--line); padding: 14px 0; overflow-x: auto; font-size: 13px; line-height: 1.6; }
pre code { background: none; padding: 0; font-size: 13px; }
.eyebrow { font-family: var(--f-ui); color: var(--accent); font-size: 12.5px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; margin: 0; }
.note { border-left: 2px solid var(--b); padding: 1px 0 1px 18px; margin: 26px 0 0; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); margin: 34px 0 30px; border-top: 1.5px solid var(--ink); border-bottom: 1px solid var(--line); }
.stats div { padding: 18px 18px 16px; }
.stats div:first-child { padding-left: 0; }
.stats div + div { border-left: 1px solid var(--line); }
.stats strong { display: block; font-size: 40px; line-height: 1; font-weight: 600; letter-spacing: -0.02em; font-variant-numeric: tabular-nums lining-nums; }
.stats span { display: block; font-family: var(--f-ui); color: var(--ink-2); font-size: 13px; line-height: 1.4; margin-top: 10px; }
nav { position: sticky; top: 0; z-index: 2; display: flex; gap: 22px; overflow-x: auto; margin: 34px -24px 0; padding: 12px 24px; background: color-mix(in srgb, var(--page) 90%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
nav a { font-family: var(--f-ui); white-space: nowrap; font-size: 13.5px; color: var(--ink-2); text-decoration: none; }
nav a:hover { color: var(--accent); }
.scroll { overflow-x: auto; margin: 18px 0 26px; }
table { border-collapse: collapse; width: 100%; font-family: var(--f-ui); font-size: 14px; line-height: 1.45; }
th, td { text-align: left; padding: 9px 20px 9px 0; vertical-align: top; overflow-wrap: anywhere; }
th { font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-2); white-space: nowrap; border-bottom: 1.5px solid var(--ink); }
td { border-bottom: 1px solid var(--line); }
td:first-child { font-weight: 600; white-space: nowrap; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums lining-nums; white-space: nowrap; }
th:last-child, td:last-child { padding-right: 0; }
figure { margin: 26px 0; max-width: 860px; }
figure img { display: block; width: 100%; height: auto; }
sup.fn { font-size: 0.72em; line-height: 0; margin-left: 2px; }
sup.fn a { font-family: var(--f-mono); text-decoration: none; padding: 0 1px; }
ol.notes { font-family: var(--f-body); font-size: 13.5px; line-height: 1.5; color: var(--ink-2); margin: -10px 0 30px; padding-left: 20px; }
ol.notes li { max-width: 78ch; margin: 5px 0; scroll-margin-top: 70px; }
ol.notes li::marker { font-family: var(--f-mono); color: var(--accent); }
ol.notes li:target { color: var(--ink); }
details { margin: 18px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
summary { cursor: pointer; padding: 12px 0; font-family: var(--f-ui); font-size: 14px; font-weight: 600; color: var(--accent); }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 22px 16px; margin: 18px 0 26px; }
.gallery a { display: block; text-decoration: none; color: var(--ink); font-family: var(--f-ui); font-size: 13px; line-height: 1.4; }
.gallery img { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; background: #000; border-radius: 3px; transition: opacity .15s ease; }
.gallery a:hover img { opacity: .86; }
.gallery span { display: block; padding-top: 8px; }
footer { font-family: var(--f-ui); color: var(--ink-2); font-size: 13px; margin-top: 90px; border-top: 1.5px solid var(--ink); padding-top: 16px; }
@media (max-width: 680px) {
  main { padding: 32px 18px 80px; } h2 { margin-top: 60px; font-size: 26px; } nav { margin: 28px -18px 0; padding: 12px 18px; }
  .stats { grid-template-columns: 1fr 1fr; } .stats div { padding: 16px 14px 14px 0; } .stats div + div { border-left: 0; }
  .stats div:nth-child(even) { border-left: 1px solid var(--line); padding-left: 16px; } .stats div:nth-child(n+3) { border-top: 1px solid var(--line); }
  td:first-child { white-space: normal; } .stats strong { font-size: 28px; white-space: nowrap; }
}
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } .gallery img { transition: none; } }
/*STYLE*/
</style>
</head>
<body>
<main>
<p class="eyebrow">Harness Bench · first pass</p>
/*BODY*/
<footer>Built from the recorded runs by <code>scripts/publish_first_pass.py</code>. <a href="/*REPO*/">Source, tasks and checks</a>.</footer>
</main>
</body>
</html>
"""


def page(body, back=""):
    """The page around a rendered document, with the palette's colours in both forms."""
    names = dict(page="page", surface="surface", ink="ink", muted="ink-2", line="line", accent="accent", a="a", b="b", n="n")
    block = lambda theme: " ".join(f"--{names[key]}: {value};" for key, value in PALETTES[PALETTE][theme].items())
    style = STYLES[STYLE]
    faces = f"--f-display: {style['display']}; --f-body: {style['body']}; --f-ui: {style['ui']}; --f-mono: {style['mono']};"
    variables = f":root {{ color-scheme: light dark; {block('light')} {faces} }}\n@media (prefers-color-scheme: dark) {{ :root {{ {block('dark')} }} }}"
    return PAGE.replace("/*VARS*/", variables).replace("/*STYLE*/", style["css"]).replace("/*FONTS*/", style["fonts"]).replace("/*BODY*/", body).replace("/*REPO*/", REPO).replace("img/card.png", back + "img/card.png")


# --- the write-up -----------------------------------------------------------------------------------------

def build():
    records, cells = load()
    summary = core.summarize(PLAN, records, ROOT)
    intervals = {(r["model"], r["harness"]): r["interval"] for r in summary["rows"]}
    rows = {model: [row(model, harness, runs, intervals) for (m, harness), runs in cells.items() if m == model] for model in MODELS}
    for model in rows:
        rows[model].sort(key=lambda r: (-r["passed"], r["seconds"]))
    ships = {model: judged(model) for model in MODELS}
    gpt, api, hosted, early = (rows[m] for m in MODELS)
    by_id = {model: {r["harness"]: r for r in rows[model]} for model in rows}
    checks = {task: next(r["checks_total"] for (m, h), runs in cells.items() for t, r in runs.items() if t == task) for task in TASKS}
    first = [r for r in records if r["run_id"].endswith(":1")]
    status = collections.Counter(r["status"] for r in first)
    started = sorted(r["started_at"] for r in first)
    versions = {h["id"]: h["version"] for h in CONFIG["harnesses"]}
    never_lost = [h for h in ships["gpt-6-1-sol"]["order"] if ships["gpt-6-1-sol"]["tally"][h][2] == 0]
    lost_most = [h for h in ships["gpt-6-1-sol"]["order"] if ships["gpt-6-1-sol"]["tally"][h][2] == 8]
    for model in list(MODELS)[:3]:      # the sentence below says so
        assert all(runs[SHIP]["checks_passed"] == runs[SHIP]["checks_total"] for (m, _), runs in cells.items() if m == model), model
    tok_total = lambda r: sum(r["tokens"][k] for k in ("input", "cached", "written", "output"))
    priced = [r for r in gpt if r["list_known"] == r["runs"]]
    counted = [r for r in gpt if r["tokens_known"]["input"] == r["runs"]]
    ties = sum(result["ties"] for result in ships.values() if result)
    pairs = sum(result["pairs"] for result in ships.values() if result)
    gpt_ship = [r["ship_seconds"] / 60 for r in gpt]
    api_ship = [r["ship_seconds"] / 60 for r in api]
    doc = Doc()

    # Summary
    doc.h(1, "Ten coding harnesses, the same models, nine tasks")
    doc.add("markdown-only", "**Harness Bench, first pass**")
    doc.p(f"Runs made {started[0][:10]} to {started[-1][:10]} (UTC) · plan `{PLAN['plan_id'][:16]}` · {len(first)} runs, one per harness, model and task")
    doc.add("tiles", [(str(len(first)), "runs, one per harness, model and task"), (str(len(CONFIG["harnesses"])), "coding harnesses"),
                      (f"{sum(r['passed'] for r in gpt)} of {sum(r['runs'] for r in gpt)}", "runs passed on gpt-6.1-sol"), (str(pairs), "ship pairs judged blind")])
    doc.note("**Read this first.** Every figure below comes from a single run per harness, model and task. The [limits](#what-this-does-not-show) are part of the result.")
    doc.add("nav", [("Findings", "Key findings"), ("At a glance", "Results at a glance"), ("3D task", "The 3D task, judged blind"),
                    ("Caveats", "Before quoting a number"), ("Setup", "Setup"), ("Details", "Detailed results"),
                    ("Allowance", "What the runs cost in subscription allowance"), ("Limits", "What this does not show"), ("Data", "Data")])

    # Findings first: a reader decides here whether to go on
    fastest, cheapest = min(gpt, key=lambda r: r["seconds"]), min(priced, key=lambda r: r["list_usd"])
    halves = [by_id["deepseek-flash-high"][r["harness"]]["list_usd"] / r["list_usd"] for r in priced
              if r["harness"] in by_id["deepseek-flash-high"] and by_id["deepseek-flash-high"][r["harness"]]["list_known"] == 9]
    stopped = [r for r in api if r["ship_status"] == "timed_out"]
    doc.h(2, "Key findings")
    doc.ul(
        f"**The harness did not change whether the work got done.** With gpt-6.1-sol at medium effort, all {word(len(gpt))} harnesses passed all nine tasks: "
        f"{sum(r['passed'] for r in gpt)} of {sum(r['runs'] for r in gpt)} runs.",
        f"**It changed the bill.** The same nine tasks took {min(r['seconds'] for r in gpt) / 60:.0f} to {max(r['seconds'] for r in gpt) / 60:.0f} minutes, "
        f"{min(map(tok_total, counted)) / 1e6:.2f}M to {max(map(tok_total, counted)) / 1e6:.2f}M tokens and {usd(min(r['list_usd'] for r in priced))} to "
        f"{usd(max(r['list_usd'] for r in priced))} at list price. {cheapest['name']} was the cheapest and the {fastest['name']} the fastest.",
        f"**The fastest harness was the one that could look at its own work.** The {fastest['name']} has a browser tool built in and made its 3D page in "
        f"{fastest['ship_seconds'] / 60:.1f} minutes; the Codex CLI, same model and same maker, took {by_id['gpt-6-1-sol']['codex']['ship_seconds'] / 60:.1f}. "
        "The app also ran outside the sandbox, so part of that gap is the setting.",
        f"**Passing the checks was not the same as being finished.** Every 3D page passed the automatic checks. Judged blind, side by side, "
        f"{word(len(never_lost))} of the ten never lost a pair and {word(len(lost_most))} lost eight of nine.",
        f"**A cheaper model cost time on the hard task, not the easy ones.** On DeepSeek's API the nine tasks cost less in every harness, about half for most "
        f"({min(halves):.0%} to {max(halves):.0%} of the gpt-6.1-sol price), and the eight smaller tasks were as fast. But the 3D page took {min(api_ship):.0f} to {max(api_ship):.0f} minutes instead of {min(gpt_ship):.0f} to {max(gpt_ship):.0f}. "
        f"{word(len(stopped)).capitalize()} harnesses were still editing it when stopped at an hour.",
        "**One run each.** Every figure is a single run per harness, model and task. No difference in pass rate is statistically clear, and time and cost can move on a second attempt.")

    def glance(table_rows, result, notes, route=None):
        head = ["Harness"] + (["Model through"] if route else []) + ["Passed", "Time", "Cost", "Tokens", "3D task, W-T-L"]
        priced_rows = [r for r in table_rows if r["list_known"] == r["runs"] and r["model"] == table_rows[0]["model"]]
        costs = sorted(r["list_usd"] for r in priced_rows)
        lines = []
        for r in table_rows:
            ship, on_plan, hand = cells[(r["model"], r["harness"])][SHIP], r["model"] == "deepseek-v4-1-flash-plan", r["harness"] in HOW
            cost, tokens = cost_cell(r), millions(tok_total(r), r["tokens_known"]["input"], r["runs"])
            why = collections.defaultdict(list)     # the notes each cell needs, numbered below in reading order
            if hand:
                why["name"].append("Run by hand in its desktop app on a Mac with a GPU, not in the sandbox. Compare its time with the other hand-run app, not with the command-line harnesses.")
            if on_plan:
                why["route"].append("The model as hosted by the harness's own plan. It is priced here at DeepSeek's API list price for comparison; on the plan it costs allowance, not dollars. "
                                    "The plan's model may not be the same as the API's.")
            if str(ship.get("note", "")).startswith("Second attempt"):
                why["time"].append("The 3D task is a second attempt. The first was cut off at an earlier 15-minute limit while still working, and its tokens are not counted.")
            if "process_seconds" in ship:
                why["time"].append("Timed to its final answer. Its command line then stayed open, idle, about five minutes before exiting; that wait is not counted.")
            if r["ship_status"] == "timed_out":
                why["time"].append("Still working on the 3D task when stopped at 60 minutes. The page it left passes every automatic check, but the run counts as not passed.")
            if r["own_known"] and not r["list_known"]:
                note = f"{r['name']} reports dollars, not tokens. This is its own figure, with one task's share worked out from its usage total, so the true cost is this or a little more."
                cost, tokens = f"at least {usd(r['own_usd'])}", "—"
                why["cost"].append(note), why["tokens"].append(note)
            if 0 < r["list_known"] < r["runs"]:
                note = f"{r['name']} reports usage only when a run ends, so its stopped 3D run has no tokens. Cost and tokens cover the other {word(r['list_known'])} tasks."
                cost, tokens = f"at least {usd(r['list_usd'])}", f"{tok_total(r) / 1e6:.2f}M"
                why["cost"].append(note), why["tokens"].append(note)
            if len(costs) > 2 and r in priced_rows and r["list_usd"] == costs[0] and costs[0] < 0.6 * costs[1]:
                others = [x["ship_seconds"] / 60 for x in table_rows if x["model"] == r["model"] and x is not r]
                place = result["order"].index(r["harness"]) + 1
                why["cost"].append(f"By far the shortest run on this model: {r['name']}'s 3D page took {r['ship_seconds'] / 60:.1f} minutes where the others took {min(others):.0f} to {max(others):.0f}, "
                                   f"so it used far fewer tokens than the other complete runs. That page was judged {place}th of {len(result['order'])}, and the run passed {r['passed']} of {r['runs']} tasks.")
            if on_plan and r["list_known"] == r["runs"] and (ship.get("input_tokens") or 0) > 1_000_000:
                why["cost"].append(f"Most of this is the 3D run, which sent {ship['input_tokens'] / 1e6:.1f}M uncached input tokens.")
            if result and r["harness"] in result["tally"] and r["model"] == result_model(result):
                judged_as = "{}-{}-{}".format(*result["tally"][r["harness"]])
            else:
                own, judged_as = ships.get(r["model"]), "—"
                if own:
                    why["judged"].append(f"Judged separately, as a single pair: {NAMES[own['order'][0]]}'s page was picked over {NAMES[own['order'][1]]}'s.")
            marks = {column: "".join(notes.mark(note) for note in why[column]) for column in ("name", "route", "time", "cost", "tokens", "judged")}
            lines.append([r["name"] + marks["name"]] + ([route(r) + marks["route"]] if route else [])
                         + [f"{r['passed']} of {r['runs']}", f"{r['seconds'] / 60:.0f} min" + marks["time"], cost + marks["cost"], tokens + marks["tokens"], judged_as + marks["judged"]])
        return head, lines, tuple(i + (1 if route else 0) for i in (2, 4))

    result_model = lambda result: next(model for model, value in ships.items() if value is result)
    doc.h(2, "Results at a glance")
    doc.p("Time is for all nine tasks. Cost is tokens at one list price for every harness, an estimate and not a bill. Tokens are everything the harness reports, cached input included. "
          "The last column is the 3D task's blind judging: pairs won, tied and lost. Numbers beside a figure point to the notes under each table.")
    doc.h(3, "gpt-6.1-sol, medium effort")
    notes = Notes("g")
    doc.table(*glance(gpt, ships["gpt-6-1-sol"], notes))
    doc.add("notes", notes.key, notes.items)
    doc.img("img/scatter-gpt.svg", "Time against cost for the nine tasks on gpt-6.1-sol, one point per harness")
    doc.h(3, "DeepSeek, high effort")
    notes = Notes("d")
    doc.table(*glance(api + hosted, ships["deepseek-flash-high"], notes,
                      route=lambda r: "DeepSeek's API" if r["model"] == "deepseek-flash-high" else "its own plan"))
    doc.add("notes", notes.key, notes.items)

    doc.h(2, "The 3D task, judged blind")
    doc.p(f"One task has no single right answer: a real-time 3D pirate ship at sunset, in one HTML file. Every page passed the ten automatic checks, so one person compared them side by side, "
          f"{pairs} pairs in all, without knowing which harness made which. The rule was completeness first (gaps in the ship that the sea shows through), then a little weight for style.")
    doc.img("img/ships-gpt.svg", "Pairs won, tied and lost by each harness's ship on gpt-6.1-sol")
    doc.img("img/ships-deepseek.svg", "Pairs won, tied and lost by each harness's ship on DeepSeek's API at high effort")
    doc.gallery([(f"ships/thumbs/gpt-6-1-sol.{h}.jpg", f"ships/gpt-6-1-sol.{h}.html", f"{NAMES[h]} · gpt-6.1-sol") for h in ships["gpt-6-1-sol"]["order"]
                 if (OUT / "ships" / f"gpt-6-1-sol.{h}.html").is_file()])
    doc.p("The ten gpt-6.1-sol pages, best-judged first. Each picture opens the page itself: drag to move the camera. [All 23 pages](ships/index.html), DeepSeek's included.")

    doc.h(2, "Before quoting a number")
    doc.ul(
        "**One run per harness, model and task.** The plan has three repeats and one was run, so nothing here measures run-to-run variation.",
        "**Two settings.** The Codex app and Capy ran by hand on a Mac with a GPU. The other eight ran headless in a container without one. Compare times within a group.",
        "**Cost is an estimate** from tokens and one price list, not what anyone was billed. Runs on a subscription cost allowance, not dollars.",
        "**One judge** for the 3D task, and one page per harness and model.",
        "**Not in this pass:** Claude Code, Cursor and others; repeats two and three of the plan; any mode with subagents.",
        "**Made with an AI assistant.** The tasks, the benchmark and this write-up were produced with Claude Code, which is not among the harnesses compared.")
    doc.p(f"The [full list of limits](#what-this-does-not-show) is further down. To explore: [interactive results](results/index.html) · [every ship, running](ships/index.html) · [data]({HERE}/data).")
    doc.add("markdown-only", "The first two of those are HTML pages: GitHub shows their source. Open them from a clone (`docs/first-pass/index.html`) or through GitHub Pages if it is switched on for this repository.")

    # Setup
    doc.h(2, "Setup")
    doc.ul(
        f"**Suite and plan:** `suites/pilot-v1.json`, plan `{PLAN['plan_id'][:16]}`. The plan holds {len(PLAN['runs'])} runs (three repeats); this is the first repeat, {len(first)} runs.",
        f"**Tasks:** nine, each started from the same folder with the same prompt. Eight are graded only by hidden checks; one is also judged by eye.",
        f"**Time limit:** {CONFIG['budget']['timeout_seconds'] // 60} minutes per run, as a safety stop. The first "
        f"{sum(1 for r in first if r.get('made_under_timeout_seconds') == 900)} runs were made under a 15-minute limit; those that finished by themselves were kept, since a harness is never told the limit.",
        "**Sandbox:** each command-line run in its own Docker container (image `harness-bench:latest`, Linux, 2 CPUs, 4 GB, no GPU, network on) with a fresh home directory and only that harness's login copied in.",
        "**Host:** Apple M1 Pro, 16 GB, macOS 15.7, Docker Desktop 29.8.",
        "**By hand:** the Codex app and Capy have no unattended mode. Each task was pasted into a new chat in a fresh copy of the task folder on the Mac, and the result graded by the same checks.",
        "**Grading:** hidden checks the harness never sees. A run passes only if every check passes.",
        "**Cost:** tokens multiplied by one price list for every harness. It is an estimate for comparison, not a bill: runs on a subscription cost allowance, not dollars.")
    doc.h(3, "Harnesses")
    doc.table(["Harness", "Version", "Where it ran", "Started with"],
              [[NAMES[h], f"`{versions[h]}`", HOW.get(h, "sandbox"), SETTINGS[h]] for h in NAMES])
    doc.h(3, "Models")
    model_rows = []
    for entry in CONFIG["models"]:
        used = [h["id"] for h in CONFIG["harnesses"] if entry["id"] in h.get("models", [])]
        names = sorted({(entry.get("harness_names") or {}).get(h, entry["name"]) for h in used})
        paid = "DeepSeek API key" if entry.get("billing") == "api" else \
            "ChatGPT/Codex subscription; Devin plan (Devin); Factory plan (Droid)" if entry["id"] == "gpt-6-1-sol" else "Devin plan (Devin); Factory plan (Droid)"
        model_rows.append([MODELS[entry["id"]], ", ".join(f"`{name}`" for name in names), entry.get("reasoning_effort") or "default", paid, ", ".join(NAMES[h] for h in used)])
    doc.table(["Setting", "Model names passed", "Effort asked for", "Paid through", "Harnesses"], model_rows)
    doc.p("All subscriptions were the $20 tier of each plan. Effort is what each harness was asked for; it could not be confirmed from the results.")
    doc.h(3, "Tasks")
    doc.table(["Task", "Kind", "What the agent must do", "Hidden checks"], [[f"`{task}`", kind, what, checks[task]] for task, (kind, what) in TASKS.items()], right=(3,))
    doc.p(f"Prompts, seeds, checks and reference solutions are in [`tasks/`]({REPO}/tree/main/tasks).")
    doc.h(3, "Price list")
    doc.table(["Model", "Input", "Cached input", "Cache write", "Output"],
              [[f"`{m['name']}`"] + [f"${m['price_per_mtok'][k]:g}" for k in ("input", "cached_input", "cache_write", "output")]
               for m in CONFIG["models"] if m["id"] in ("gpt-6-1-sol", "deepseek-flash-high")], right=(1, 2, 3, 4))
    doc.p("US dollars per million tokens, taken from the model catalogue shipped with Pi 1.0.4. For gpt-6.1-sol it reproduces, to the cent, the cost a second tool (CodexBar) "
          "computes from the Codex app's own logs. It has not been checked against the providers' price pages.")

    # Results in full
    doc.h(2, "Detailed results")
    doc.p(f"The same results in full, in the order of this project's [write-up template]({REPO}/blob/main/docs/writing-up-results.md).")
    doc.h(3, "1. Is there any difference in pass rate?")
    doc.table(["Model setting", "Harnesses", "Best minus worst pass rate", "p-value"],
              [[MODELS[o["model"]], o["harnesses"], f"{o['spread'] * 100:.0f} points", f"{o['p_value']:.3f}"] for o in summary["overall"]], right=(1, 2, 3))
    clear = [c for c in summary["comparisons"] if c["clear"]]
    doc.p(f"No. A permutation test per model (outcomes shuffled among harnesses within each task) finds nothing: every p-value is 1. Of {len(summary['comparisons'])} "
          f"head-to-head comparisons on the same model, {len(clear)} are clear. Everything after this point is about time, cost and the look of one task, not about which harness is more often right.")
    doc.h(3, "2. Pass rate with intervals")
    harness_order = [r["harness"] for r in gpt]
    rate = lambda model, h: f"{by_id[model][h]['passed']} of {by_id[model][h]['runs']}" if h in by_id[model] else "not run"
    doc.table(["Harness"] + [SHORT[m] for m in list(MODELS)[:3]], [[NAMES[h]] + [rate(m, h) for m in list(MODELS)[:3]] for h in harness_order])
    spans = sorted({(r["passed"], r["runs"], percent_range(r["interval"])) for m in list(MODELS)[:3] for r in rows[m]}, reverse=True)
    doc.p("With nine runs each of these is a wide range, not a point. The 95% intervals (Wilson): "
          + "; ".join(f"{passed} of {runs} is {span}" for passed, runs, span in spans) + ".")

    def time_cost(table_rows, ship_result):
        head = ["Harness", "Passed", "All nine", "Eight smaller", "Ship", "Median task", "Cost", "Per pass"]
        lines = [[r["name"], f"{r['passed']} of {r['runs']}", mins(r["seconds"]), mins(r["rest_seconds"]), ship_cell(r), f"{r['median_seconds']:.0f} s",
                  cost_cell(r), usd(r["per_pass"], 3) if r["per_pass"] is not None else "unknown"] for r in table_rows]
        if ship_result:
            head.append("Ship W-T-L")
            for line, r in zip(lines, table_rows):
                line.append("{}-{}-{}".format(*ship_result["tally"][r["harness"]]) if r["harness"] in ship_result["tally"] else "not judged")
        return head, lines

    def usage(table_rows):
        return (["Harness", "Uncached input", "Cached input", "Output", "All tokens", "Model calls", "Tool calls"],
                [[r["name"]] + [millions(r["tokens"][k], r["tokens_known"][k], r["runs"]) for k in ("input", "cached", "output")]
                 + [millions(tok_total(r), r["tokens_known"]["input"], r["runs"]),
                    count_cell(r["tokens"]["turns"], r["tokens_known"]["turns"], r["runs"]), count_cell(r["tokens"]["tools"], r["tokens_known"]["tools"], r["runs"])] for r in table_rows])

    doc.h(3, "3. gpt-6.1-sol, medium effort")
    doc.img("img/time-gpt.svg", "Minutes for the nine tasks on gpt-6.1-sol, split into the eight smaller tasks and the pirate ship")
    doc.table(*time_cost(gpt, ships["gpt-6-1-sol"]), right=(2, 3, 4, 5, 7))
    doc.p("Time is for all nine tasks, then split into the eight smaller ones and the pirate ship. Cost is at list price; per pass divides it by the tasks passed. The last column is the ship's blind judging: pairs won, tied and lost.")
    doc.table(*usage(gpt), right=(1, 2, 3, 4, 5, 6))
    doc.p("Tokens and steps are each harness's own report for the nine tasks. A dash means the harness does not report that figure; \"8 of 9\" means one run's figure is missing.")
    fastest, cheapest, slowest = min(gpt, key=lambda r: r["seconds"]), min(priced, key=lambda r: r["list_usd"]), max(gpt, key=lambda r: r["seconds"])
    heaviest = max(counted, key=tok_total)
    doc.ul(
        f"**Fastest:** {fastest['name']}, {mins(fastest['seconds'])}. Its pirate ship took {mins(fastest['ship_seconds'])}; the Codex CLI, with the same model from the same company, took {mins(by_id['gpt-6-1-sol']['codex']['ship_seconds'])}. "
        "The app has a browser tool built in. In the sandbox the CLI had none: it installed Playwright to take screenshots and wrote its own image reader to inspect them.",
        f"**Cheapest:** {cheapest['name']}, {usd(cheapest['list_usd'])} and {tok_total(cheapest) / 1e6:.2f}M tokens. {heaviest['name']} used {tok_total(heaviest) / 1e6:.2f}M tokens on the same nine tasks.",
        f"**Slowest:** {slowest['name']}, {mins(slowest['seconds'])}, with {slowest['tokens']['turns']:,} model calls against Pi's {by_id['gpt-6-1-sol']['pi']['tokens']['turns']:,}.",
        f"**Droid** was the quickest on the eight smaller tasks ({mins(by_id['gpt-6-1-sol']['droid']['rest_seconds'])}) and the slowest on the ship ({mins(by_id['gpt-6-1-sol']['droid']['ship_seconds'])}).",
        "**Capy** reports no tokens per run. Its cost is the dollar figure on its own usage page.",
        "**DeepSeek Harness** is timed to its final answer. Its command line then stayed open about five minutes before exiting; that wait is kept in the data as `process_seconds`.")

    doc.h(3, "4. DeepSeek's API, high effort")
    doc.img("img/time-deepseek.svg", "Minutes for the nine tasks on DeepSeek's API at high effort")
    doc.table(*time_cost(api, ships["deepseek-flash-high"]), right=(2, 3, 4, 5, 7))
    doc.table(*usage(api), right=(1, 2, 3, 4, 5, 6))
    both = [(by_id["gpt-6-1-sol"][r["harness"]], r) for r in api if r["list_known"] == r["runs"]]
    doc.ul(
        "**Cheaper in every harness.** " + "; ".join(f"{a['name']} {usd(b['list_usd'])} against {usd(a['list_usd'])}" for a, b in both) + ".",
        f"**The extra time is the ship.** The eight smaller tasks took {min(r['rest_seconds'] for r in api) / 60:.0f} to {max(r['rest_seconds'] for r in api) / 60:.0f} minutes in total, "
        f"against {min(r['rest_seconds'] for r in gpt) / 60:.0f} to {max(r['rest_seconds'] for r in gpt) / 60:.0f} on gpt-6.1-sol.",
        "**Two runs never stopped by themselves.** Droid and DeepSeek Harness were still editing their ships at the 60-minute stop. The pages they left pass every automatic check.",
        "**Far more tokens, mostly cached.** Long runs re-read their own history on every call.")

    doc.h(3, "5. DeepSeek V4.1 Flash as hosted by a plan")
    doc.table(*time_cost(hosted, None), right=(2, 3, 4, 5, 7))
    doc.table(*usage(hosted), right=(1, 2, 3, 4, 5, 6))
    doc.p("Only Devin and Droid offer this route. Droid also ran on DeepSeek's own API (section 4): 8 of 9 there, 7 of 9 here. The plans' model and the API's `deepseek-flash` may not be the same model.")

    doc.h(3, "6. By task")

    def matrix(table_rows, model, value):
        lines = []
        for r in table_rows:
            line = [r["name"]]
            for task in TASKS:
                record = cells[(model, r["harness"])].get(task)
                line.append("none" if record is None else value(record))
            lines.append(line)
        return ["Harness"] + [BRIEF[task] for task in TASKS], lines, tuple(range(1, len(TASKS) + 1))

    seconds_cell = lambda record: f"{record['elapsed_seconds']:.0f}" + {"passed": "", "failed": " ✗", "timed_out": " ■"}[record["status"]]
    price_cell = lambda record: f"{record['list_price_usd']:.3f}" if record.get("list_price_usd") is not None else (f"{record['cost_usd']:.2f}*" if record.get("cost_usd") is not None else "?")
    doc.p("Seconds per task, with the tasks in the order of the task table above. ✗ marks a failed check and ■ a run stopped at the time limit.")
    doc.h(4, "gpt-6.1-sol")
    doc.table(*matrix(gpt, "gpt-6-1-sol", seconds_cell))
    doc.h(4, "DeepSeek's API, high effort")
    doc.table(*matrix(api, "deepseek-flash-high", seconds_cell))
    extra = Doc()
    extra.p("Dollars per task at list price. `*` marks a harness's own figure and `?` an unknown cost.")
    extra.h(4, "gpt-6.1-sol: cost per task")
    extra.table(*matrix(gpt, "gpt-6-1-sol", price_cell))
    extra.h(4, "DeepSeek's API, high effort: cost per task")
    extra.table(*matrix(api, "deepseek-flash-high", price_cell))
    extra.h(4, "Plan-hosted DeepSeek: seconds per task")
    extra.table(*matrix(hosted, "deepseek-v4-1-flash-plan", seconds_cell))
    doc.details("Cost per task, and the plan-hosted rows", extra)
    doc.p(f"On gpt-6.1-sol the pirate ship is {sum(r['ship_seconds'] for r in gpt) / sum(r['seconds'] for r in gpt):.0%} of all time spent; on DeepSeek's API it is "
          f"{sum(r['ship_seconds'] for r in api) / sum(r['seconds'] for r in api):.0%}. One task drives most of the time differences.")

    doc.h(3, "7. What tripped them up")
    problems = []
    for model in list(MODELS)[:3]:
        for r in rows[model]:
            for task in TASKS:
                record = cells[(model, r["harness"])].get(task)
                if record is not None and record["status"] != "passed":
                    what = "; ".join(failed_checks(record)) if record["status"] == "failed" else \
                        f"still working when stopped at {record['elapsed_seconds'] / 60:.0f} minutes; the page as left passes {record['checks_passed']} of {record['checks_total']} checks"
                    problems.append([r["name"], MODELS[model], f"`{task}`", f"{record['checks_passed']} of {record['checks_total']}", what])
    doc.table(["Harness", "Model setting", "Task", "Checks passed", "The check that failed, or why the run did not pass"], problems)
    failed_runs = [line for line in problems if "still working" not in line[4]]
    doc.p(f"Every run that did not pass is on a DeepSeek route. {word(len(failed_runs)).capitalize()} runs failed {word(sum(line[4].count(';') + 1 for line in failed_runs))} checks between them. "
          "Each failed check tests one behaviour the prompt states, and each was failed by one harness only on that model setting.")
    doc.h(3, "8. Blocked and ungraded runs")
    doc.p("None remain. During the runs one OpenCode run was refused by a subscription usage limit and was run again after the limit reset. "
          "Two gpt-6.1-sol ship runs (Devin, Droid) were first cut off at the earlier 15-minute limit and were made again without it; each is a fresh attempt, not a continuation. "
          "Capy's `log-report` run stalled at a prompt asking for access outside the task folder, changed nothing, and was run again in a new chat.")

    doc.h(3, "9. The pirate ship, judged by eye")
    doc.p(f"Every page that was judged passes all ten automatic checks, so looks were judged separately. One person (the author) compared pages side by side, {pairs} pairs in all, "
          "without being told which harness made which. Both pages ran live so the camera could be moved. The judge's rule: completeness first (gaps in the ship through which the sea shows), "
          f"\"about the same\" when both are complete, and a small weight for style. {ties} of the {pairs} picks were ties.")
    for model, title, image in (("gpt-6-1-sol", "gpt-6.1-sol", "img/ships-gpt.svg"), ("deepseek-flash-high", "DeepSeek's API, high effort", "img/ships-deepseek.svg")):
        result = ships[model]
        doc.h(4, f"{title}: {result['pairs']} pairs")
        doc.table(["Rank", "Harness", "Won", "Tied", "Lost", "Rating", "95% interval", "Ship time", "Ship cost"],
                  [[place, NAMES[h], *result["tally"][h], f"{result['rating'][h][0]:.0f}", f"{result['rating'][h][1]:.0f} to {result['rating'][h][2]:.0f}",
                    ship_cell(by_id[model][h]), (lambda record: usd(record["list_price_usd"]) if record.get("list_price_usd") is not None else
                                                 f"{usd(record['cost_usd'])} (own figure)" if record.get("cost_usd") is not None else "unknown")(cells[(model, h)][SHIP])]
                   for place, h in zip(shared_ranks(result["order"], result["tally"]), result["order"])], right=(0, 2, 3, 4, 5, 7, 8))
        grid = Doc()
        grid.p("Each row against each column: W won, T tied, L lost.")
        grid.table(["Harness"] + [NAMES[h] for h in result["order"]],
                   [[NAMES[a]] + ["·" if a == b else result["against"][(a, b)] for b in result["order"]] for a in result["order"]])
        doc.details(f"Who beat whom on {title}", grid)
    hosted_result = ships["deepseek-v4-1-flash-plan"]
    winner = hosted_result["order"][0]
    doc.h(4, "Plan-hosted DeepSeek: 1 pair")
    doc.p(f"{NAMES[winner]}'s page was picked over {NAMES[hosted_result['order'][1]]}'s. The judge's note: the other had the better style but a hole at the back of the ship.")
    doc.ul(
        "**Ratings** are Bradley-Terry strengths on an Elo-style scale (1500 is average). Intervals come from resampling the picks; where they overlap the order is not settled.",
        f"**On gpt-6.1-sol** the five pages that never lost ({', '.join(NAMES[h] for h in never_lost)}) cannot be told apart. Capy's and Hermes Agent's are clearly below the rest.",
        "**On DeepSeek** the top five overlap; OpenCode's and Hermes Agent's are clearly below. The two top-ranked pages come from runs that were stopped at 60 minutes, so they had the most time.",
        "**No second judge**, so there is no measure of agreement. A model judge was not used.")
    doc.h(4, "Every ship")
    gallery = []
    for model in MODELS:
        for r in sorted(rows[model], key=lambda r: r["name"]):
            if (OUT / "ships" / f"{model}.{r['harness']}.html").is_file():
                state = "" if r["ship_status"] == "passed" else f" ({ship_cell(r)})"
                gallery.append((f"ships/thumbs/{model}.{r['harness']}.jpg", f"ships/{model}.{r['harness']}.html", f"{r['name']} · {SHORT[model]}{state}"))
    doc.gallery(gallery)
    doc.p("Each picture opens the page itself: drag to move the camera. [All of them on one page](ships/index.html).")
    doc.h(3, "10. Subagent mode")
    doc.p("Not run. Every run used each harness's ordinary single-agent mode.")

    # Allowance
    doc.h(2, "What the runs cost in subscription allowance")
    doc.table(["Plan", "Runs", "Limit used", "How it was read"], [list(line) for line in ALLOWANCE])
    doc.p("These are whole percentage points from the providers' own meters, mostly single before-and-after readings. They are rough, and the plans' windows differ (5 hours, a day, a week), so they do not convert into one another.")

    # Limits
    doc.h(2, "What this does not show")
    doc.h(3, "Sample size")
    doc.ul(
        "**One run per harness, model and task.** The plan has three repeats and one was run. Run-to-run variation was not measured.",
        "**No pass-rate difference is statistically clear.** A 9 of 9 row has a 95% interval of 70% to 100%.",
        "**Time, tokens and cost are single measurements.** A second attempt can differ a lot: Devin's first ship attempt was still working at 15 minutes, and its second finished in about 10.")
    doc.h(3, "Tasks")
    doc.ul(
        "**Nine small tasks, mostly JavaScript, each a few minutes of work.** Nothing here measures work in a large existing codebase or over a long session.",
        "**The eight graded tasks are at gpt-6.1-sol's ceiling.** Every run passed, so they cannot separate harnesses on correctness with that model.",
        "**One author wrote the tasks, checks and reference solutions, with an AI assistant (Claude Code).** The benchmark's code and this write-up were produced the same way. Claude Code is not among the harnesses compared.",
        "**Hidden checks miss things.** The ship's checks pass pages with visible holes; a check can also encode an assumption the prompt does not state.",
        "**The ship's brief follows a widely shared one-prompt demo,** so models may have seen similar work.")
    doc.h(3, "Conditions were not identical")
    doc.ul(
        "**Two settings.** The Codex app and Capy ran by hand on the Mac, with its GPU and, for the Codex app, the user's own configuration and built-in browser tool. The other eight ran headless in a Linux container with 2 CPUs, 4 GB, no GPU and an empty home directory. Compare times within a group, not across.",
        "**Software rendering.** In the container a 3D page is drawn without a GPU, and a harness that wanted to look at its page had to install its own tooling first.",
        "**Hand-run times come from each app's own record** (the Codex app's session logs, Capy's \"Worked for\" timers), not from the runner's clock.",
        "**Three routes to one model.** gpt-6.1-sol was reached through the ChatGPT/Codex subscription, Devin's plan and Factory's plan. What each provider sets on its side is not visible.",
        "**Effort is what was asked for.** DeepSeek has no \"medium\" level; the first DeepSeek rows asked for it and ran at an unknown effort, so they were run again at high and are kept only in the appendix.",
        "**The API's `deepseek-flash` and the plans' DeepSeek V4.1 Flash may be different models.**",
        "**Each harness's own system prompt, tools and defaults are part of what is measured.** Only the model and effort were matched.",
        "**Second attempts.** Devin's and Droid's gpt-6.1-sol ships and Capy's `log-report` are second attempts; the first attempts' tokens are not counted.",
        "**The time limit changed during the study,** from 15 to 60 minutes.",
        "**DeepSeek Harness.** gpt-6.1-sol is not in its built-in model list and was declared in its settings. Its time on that model is measured to its final answer. Two of its nine runs there ended with a connection error after the files were complete and are counted as passed.",
        "**Network was on.** Harnesses could and did install packages.")
    doc.h(3, "Cost and usage")
    doc.ul(
        "**Cost is an estimate, not a bill.** It is tokens multiplied by one price list that has not been checked against the providers' pages.",
        "**Token counts are each harness's own report,** read by a separate parser per harness. Definitions can differ, for example in whether reasoning is counted as output.",
        "**Capy reports no tokens per run.** Its cost is its own dollar figure, and one task's share was worked out from its usage total, so it is a floor.",
        "**Droid reports usage only when a run ends.** Its two stopped ships have no tokens, so its DeepSeek costs are floors.",
        "**Allowance readings are rough:** whole points, single readings, and some cover mixed runs.")
    doc.h(3, "Judging")
    doc.ul(
        "**One judge, one page per harness and model.** Another attempt by the same harness could look different, and another judge could choose differently.",
        "**The rule favours completeness.** It separates flawed pages from clean ones and does not rank the clean ones against each other.",
        "**The judge saw the pages running in a desktop browser with a GPU,** not in the software-rendered setting the automatic checks used.",
        "**Three judged DeepSeek pages come from runs stopped at the time limit.**",
        "**Blindness covers file names and the judging page.** A page could in principle identify its maker on screen; none was seen to.")
    doc.h(3, "Scope and age")
    doc.ul(
        "**Not tested:** Claude Code, Cursor and other harnesses; other models; subagent modes; team or cloud features of any plan.",
        "**Versions are those of early October 2026.** Harnesses and models change behind the same names; these numbers will age.",
        "**One machine, one network, one account per provider.**")

    # Appendix and reproduction
    doc.h(2, "Appendix: the superseded DeepSeek rows")
    doc.p("The first DeepSeek runs asked for \"medium\" effort, which DeepSeek does not have, under the 15-minute limit. They are kept for the record and are not used above.")
    doc.table(*time_cost(early, None), right=(2, 3, 4, 5, 7))
    doc.h(2, "Reproducing it")
    doc.code("docker build -t harness-bench:latest docker/\n"
             "python3 -m harness_bench check --suite runs/pilot-v1-pinned.json          # tasks, image, versions, logins; no model calls\n"
             "python3 -m harness_bench run --plan runs/pilot-v1-plan.json --repetition 1  # spends your own keys and allowances\n"
             "python3 -m harness_bench report --plan runs/pilot-v1-plan.json --html report.html\n"
             "python3 -m harness_bench judge-prepare --plan runs/pilot-v1-plan.json --task pirate-ship-3d --model gpt-6-1-sol\n"
             "python3 scripts/publish_first_pass.py")
    doc.h(2, "Data")
    doc.ul(
        "[`data/results.jsonl`](data/results.jsonl): one record per run, with status, checks, seconds, tokens, cost and notes.",
        "[`data/plan.json`](data/plan.json): the pinned plan, with task revisions, harness versions, model settings and prices.",
        "[`data/summary.json`](data/summary.json): the per-harness figures in this write-up.",
        f"[`data/judging/`]({HERE}/data/judging): the pairs, the judge's picks and the rankings.",
        "[`results/index.html`](results/index.html): the interactive results page, with every run and its failed checks.",
        "Raw transcripts and the folders each run left are not published; they can hold provider output and login details.")
    return doc, rows, ships, gpt, never_lost


def copy_assets(rows):
    for name in ("img", "ships", "results", "data"):
        shutil.rmtree(OUT / name, ignore_errors=True)
    (OUT / "img").mkdir(parents=True)
    (OUT / "ships" / "thumbs").mkdir(parents=True)
    (OUT / "data" / "judging").mkdir(parents=True)
    shutil.copytree(BASE / "report", OUT / "results", ignore=shutil.ignore_patterns("report.md", "report.err"))
    shutil.copyfile(BASE / "results.jsonl", OUT / "data" / "results.jsonl")
    shutil.copyfile(ROOT / "runs/pilot-v1-plan.json", OUT / "data" / "plan.json")
    for path in sorted((BASE / "judging").glob("*.json")) + sorted((BASE / "judging").glob("ranking.*.md")):
        shutil.copyfile(path, OUT / "data" / "judging" / path.name)
    try:
        from PIL import Image
    except ImportError:
        Image = None
    listing = []
    for model in MODELS:
        for r in sorted(rows[model], key=lambda r: r["seconds"]):
            folder = BASE / f"{SHIP}.{r['harness']}.{model}.single.1"
            name = f"{model}.{r['harness']}"
            try:
                with tarfile.open(folder / "workspace.tar.gz") as archive:
                    member = next(m for m in archive.getmembers() if m.name == "workspace/index.html")
                    (OUT / "ships" / f"{name}.html").write_bytes(archive.extractfile(member).read())
            except (OSError, StopIteration, tarfile.TarError):
                continue
            frames = sorted((folder / "capture").glob("frame-*.jpg"))
            if frames:
                if Image:
                    picture = Image.open(frames[-1]).convert("RGB")
                    picture.thumbnail((640, 400))
                    picture.save(OUT / "ships" / "thumbs" / f"{name}.jpg", quality=82)
                else:
                    shutil.copyfile(frames[-1], OUT / "ships" / "thumbs" / f"{name}.jpg")
            listing.append((model, r, name))
    listing_page = Doc().h(1, "Every pirate ship").p("One page per harness and model, as each run left it. Drag to move the camera. [Back to the report](../index.html).")
    for model in MODELS:
        group = [(r, name) for m, r, name in listing if m == model]
        if group:
            listing_page.h(2, MODELS[model])
            listing_page.gallery([(f"thumbs/{name}.jpg", f"{name}.html", f"{r['name']} · {ship_cell(r)}") for r, name in group])
    (OUT / "ships" / "index.html").write_text(page(to_html(listing_page), "../"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records, cells = load()
    intervals = {}
    rows = {model: [row(model, harness, runs, intervals) for (m, harness), runs in cells.items() if m == model] for model in MODELS}
    copy_assets(rows)                       # the gallery in the write-up lists the ship pages that exist
    doc, rows, ships, gpt, never_lost = build()
    def draw():
        return {"time-gpt": time_chart("gpt-6.1-sol: minutes for the nine tasks", rows["gpt-6-1-sol"]),
                "time-deepseek": time_chart("DeepSeek's API, high effort: minutes for the nine tasks", rows["deepseek-flash-high"]),
                "ships-gpt": ship_chart("gpt-6.1-sol ships: pairs won, tied and lost", ships["gpt-6-1-sol"]),
                "ships-deepseek": ship_chart("DeepSeek ships: pairs won, tied and lost", ships["deepseek-flash-high"]),
                "scatter-gpt": scatter(gpt, never_lost=never_lost)}

    charts = {}
    for theme, suffix in (("dark", "-dark"), ("light", "")):      # light last, so the share picture is drawn in it
        use(theme)
        charts.update({f"{name}{suffix}.svg": content for name, content in draw().items()})
    charts.update({f"{name}-card.svg": on_card(content) for name, content in draw().items()})      # light, the theme last set
    charts["card.svg"] = card(gpt, never_lost)
    for name, content in charts.items():
        (OUT / "img" / name).write_text(content)
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-w", "1600", str(OUT / "img" / "card.svg"), "-o", str(OUT / "img" / "card.png")], check=True)
    (OUT / "README.md").write_text(markdown(doc) + "\n")
    (OUT / "index.html").write_text(page(to_html(doc)))
    tidy = lambda r: {k: v for k, v in r.items() if k != "interval"} | {"interval": r["interval"]}
    (OUT / "data" / "summary.json").write_text(json.dumps({
        "plan_id": PLAN["plan_id"], "rows": {model: [tidy(r) for r in rows[model]] for model in rows},
        "ships": {model: {"pairs": s["pairs"], "ties": s["ties"], "tally": s["tally"], "rating": s["rating"]} for model, s in ships.items() if s},
        "allowance": [dict(zip(("plan", "runs", "used", "how_read"), line)) for line in ALLOWANCE]}, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}: README.md, index.html, {len(charts)} charts, "
          f"{len(list((OUT / 'ships').glob('*.html'))) - 1} ship pages, results page and data")


if __name__ == "__main__":
    main()
