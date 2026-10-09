"""Blind side-by-side judging of visual tasks, by people or by a model.

`prepare` builds a self-contained folder: the captured stills and clips copied under random
names and a page for a person to work through. The key that says which attempt is which is
written beside the folder, not in it, so the folder can be handed to a judge as it is.
`judge_with_model` answers the same pairs with any command-line model. `ranking` joins picks
with the key and scores the configurations.
"""

import hashlib
import json
import os
from pathlib import Path
import random
import re
import secrets
import shlex
import shutil
import subprocess
import tarfile
import tempfile

from . import tasks
from .core import require, validate_plan
from .runner import run_directory
from .ranking import agreement, rank

ANSWERS = ("left", "right", "tie")

QUESTION = """You are judging two attempts at the same task. The two image files in the current directory,
left.png and right.png, are screenshots of the two results. Open both and look at them before answering.

The task given to both attempts:
---
{prompt}
---

Decide which attempt is the better result for this task: how well it meets the brief, and how good it looks
(composition, lighting, colour, detail, polish). Ignore which side an image is on. If they are equally good, say TIE.

Explain your choice in two or three sentences, then end with one final line containing only LEFT, RIGHT or TIE."""


def key_path(folder):
    return Path(str(Path(folder)).rstrip("/") + ".key.json")


def read_key(folder):
    path = key_path(folder)
    require(path.is_file(), f"no key for {folder}: expected {path} (written by judge-prepare)")
    return json.loads(path.read_text(encoding="utf-8"))


# Left out when an attempt's files are unpacked for live viewing: nothing a page needs, and a lot of weight.
NOT_FOR_VIEWING = (".git", ".git-as-left-by-agent", "node_modules")


def unpack_for_viewing(archive, page, target):
    """Unpack what an attempt left so that its page can be opened live, and say whether the page is there.

    Only plain files are written, and only inside `target`: an archive holds whatever an agent made,
    links and odd paths included.
    """
    if not Path(archive).is_file():
        return False
    try:
        with tarfile.open(archive) as tar:
            for member in tar:
                parts = Path(member.name).parts
                if (not member.isreg() or len(parts) < 2 or parts[0] != "workspace" or ".." in parts
                        or any(part in NOT_FOR_VIEWING for part in parts)):
                    continue
                destination = target.joinpath(*parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, open(destination, "wb") as copy:
                    shutil.copyfileobj(source, copy)
    except (OSError, tarfile.TarError):
        shutil.rmtree(target, ignore_errors=True)
        return False
    return (target / page).is_file()


def prepare(plan, root, task_id, *, per_pair=None, seed=0, replace=False, model=None):
    """Write runs/<plan>/judging/<task>/ and return its path.

    With `model`, only that model's attempts are paired, in runs/<plan>/judging/<task>.<model>/:
    harnesses are then compared on the same model, which is the comparison the suite is designed for.

    Preparing again draws new pairs under new names, which orphans any picks already made,
    so an existing folder is only overwritten when `replace` is set.
    """
    validate_plan(plan)
    root = Path(root).resolve()
    configuration = plan["configuration"]
    entry = next((task for task in configuration["tasks"] if task["id"] == task_id), None)
    require(entry, f"no task {task_id} in this plan")
    task = tasks.load(root, entry)
    require(task.capture, f"task {task_id} has no capture settings, so there is nothing to look at")
    base = root / "runs" / plan["plan_id"][:16]
    target = base / "judging" / (task_id if model is None else f"{task_id}.{model}")
    require(replace or not (target.exists() or key_path(target).exists()),
            f"{target} already exists. Picks made for it would stop matching; pass --replace to discard it anyway")
    # Build beside the destination and swap in only once complete, so a failure costs nothing:
    # neither a half-made folder nor, with --replace, the folder and key that earlier picks need.
    staging = target.with_name(target.name + ".building")
    shutil.rmtree(staging, ignore_errors=True)
    key_path(staging).unlink(missing_ok=True)
    try:
        _prepare(plan, task, task_id, base, staging, per_pair, seed, model)
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging, target)
        os.replace(key_path(staging), key_path(target))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        key_path(staging).unlink(missing_ok=True)
        raise
    return target


def _prepare(plan, task, task_id, base, target, per_pair, seed, model=None):
    configuration = plan["configuration"]
    (target / "media").mkdir(parents=True)

    # Each attempt gets a random name, so neither file names nor the judging page's source reveal the harness.
    # An attempt's own page is shown as the agent wrote it; nothing stops an agent signing its work on screen.
    attempts, by_configuration = {}, {}
    page = task.capture.get("path") if isinstance(task.capture, dict) else None
    for run in plan["runs"]:
        if run["task_id"] != task_id or model not in (None, run.get("model_id")):
            continue
        frames = run_directory(base, run) / "capture"
        report = frames / "capture.json"
        if not report.is_file():
            continue
        capture = json.loads(report.read_text())
        if not capture.get("frames"):
            continue
        name = secrets.token_hex(6)
        (target / "media" / name).mkdir()
        still = capture["frames"][-1]["file"]
        shutil.copyfile(frames / still, target / "media" / name / "still.png")
        clip = []
        for index, frame in enumerate(capture.get("clip") or []):
            shutil.copyfile(frames / frame["file"], target / "media" / name / f"clip-{index:03d}.jpg")
            clip.append(frame["offset_ms"])
        # The page itself, where the run's files were kept: a judge can then move around in it, which a clip cannot show.
        live = bool(page) and unpack_for_viewing(run_directory(base, run) / "workspace.tar.gz", page, target / "media" / name / "live")
        key = (run["harness_id"], run.get("model_id", configuration.get("model")), run.get("mode_id", "single"))
        attempts[name] = {"run_id": run["run_id"], "configuration": list(key), "repetition": run["repetition"], "clip_ms": clip,
                          "live": live}
        by_configuration.setdefault(key, []).append(name)
    require(len(by_configuration) >= 2, f"need captured attempts from at least two configurations for {task_id}")

    # Every pair of configurations meets once per repetition they both have, sides chosen at random.
    rng = random.Random(seed)
    pairs = []
    keys = sorted(by_configuration)
    for index, first in enumerate(keys):
        for second in keys[index + 1:]:
            matches = list(zip(by_configuration[first], by_configuration[second]))
            rng.shuffle(matches)
            for one, other in matches[:per_pair]:
                left, right = (one, other) if rng.random() < 0.5 else (other, one)
                pairs.append({"left": left, "right": right})
    rng.shuffle(pairs)
    for index, pair in enumerate(pairs, 1):
        pair["id"] = f"p{index:03d}"

    # Picks are only meaningful for this exact set of matchups; the fingerprint ties them to it.
    fingerprint = hashlib.sha256(json.dumps([pairs, sorted(attempts)], sort_keys=True).encode()).hexdigest()[:12]
    key = {"plan_id": plan["plan_id"], "task_id": task_id, "pairs_id": fingerprint, "prompt": task.prompt,
           "attempts": attempts, "pairs": pairs}
    key_path(target).write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    shape = task.capture if isinstance(task.capture, dict) else {}
    data = {"task_id": task_id, "pairs_id": fingerprint, "prompt": task.prompt, "pairs": pairs,
            "clips": {name: attempt["clip_ms"] for name, attempt in attempts.items()},
            "live": {name: f"live/{page}" for name, attempt in attempts.items() if attempt["live"]},
            "aspect": [shape.get("width") or 16, shape.get("height") or 10]}
    (target / "index.html").write_text(PAGE.replace("/*DATA*/null", json.dumps(data).replace("<", "\\u003c")), encoding="utf-8")
    return target


def last_answer(text):
    """The verdict on the final line of a judge's reply, or None if that line is not purely a verdict.

    The judge is asked to end with a line holding only LEFT, RIGHT or TIE. Case, punctuation,
    emphasis marks and a lead-in such as "Final answer:" are allowed. A sentence is not:
    "the LEFT image is clearly worse" must never count as a vote for left.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    bare = re.sub(r"^(the\s+)?(final\s+)?(answer|verdict|choice|pick)\s*(is)?\s*[:\-]?\s*", "",
                  lines[-1].strip("*_`#>. "), flags=re.IGNORECASE).strip("*_`#>.:!\"' ")
    return bare.lower() if bare.lower() in ANSWERS else None


def judge_with_model(folder, command, label, *, both_orders=True, log=print):
    """Ask a command-line model about every pair. Returns the picks document.

    `command` is a command line containing {prompt}. For each question it runs in a fresh
    directory holding only left.png and right.png, so it cannot see the key or the run
    folders, and it must print its answer. With both_orders, each pair is asked twice with
    the sides swapped, and a model that does not pick the same attempt both times is recorded
    as a tie, which removes its preference for one side from the result.
    """
    folder = Path(folder)
    key = read_key(folder)
    template = shlex.split(command)
    require(any("{prompt}" in part for part in template), "the judge command must contain {prompt}")
    question = QUESTION.format(prompt=key["prompt"].strip())

    def ask(left, right):
        with tempfile.TemporaryDirectory(prefix="hb-judge-") as booth:
            shutil.copyfile(folder / "media" / left / "still.png", Path(booth) / "left.png")
            shutil.copyfile(folder / "media" / right / "still.png", Path(booth) / "right.png")
            try:
                done = subprocess.run([part.replace("{prompt}", question) for part in template], cwd=booth,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=600)
            except (subprocess.TimeoutExpired, OSError):
                # One question that cannot be asked must not throw away the answers already paid for.
                return None
        # A command that failed has not judged anything, whatever its message happens to say.
        return last_answer(done.stdout) if done.returncode == 0 else None

    picks, stats = [], {"asked": 0, "unreadable": 0, "changed_with_side": 0}
    for index, pair in enumerate(key["pairs"], 1):
        answers = [ask(pair["left"], pair["right"])]
        if both_orders:
            swapped = ask(pair["right"], pair["left"])
            answers.append({"left": "right", "right": "left"}.get(swapped, swapped))
        stats["asked"] += len(answers)
        if None in answers:
            stats["unreadable"] += 1
            log(f"[{index}/{len(key['pairs'])}] {pair['id']}: no readable answer, skipped")
            continue
        if len(set(answers)) > 1:
            stats["changed_with_side"] += 1
        winner = answers[0] if len(set(answers)) == 1 else "tie"
        picks.append({"pair": pair["id"], "winner": winner})
        log(f"[{index}/{len(key['pairs'])}] {pair['id']}: {winner}" + (" (answers differed by side)" if len(set(answers)) > 1 else ""))
    return {"judge": label, "kind": "model", "task_id": key["task_id"], "pairs_id": key["pairs_id"],
            "both_orders": both_orders, "stats": stats, "picks": picks}


def load_picks(path, key):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    require(document.get("pairs_id") == key["pairs_id"] and document.get("task_id") == key["task_id"],
            f"{path}: these picks are for a different task or a different set of pairs (judge-prepare was run again?)")
    known = {pair["id"] for pair in key["pairs"]}
    answers = {}
    for pick in document.get("picks", []):
        require(pick.get("pair") in known and pick.get("winner") in ANSWERS, f"{path}: invalid pick {pick}")
        answers[pick["pair"]] = pick["winner"]
    return document.get("judge") or Path(path).stem, answers, document


def ranking(folder, pick_files):
    """Markdown: a ranking per judge, a pooled ranking, and agreement between judges."""
    key = read_key(folder)
    label = lambda name: " / ".join(str(part) for part in key["attempts"][name]["configuration"])
    pairs = {pair["id"]: pair for pair in key["pairs"]}
    items = sorted({label(name) for name in key["attempts"]})
    judges = [load_picks(path, key) for path in pick_files]
    require(judges, "give at least one picks file")

    def comparisons(answers):
        return [(label(pairs[pair]["left"]), label(pairs[pair]["right"]), {"left": 1, "right": 0, "tie": 0.5}[winner])
                for pair, winner in answers.items()]

    lines = [f"# Side-by-side ranking: {key['task_id']}", "",
             f"{len(key['pairs'])} pairs from {len(key['attempts'])} captured attempts across {len(items)} configurations.", ""]
    sections = [(f"Judge: {name} ({len(answers)} picks)", comparisons(answers)) for name, answers, _ in judges]
    if len(judges) > 1:
        sections.append(("All judges pooled", [c for _, answers, _ in judges for c in comparisons(answers)]))
    for title, picks in sections:
        lines += [f"## {title}", "", "| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |",
                  "|---:|---|---:|---|---:|---:|"]
        for position, row in enumerate(rank(picks, items), 1):
            interval = f"{row['low']:.0f} to {row['high']:.0f}" if row["low"] is not None else "unknown"
            share = f"{row['win_share']:.0%}" if row["win_share"] is not None else "unknown"
            lines.append(f"| {position} | {row['item']} | {row['rating']:.0f} | {interval} | {share} | {row['games']} |")
        lines.append("")
    for _, _, document in judges:
        stats = document.get("stats")
        if stats and document.get("both_orders"):
            asked = stats["asked"] // 2
            lines.append(f"{document.get('judge')}: gave a different answer when the sides were swapped on "
                         f"{stats['changed_with_side']} of {asked} pairs (recorded as ties); {stats['unreadable']} had no readable answer.")
    if len(judges) > 1:
        lines += ["", "## Agreement between judges", "", "| Judges | Shared pairs | Same answer | Cohen's kappa |", "|---|---:|---:|---:|"]
        for index, (first, first_answers, _) in enumerate(judges):
            for second, second_answers, _ in judges[index + 1:]:
                result = agreement(first_answers, second_answers)
                same = f"{result['agreement']:.0%}" if result["pairs"] else "unknown"
                kappa = "unknown" if not result["pairs"] else "undefined" if result["kappa"] is None else f"{result['kappa']:.2f}"
                lines.append(f"| {first} and {second} | {result['pairs']} | {same} | {kappa} |")
    lines += ["", "Ratings are Bradley-Terry strengths on an Elo-style scale: 1500 is average, and a 400-point gap means ten-to-one odds of being picked. "
              "Intervals come from resampling the picks. Overlapping intervals mean the order is not settled.",
              "Kappa is agreement beyond chance: 0 is chance level and 1 is perfect. It is undefined when both judges gave one and the same answer every time. "
              "A model judge is only worth trusting on a task where it agrees well with people."]
    return "\n".join(lines) + "\n"


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Side-by-side judging</title>
<style>
:root { color-scheme: light dark; --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --line: #c3c2b7; --accent: #2a78d6; }
@media (prefers-color-scheme: dark) { :root { --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --line: #383835; --accent: #3987e5; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1500px; margin: 0 auto; padding: 16px; }
h1 { font-size: 20px; margin: 0; }
header { display: flex; flex-wrap: wrap; gap: 8px 20px; align-items: baseline; justify-content: space-between; }
.sub { color: var(--ink-2); }
details { margin: 10px 0; color: var(--ink-2); }
details pre { white-space: pre-wrap; font: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
figure { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
figure img { display: block; width: 100%; height: auto; background: #000; }
figure iframe { display: block; width: 100%; border: 0; background: #000; }
figure [hidden] { display: none; }
figcaption { padding: 6px 10px; color: var(--ink-2); font-size: 13px; }
.bar { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; align-items: center; margin: 14px 0; }
button { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 9px 16px; cursor: pointer; }
button.choice { min-width: 170px; font-weight: 600; }
button:hover, button:focus-visible { border-color: var(--accent); outline: none; }
button:disabled { opacity: 0.45; cursor: default; }
kbd { font: 12px ui-monospace, monospace; border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; margin-left: 6px; color: var(--ink-2); }
progress { width: 220px; }
#done { text-align: center; padding: 40px 0; }
#done input { font: inherit; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); }
textarea { width: 100%; height: 160px; margin-top: 16px; font: 12px ui-monospace, monospace; }
@media (max-width: 760px) { .pair { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<main>
  <header>
    <h1>Which attempt is better?</h1>
    <span class="sub" id="count"></span>
  </header>
  <details><summary>The task both attempts were given</summary><pre id="prompt"></pre></details>
  <div id="judging">
    <!-- The attempts' own pages run in frames that may not open windows, leave the page or submit forms. They keep
         their own origin: with it taken away, a 3D page stayed black in one browser this was tried in. -->
    <div class="pair">
      <figure><img id="left" alt="Attempt on the left"><iframe id="left-live" title="Attempt on the left, live" sandbox="allow-scripts allow-same-origin allow-pointer-lock" hidden></iframe><figcaption>Left</figcaption></figure>
      <figure><img id="right" alt="Attempt on the right"><iframe id="right-live" title="Attempt on the right, live" sandbox="allow-scripts allow-same-origin allow-pointer-lock" hidden></iframe><figcaption>Right</figcaption></figure>
    </div>
    <div class="bar">
      <button class="choice" data-answer="left">Left is better<kbd>&larr;</kbd></button>
      <button class="choice" data-answer="tie">About the same<kbd>&darr;</kbd></button>
      <button class="choice" data-answer="right">Right is better<kbd>&rarr;</kbd></button>
    </div>
    <div class="bar">
      <button id="back">Back<kbd>&uarr;</kbd></button>
      <button id="motion">Show still<kbd>space</kbd></button>
      <button id="restart" hidden>Restart both</button>
      <progress id="progress" value="0" max="1"></progress>
    </div>
    <p class="sub" style="text-align:center">Judge the result against the task: how well it meets the brief and how good it looks. You are not told which tool made which.</p>
    <p class="sub" id="live-hint" style="text-align:center" hidden>These are the pages themselves, running: drag, scroll or press keys inside one as the task describes. Move the pointer off the pages before using the arrow keys to answer.</p>
  </div>
  <div id="done" hidden>
    <h1>All pairs judged</h1>
    <p class="sub">Save your picks, then pass the file to the <code>rank</code> command.</p>
    <p><input id="judge" placeholder="Your name" aria-label="Your name"> <button id="save">Save picks</button> <button id="review">Go back</button></p>
    <textarea id="json" readonly aria-label="Picks as JSON"></textarea>
  </div>
</main>
<script>
const DATA = /*DATA*/null;
const $ = (id) => document.getElementById(id);
const storageKey = `picks:${DATA.task_id}:${DATA.pairs_id}`;
let picks = {};
try { picks = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch (error) { picks = {}; }
let index = Math.min(DATA.pairs.findIndex((pair) => !picks[pair.id]) < 0 ? DATA.pairs.length : DATA.pairs.findIndex((pair) => !picks[pair.id]), DATA.pairs.length);
// Three ways to look at a pair: the pages themselves running (where a run's files were kept), the recorded clip, one still.
const live = DATA.live || {};
const canRun = Object.keys(live).length > 0;
let mode = canRun ? 'live' : 'clip', timer = null;
const NEXT = { live: 'clip', clip: 'still', still: canRun ? 'live' : 'clip' };
const OFFER = { live: 'Show live page', clip: canRun ? 'Show recorded clip' : 'Show motion', still: 'Show still' };
for (const side of ['left', 'right']) $(`${side}-live`).style.aspectRatio = `${DATA.aspect[0]} / ${DATA.aspect[1]}`;

function play(image, name) {
  const offsets = DATA.clips[name] || [];
  // The still shows at once; the clip takes over as its frames arrive, so a pane is never empty.
  image.src = `media/${name}/still.png`;
  // In the live view a side with no page to run falls back to its clip.
  if (!(mode === 'clip' || (mode === 'live' && !live[name])) || !offsets.length) return [];
  // Preload every frame, then loop through them at the pace they were recorded.
  return offsets.map((_, frame) => { const preload = new Image(); preload.src = `media/${name}/clip-${String(frame).padStart(3, '0')}.jpg`; return preload; });
}

function show() {
  clearInterval(timer);
  const finished = index >= DATA.pairs.length;
  $('judging').hidden = finished;
  $('done').hidden = !finished;
  $('count').textContent = `${Object.keys(picks).length} of ${DATA.pairs.length} judged`;
  $('progress').value = Object.keys(picks).length / DATA.pairs.length;
  if (finished) { for (const side of ['left', 'right']) $(`${side}-live`).src = 'about:blank'; $('json').value = JSON.stringify(result(), null, 2); return; }
  const pair = DATA.pairs[index];
  $('back').disabled = index === 0;
  $('motion').firstChild.textContent = OFFER[NEXT[mode]];
  $('restart').hidden = $('live-hint').hidden = mode !== 'live';
  // Both pages are loaded at the same moment, so that neither has a head start. A side whose files were not kept shows its clip.
  for (const side of ['left', 'right']) {
    const frame = $(`${side}-live`), running = mode === 'live' && Boolean(live[pair[side]]);
    frame.hidden = !running;
    $(side).hidden = running;
    frame.src = running ? `media/${pair[side]}/${live[pair[side]]}` : 'about:blank';
  }
  for (const button of document.querySelectorAll('.choice')) button.style.borderColor = picks[pair.id] === button.dataset.answer ? 'var(--accent)' : '';
  const reels = [[$('left'), pair.left], [$('right'), pair.right]].map(([image, name]) => ({ image, name, frames: play(image, name) }));
  const started = performance.now();
  if (reels.some((reel) => reel.frames.length)) timer = setInterval(() => {
    for (const reel of reels) {
      const offsets = DATA.clips[reel.name];
      if (!reel.frames.length) continue;
      const length = offsets[offsets.length - 1] + 150, now = (performance.now() - started) % length;
      let frame = 0;
      while (frame + 1 < offsets.length && offsets[frame + 1] <= now) frame += 1;
      if (reel.frames[frame].complete) reel.image.src = reel.frames[frame].src;
    }
  }, 40);
}

function result() {
  return { judge: $('judge').value.trim() || 'person', kind: 'person', task_id: DATA.task_id, pairs_id: DATA.pairs_id,
    picks: DATA.pairs.filter((pair) => picks[pair.id]).map((pair) => ({ pair: pair.id, winner: picks[pair.id] })) };
}
function answer(choice) {
  if (index >= DATA.pairs.length) return;
  picks[DATA.pairs[index].id] = choice;
  try { localStorage.setItem(storageKey, JSON.stringify(picks)); } catch (error) { /* progress just is not kept */ }
  index += 1;
  show();
}
for (const button of document.querySelectorAll('.choice')) button.addEventListener('click', () => answer(button.dataset.answer));
$('back').addEventListener('click', () => { index = Math.max(0, index - 1); show(); });
$('review').addEventListener('click', () => { index = DATA.pairs.length - 1; show(); });
$('motion').addEventListener('click', () => { mode = NEXT[mode]; show(); });
$('restart').addEventListener('click', show);
// Keys pressed while a page has the focus go to that page. Leaving it hands them back, so the arrows answer again.
for (const figure of document.querySelectorAll('figure')) figure.addEventListener('mouseleave', () => {
  if (document.activeElement && document.activeElement.tagName === 'IFRAME') document.activeElement.blur();
});
$('judge').addEventListener('input', () => { $('json').value = JSON.stringify(result(), null, 2); });
$('save').addEventListener('click', () => {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([JSON.stringify(result(), null, 2)], { type: 'application/json' }));
  link.download = `picks-${(result().judge).replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.json`;
  link.click();
});
document.addEventListener('keydown', (event) => {
  if (event.target.tagName === 'INPUT') return;
  const keys = { ArrowLeft: 'left', ArrowRight: 'right', ArrowDown: 'tie' };
  if (keys[event.key]) { event.preventDefault(); answer(keys[event.key]); }
  if (event.key === 'ArrowUp') { event.preventDefault(); $('back').click(); }
  if (event.key === ' ') { event.preventDefault(); $('motion').click(); }
});
$('prompt').textContent = DATA.prompt;
show();
</script>
</body>
</html>
"""
