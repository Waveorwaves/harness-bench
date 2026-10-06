"""Renders a summary as one HTML page (no network, no dependencies).

The page is self-contained except for screenshots of visual tasks, which are copied into a
`media` folder beside it when the run folders are available.
"""

import json
from pathlib import Path
import shutil

from .core import summarize


def render(plan, records, root=None, media=None):
    """The page as a string. `root` adds each run's failed checks; `media` is where screenshots are copied."""
    summary = summarize(plan, records, root)
    for run in summary["runs"]:
        frames = Path(root) / run["folder"] / "capture" if root and media else None
        report = frames / "capture.json" if frames else None
        if not report or not report.is_file():
            continue
        try:
            capture = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not capture.get("frames"):
            continue
        name = Path(run["folder"]).name
        target = Path(media) / name
        target.mkdir(parents=True, exist_ok=True)
        still = capture["frames"][-1].get("compact") or capture["frames"][-1]["file"]
        clip = capture.get("clip") or []
        small = clip[len(clip) // 2]["file"] if clip else still
        shutil.copyfile(frames / still, target / f"still{Path(still).suffix}")
        shutil.copyfile(frames / small, target / f"thumb{Path(small).suffix}")
        run["still"] = f"{Path(media).name}/{name}/still{Path(still).suffix}"
        run["thumb"] = f"{Path(media).name}/{name}/thumb{Path(small).suffix}"
    # No "<" may reach the page inside the data: "</script" would end the script and "<!--" can swallow it.
    data = json.dumps(summary, allow_nan=False).replace("<", "\\u003c")
    return TEMPLATE.replace("/*DATA*/null", data)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness Bench results</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --warning: #fab219;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 0 0 2px; }
p { margin: 0; }
.sub { color: var(--ink-2); }
.note { color: var(--ink-2); font-size: 13px; margin-top: 10px; }
.banner { display: flex; gap: 10px; align-items: flex-start; margin: 16px 0 0; padding: 10px 12px; background: var(--surface);
  border: 1px solid var(--border); border-left: 4px solid var(--warning); border-radius: 6px; }
.filters { display: flex; flex-wrap: wrap; gap: 16px; margin: 20px 0 4px; }
.filters label { color: var(--ink-2); font-size: 13px; display: flex; gap: 6px; align-items: center; }
select { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--axis); border-radius: 6px; padding: 4px 8px; }
section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-top: 16px; }
svg { display: block; width: 100%; height: auto; margin-top: 10px; overflow: visible; }
svg text { fill: var(--ink-2); font-size: 12px; }
svg text.name { fill: var(--ink); font-size: 13px; }
svg text.tick { fill: var(--muted); font-variant-numeric: tabular-nums; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { stroke: var(--axis); stroke-width: 1; }
.interval { stroke-width: 2; stroke-linecap: round; opacity: 0.55; }
.dot { stroke: var(--surface); stroke-width: 2; }
.hit { fill: transparent; cursor: default; outline: none; }
.hit:focus-visible + .dot, .hit:hover + .dot { stroke: var(--ink); }
.legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; font-size: 13px; color: var(--ink-2); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.empty { color: var(--ink-2); padding: 18px 0 6px; }
.scroll { overflow-x: auto; margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th { color: var(--ink-2); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
table.heat td.cell { text-align: center; font-variant-numeric: tabular-nums; border: 2px solid var(--surface); border-radius: 4px; min-width: 48px; padding: 6px 4px; }
table.heat th.task { text-align: center; white-space: normal; max-width: 76px; font-weight: 500; padding: 6px 4px; overflow-wrap: anywhere; }
.runs summary { display: grid; grid-template-columns: 1.3fr 1.2fr 1fr 0.9fr 0.7fr 0.7fr 1fr; gap: 8px; padding: 6px 4px; border-bottom: 1px solid var(--grid);
  font-size: 13px; cursor: pointer; align-items: center; font-variant-numeric: tabular-nums; }
.runs summary::-webkit-details-marker { display: none; }
.runs summary.head { cursor: default; color: var(--ink-2); font-weight: 600; }
.runs .more { padding: 8px 12px 12px; font-size: 13px; color: var(--ink-2); border-bottom: 1px solid var(--grid); }
.runs .more li { margin: 3px 0; }
.runs .more code { font-size: 12px; overflow-wrap: anywhere; }
.state i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.meter { display: inline-block; width: 90px; height: 6px; border-radius: 3px; background: var(--grid); vertical-align: middle; margin-right: 8px; overflow: hidden; }
.meter b { display: block; height: 100%; background: var(--series-1); border-radius: 3px 0 0 3px; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; margin-top: 10px; }
.gallery figure { margin: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--page); }
.gallery img { display: block; width: 100%; height: auto; background: #000; }
.gallery figcaption { padding: 6px 8px; font-size: 12px; color: var(--ink-2); }
.gallery figcaption b { color: var(--ink); font-weight: 600; display: block; }
h3 { font-size: 14px; margin: 16px 0 0; }
#tip { position: fixed; pointer-events: none; z-index: 5; display: none; max-width: 280px; background: var(--surface); color: var(--ink-2);
  border: 1px solid var(--axis); border-radius: 6px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 14px rgba(0,0,0,0.18); }
#tip b { color: var(--ink); display: block; font-size: 15px; }
</style>
</head>
<body>
<main>
  <h1 id="title"></h1>
  <p class="sub" id="status"></p>
  <div class="banner" id="mock" hidden><span aria-hidden="true">&#9888;</span>
    <p><strong>Pipeline test, not a measurement.</strong> Some or all rows come from the built-in fake agent, marked (mock).</p></div>
  <div class="filters">
    <label>Mode <select id="mode"></select></label>
    <label>Model <select id="model"></select></label>
  </div>
  <section>
    <h2>Pass rate</h2>
    <p class="sub">Share of attempted runs that passed every hidden check. Lines show the 95% interval.</p>
    <div id="rates"></div>
  </section>
  <section>
    <h2>Cost against pass rate</h2>
    <p class="sub" id="cost-sub"></p>
    <div id="scatter"></div>
  </section>
  <section>
    <h2>Head to head</h2>
    <p class="sub">Is the gap between two harnesses bigger than rerunning the same tasks would produce? Same model and mode only.</p>
    <p class="sub" id="overall" style="margin-top:8px"></p>
    <div class="scroll" id="pairs"></div>
    <p class="note" id="pairs-note"></p>
  </section>
  <section>
    <h2>By task</h2>
    <p class="sub">Passes out of attempted runs. Darker means more passes.</p>
    <div class="scroll" id="tasks"></div>
  </section>
  <section id="hard-section">
    <h2>What trips them up</h2>
    <p class="sub">The hidden checks failed most often, across every harness in the selection.</p>
    <div class="scroll" id="hard"></div>
  </section>
  <section id="gallery-section" hidden>
    <h2>Gallery</h2>
    <p class="sub">A frame from each attempt at the visual tasks. These carry labels; for ranking, use the blind judging page.</p>
    <div id="gallery"></div>
  </section>
  <section>
    <h2>Runs</h2>
    <p class="sub">Every recorded run in the selection. Open one to see which hidden checks it failed and where its files are.</p>
    <div class="filters" style="margin-top:10px">
      <label>Task <select id="run-task"></select></label>
      <label>Harness <select id="run-harness"></select></label>
      <label>Outcome <select id="run-status"></select></label>
    </div>
    <div class="runs" id="runs"></div>
    <p class="note" id="runs-note"></p>
  </section>
  <section>
    <h2>All numbers</h2>
    <p class="sub">Sorted by pass rate. Configurations whose intervals overlap are not reliably different.</p>
    <div class="scroll" id="table"></div>
    <p class="note">Pass rate leaves out blocked runs, which never fairly started or could not be graded for a reason outside the harness. Ungraded counts runs where the evaluator ran but produced no result; they are counted as failures and deserve a look. Cost per pass is the cost of every attempted run, failures included, divided by the number of passes. Reported cost is what the harness billed through an API. List-price cost is tokens multiplied by the suite's price table: an estimate, not an invoice. Change size is the median number of lines a run touched, as a multiple of what the reference solution touches: well above 1× suggests work beyond what was asked. A dash means the number is unknown.</p>
  </section>
</main>
<div id="tip" role="status"></div>
<script>
const DATA = /*DATA*/null;
const SVG = 'http://www.w3.org/2000/svg';
const RAMP = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'];
const $ = (id) => document.getElementById(id);
const dark = matchMedia('(prefers-color-scheme: dark)');

function el(tag, attributes = {}, text) {
  const node = tag === 'svg' || ['g', 'line', 'circle', 'text', 'rect'].includes(tag)
    ? document.createElementNS(SVG, tag) : document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
const percent = (value) => `${Math.round(value * 100)}%`;
const money = (value) => (value === null ? '–' : `$${value < 0.1 ? value.toFixed(4) : value.toFixed(2)}`);
const whole = (value) => (value === null ? '–' : Math.round(value).toLocaleString('en-US'));
const label = (row) => row.harness + (row.mock ? ' (mock)' : '');
// Three colours exist. With more models only one is shown at a time, and it takes the first.
const colorOf = (model) => `var(--series-${DATA.models.length <= 3 ? DATA.models.indexOf(model) + 1 : 1})`;

const tip = $('tip');
function attachTip(node, heading, lines) {
  const show = (event) => {
    tip.replaceChildren(el('b', {}, heading), ...lines.map((line) => el('div', {}, line)));
    tip.style.display = 'block';
    const box = node.getBoundingClientRect();
    const x = event.clientX ?? box.left + box.width / 2;
    const y = event.clientY ?? box.top;
    tip.style.left = `${Math.min(x + 14, innerWidth - tip.offsetWidth - 8)}px`;
    tip.style.top = `${Math.max(8, y - tip.offsetHeight - 12)}px`;
  };
  const hide = () => { tip.style.display = 'none'; };
  node.addEventListener('pointermove', show);
  node.addEventListener('pointerleave', hide);
  node.addEventListener('focus', show);
  node.addEventListener('blur', hide);
}
function rateLines(row) {
  if (!row.attempted) return ['No attempted runs yet'];
  return [`${row.passed} of ${row.attempted} runs passed`,
    `95% interval ${percent(row.interval[0])} to ${percent(row.interval[1])}`];
}

// Colour is by model, so only three models can share a chart; beyond that, pick one.
const comparable = DATA.models.length <= 3;
for (const mode of DATA.modes) $('mode').append(el('option', { value: mode }, mode));
if (comparable && DATA.models.length > 1) $('model').append(el('option', { value: '' }, 'All models'));
for (const model of DATA.models) $('model').append(el('option', { value: model }, model));

function selected() {
  const model = $('model').value;
  return DATA.rows.filter((row) => row.mode === $('mode').value && (!model || row.model === model));
}

function legend(rows) {
  const models = DATA.models.filter((model) => rows.some((row) => row.model === model));
  const box = el('div', { class: 'legend' });
  if (models.length < 2) return box;
  for (const model of models) {
    const item = el('span');
    item.append(el('i', { style: `background:${colorOf(model)}` }), document.createTextNode(model));
    box.append(item);
  }
  return box;
}

function drawRates(rows) {
  const host = $('rates');
  host.replaceChildren();
  const harnesses = [...new Set(rows.map((row) => row.harness))];
  if (!harnesses.length) return host.append(el('p', { class: 'empty' }, 'No runs planned for this selection.'));
  const perRow = Math.max(...harnesses.map((name) => rows.filter((row) => row.harness === name).length));
  const band = Math.max(34, perRow * 16 + 14);
  const left = 170, right = 24, top = 8, width = 760, plot = width - left - right;
  const height = top + harnesses.length * band + 28;
  const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Pass rate by harness with 95% intervals' });
  const x = (value) => left + value * plot;
  for (const tick of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(el('line', { class: tick ? 'grid' : 'axis', x1: x(tick), x2: x(tick), y1: top, y2: height - 28 }));
    svg.append(el('text', { class: 'tick', x: x(tick), y: height - 10, 'text-anchor': 'middle' }, percent(tick)));
  }
  harnesses.forEach((name, index) => {
    const group = rows.filter((row) => row.harness === name);
    const middle = top + index * band + band / 2;
    svg.append(el('text', { class: 'name', x: left - 12, y: middle + 4, 'text-anchor': 'end' }, label(group[0])));
    group.forEach((row, position) => {
      const y = middle + (position - (group.length - 1) / 2) * 16;
      if (!row.attempted) {
        svg.append(el('text', { x: left + 8, y: y + 4 }, group.length > 1 ? `${row.model}: no attempted runs` : 'no attempted runs'));
        return;
      }
      svg.append(el('line', { class: 'interval', stroke: colorOf(row.model), x1: x(row.interval[0]), x2: x(row.interval[1]), y1: y, y2: y }));
      const hit = el('circle', { class: 'hit', cx: x(row.pass_rate), cy: y, r: 12, tabindex: 0 });
      attachTip(hit, `${percent(row.pass_rate)} · ${label(row)}`, [row.model, ...rateLines(row)]);
      svg.append(hit, el('circle', { class: 'dot', cx: x(row.pass_rate), cy: y, r: 5, fill: colorOf(row.model) }));
    });
  });
  host.append(svg, legend(rows));
}

function niceStep(maximum, count) {
  const raw = maximum / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((step) => step >= raw);
}

function drawScatter(rows) {
  const host = $('scatter');
  host.replaceChildren();
  const attempted = rows.filter((row) => row.attempted);
  // One basis for every point, so configurations stay comparable: whichever covers more of them.
  const bases = [['list_price_usd_per_run', 'list-price estimate'], ['cost_usd_per_run', 'cost reported by the harness']]
    .map(([field, name]) => ({ field, name, points: attempted.filter((row) => row[field] !== null) }))
    .sort((a, b) => b.points.length - a.points.length);
  const { field, name, points } = bases[0];
  const hidden = attempted.length - points.length;
  $('cost-sub').textContent = points.length
    ? `Average cost per attempted run (${name}) against pass rate. Up and to the left is better.`
      + (hidden ? ` ${hidden} configuration${hidden > 1 ? 's are' : ' is'} left out because the cost is unknown.` : '')
    : 'Average cost per attempted run against pass rate.';
  if (!points.length) {
    return host.append(el('p', { class: 'empty' }, 'No cost is known yet. Add a price table to the suite, or run a harness that reports its cost.'));
  }
  const left = 52, right = 24, top = 20, bottom = 44, width = 760, height = 360;
  const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Cost per run against pass rate' });
  const step = niceStep(Math.max(...points.map((row) => row[field])) || 1, 4);
  const maximum = step * Math.ceil((Math.max(...points.map((row) => row[field])) || step) / step);
  const x = (value) => left + (value / maximum) * (width - left - right);
  const y = (value) => top + (1 - value) * (height - top - bottom);
  for (const tick of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(el('line', { class: tick ? 'grid' : 'axis', x1: left, x2: width - right, y1: y(tick), y2: y(tick) }));
    svg.append(el('text', { class: 'tick', x: left - 8, y: y(tick) + 4, 'text-anchor': 'end' }, percent(tick)));
  }
  const decimals = Math.max(2, Math.min(4, Math.ceil(-Math.log10(step)) + 1));
  for (let tick = 0; tick <= maximum + step / 2; tick += step) {
    svg.append(el('text', { class: 'tick', x: x(tick), y: height - bottom + 18, 'text-anchor': 'middle' }, `$${tick.toFixed(decimals)}`));
  }
  svg.append(el('text', { x: (left + width - right) / 2, y: height - 6, 'text-anchor': 'middle' }, 'Average cost per attempted run (USD)'));
  // Place each name beside its dot where it collides with nothing; a name with no free spot
  // is left to the legend, tooltip and table rather than stacked on top of another.
  const taken = points.map((row) => ({ x0: x(row[field]) - 8, x1: x(row[field]) + 8, y0: y(row.pass_rate) - 8, y1: y(row.pass_rate) + 8 }));
  const free = (box) => box.x0 >= left && box.x1 <= width - 4 && box.y0 >= 0
    && taken.every((other) => box.x1 < other.x0 || box.x0 > other.x1 || box.y1 < other.y0 || box.y0 > other.y1);
  function placeName(row) {
    const text = label(row), wide = text.length * 7 + 4, cx = x(row[field]), cy = y(row.pass_rate);
    const spots = [[cx + 11, cy + 4, 'start'], [cx - 11, cy + 4, 'end'], [cx, cy - 12, 'middle'], [cx, cy + 22, 'middle']];
    for (const [tx, ty, anchor] of spots) {
      const x0 = anchor === 'start' ? tx : anchor === 'end' ? tx - wide : tx - wide / 2;
      const box = { x0, x1: x0 + wide, y0: ty - 12, y1: ty + 4 };
      if (free(box)) {
        taken.push(box);
        return el('text', { class: 'name', x: tx, y: ty, 'text-anchor': anchor }, text);
      }
    }
    return null;
  }
  for (const row of points) {
    const hit = el('circle', { class: 'hit', cx: x(row[field]), cy: y(row.pass_rate), r: 14, tabindex: 0 });
    attachTip(hit, `${percent(row.pass_rate)} at ${money(row[field])} per run`, [`${label(row)} · ${row.model}`, ...rateLines(row),
      row[field.replace('_per_run', '_per_pass')] === null ? 'No passes, so no cost per pass'
        : `${money(row[field.replace('_per_run', '_per_pass')])} per pass`]);
    svg.append(hit, el('circle', { class: 'dot', cx: x(row[field]), cy: y(row.pass_rate), r: 6, fill: colorOf(row.model) }));
  }
  for (const row of points) {
    const name = placeName(row);
    if (name) svg.append(name);
  }
  host.append(svg, legend(points));
}

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255)
    .map((channel) => (channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function drawTasks(rows) {
  const host = $('tasks');
  host.replaceChildren();
  const table = el('table', { class: 'heat' });
  const head = el('tr');
  head.append(el('th', {}, 'Harness'), el('th', {}, 'Model'));
  for (const task of DATA.tasks) head.append(el('th', { class: 'task' }, task));
  table.append(head);
  // On a dark surface the low end must be the dark one, so that "few passes" still recedes.
  const ramp = dark.matches ? [...RAMP].reverse().slice(0, 11) : RAMP.slice(0, 12);
  for (const row of rows) {
    const line = el('tr');
    line.append(el('td', {}, label(row)), el('td', {}, row.model));
    for (const task of DATA.tasks) {
      const cell = row.tasks[task];
      if (!cell || !cell.attempted) {
        line.append(el('td', { class: 'cell' }, '–'));
        continue;
      }
      const shade = ramp[Math.round((cell.passed / cell.attempted) * (ramp.length - 1))];
      const node = el('td', { class: 'cell', tabindex: 0,
        style: `background:${shade};color:${luminance(shade) > 0.32 ? '#0b0b0b' : '#ffffff'}` }, `${cell.passed}/${cell.attempted}`);
      attachTip(node, `${cell.passed} of ${cell.attempted} passed`, [task, `${label(row)} · ${row.model}`]);
      line.append(node);
    }
    table.append(line);
  }
  host.append(table);
}

function drawTable(rows) {
  const host = $('table');
  host.replaceChildren();
  const columns = [
    ['Harness', (row) => label(row)], ['Model', (row) => row.model],
    ['Pass rate', (row) => (row.attempted ? percent(row.pass_rate) : '–'), true],
    ['95% interval', (row) => (row.attempted ? `${percent(row.interval[0])}–${percent(row.interval[1])}` : '–'), true],
    ['Passed', (row) => `${row.passed}/${row.attempted}`, true],
    ['Blocked', (row) => row.blocked, true], ['Pending', (row) => row.pending, true],
    ['Ungraded', (row) => row.evaluator_errors, true],
    ['Change size', (row) => (row.change_ratio === null ? '–' : `${row.change_ratio.toFixed(1)}×`), true],
    ['Median seconds', (row) => (row.seconds === null ? '–' : row.seconds.toFixed(1)), true],
    ['Tokens in', (row) => whole(row.input_tokens), true], ['Cached', (row) => whole(row.cached_input_tokens), true],
    ['Out', (row) => whole(row.output_tokens), true],
    ['Reported $ per pass', (row) => money(row.cost_usd_per_pass), true],
    ['List-price $ per pass', (row) => money(row.list_price_usd_per_pass), true],
  ];
  const table = el('table');
  const head = el('tr');
  for (const [name, , numeric] of columns) head.append(el('th', numeric ? { class: 'num' } : {}, name));
  table.append(head);
  const sorted = [...rows].sort((a, b) => (b.pass_rate ?? -1) - (a.pass_rate ?? -1)
    || (a.list_price_usd_per_run ?? Infinity) - (b.list_price_usd_per_run ?? Infinity));
  for (const row of sorted) {
    const line = el('tr');
    for (const [, value, numeric] of columns) line.append(el('td', numeric ? { class: 'num' } : {}, String(value(row))));
    table.append(line);
  }
  host.append(table);
}

function drawPairs() {
  const host = $('pairs');
  host.replaceChildren();
  const model = $('model').value;
  const pairs = DATA.comparisons.filter((item) => item.mode === $('mode').value && (!model || item.model === model))
    .sort((a, b) => b.clear - a.clear || b.difference - a.difference);
  $('pairs-note').textContent = pairs.length
    ? `The plausible range (95%) allows for run-to-run noise on these tasks, with tasks counted equally. It is cautious: with few repeats it sits closer to zero than the observed gap, because a task passed three times out of three may still fail the fourth. It says nothing about other tasks. ${pairs.length} pairs are shown without correction; for two identical harnesses, fewer than 1 in 20 would be called "clear" by chance.`
    : '';
  if (!pairs.length) return host.append(el('p', { class: 'empty' }, 'Nothing to compare yet: two harnesses need attempted runs on the same task.'));
  const points = (value) => `${value >= 0 ? '+' : '−'}${Math.abs(Math.round(value * 100))}`;
  const table = el('table');
  const head = el('tr');
  for (const [name, numeric] of [['Better', 0], ['Worse', 0], ['Model', 0], ['Observed gap', 1], ['Plausible range', 1], ['Verdict', 0]]) {
    head.append(el('th', numeric ? { class: 'num' } : {}, name));
  }
  table.append(head);
  const names = Object.fromEntries(DATA.rows.map((row) => [row.harness, label(row)]));
  for (const item of pairs) {
    const line = el('tr');
    line.append(el('td', {}, names[item.better]), el('td', {}, names[item.worse]), el('td', {}, item.model),
      el('td', { class: 'num' }, `${points(item.difference)} pts`),
      el('td', { class: 'num' }, `${points(item.low)} to ${points(item.high)} pts`),
      el('td', {}, item.clear ? '● Clear' : '○ Within noise'));
    table.append(line);
  }
  host.append(table);
}

function drawOverall() {
  const model = $('model').value;
  const tests = DATA.overall.filter((item) => item.mode === $('mode').value && (!model || item.model === model));
  $('overall').textContent = tests.map((item) => {
    const p = item.p_value < 0.001 ? 'under 0.001' : item.p_value.toFixed(3);
    return `${item.model}: best and worst harness are ${Math.round(item.spread * 100)} points apart; a spread this large would arise with no real difference with probability ${p} (permutation test over ${item.harnesses} harnesses).`;
  }).join(' ');
}

const STATES = { passed: ['Passed', '#0ca30c'], failed: ['Failed', '#d03b3b'], timed_out: ['Timed out', '#fab219'], blocked: ['Blocked', '#898781'] };
function state(status) {
  const box = el('span', { class: 'state' });
  box.append(el('i', { style: `background:${STATES[status][1]}` }), document.createTextNode(STATES[status][0]));
  return box;
}
function inSelection(run) {
  const model = $('model').value;
  return run.mode === $('mode').value && (!model || run.model === model);
}

function drawHard() {
  const host = $('hard');
  host.replaceChildren();
  const graded = DATA.runs.filter((run) => inSelection(run) && run.failed !== null);
  const rows = DATA.checks.map((check) => {
    const runs = graded.filter((run) => run.task === check.task);
    const failed = runs.filter((run) => run.failed.some((item) => item.name === check.name)).length;
    return { ...check, runs: runs.length, passed: runs.length - failed };
  }).filter((check) => check.runs && check.passed < check.runs)
    .sort((a, b) => a.passed / a.runs - b.passed / b.runs).slice(0, 12);
  $('hard-section').hidden = !DATA.checks.length;
  if (!rows.length) return host.append(el('p', { class: 'empty' }, graded.length ? 'Every check passed in every run.' : 'No graded runs in this selection yet.'));
  const table = el('table');
  const head = el('tr');
  head.append(el('th', {}, 'Task'), el('th', {}, 'Hidden check'), el('th', {}, 'Runs that passed it'));
  table.append(head);
  for (const row of rows) {
    const line = el('tr');
    const meter = el('span', { class: 'meter' });
    meter.append(el('b', { style: `width:${(row.passed / row.runs) * 100}%` }));
    const share = el('td');
    share.append(meter, document.createTextNode(`${row.passed} of ${row.runs}`));
    line.append(el('td', {}, row.task), el('td', { style: 'white-space:normal' }, row.name), share);
    table.append(line);
  }
  host.append(table);
}

function drawGallery() {
  const host = $('gallery');
  host.replaceChildren();
  const shots = DATA.runs.filter((run) => inSelection(run) && run.thumb);
  $('gallery-section').hidden = !shots.length;
  for (const task of DATA.tasks) {
    const mine = shots.filter((run) => run.task === task);
    if (!mine.length) continue;
    host.append(el('h3', {}, task));
    const grid = el('div', { class: 'gallery' });
    for (const run of mine) {
      const figure = el('figure');
      const link = el('a', { href: run.still, target: '_blank', rel: 'noopener' });
      link.append(el('img', { src: run.thumb, loading: 'lazy', alt: `${run.harness}, ${run.model}, repeat ${run.repetition}` }));
      const caption = el('figcaption');
      caption.append(el('b', {}, `${run.harness} · ${run.model}`), document.createTextNode(`Repeat ${run.repetition} · ${STATES[run.status][0]} · ${run.checks_passed}/${run.checks_total} checks`));
      figure.append(link, caption);
      grid.append(figure);
    }
    host.append(grid);
  }
}

function options(select, values, all) {
  const current = select.value;
  select.replaceChildren(el('option', { value: '' }, all), ...values.map((value) => el('option', { value }, STATES[value] ? STATES[value][0] : value)));
  if (values.includes(current)) select.value = current;
}
function drawRuns() {
  const host = $('runs');
  host.replaceChildren();
  const scope = DATA.runs.filter(inSelection);
  options($('run-task'), DATA.tasks.filter((task) => scope.some((run) => run.task === task)), 'All tasks');
  options($('run-harness'), [...new Set(scope.map((run) => run.harness))], 'All harnesses');
  options($('run-status'), Object.keys(STATES).filter((status) => scope.some((run) => run.status === status)), 'All outcomes');
  const runs = scope.filter((run) => (!$('run-task').value || run.task === $('run-task').value)
    && (!$('run-harness').value || run.harness === $('run-harness').value)
    && (!$('run-status').value || run.status === $('run-status').value));
  const head = el('summary', { class: 'head' });
  for (const name of ['Task', 'Harness', 'Model', 'Outcome', 'Checks', 'Seconds', 'Tokens in / out']) head.append(el('span', {}, name));
  const first = el('details');
  first.append(head);
  first.addEventListener('click', (event) => event.preventDefault());
  host.append(first);
  const LIMIT = 300;
  for (const run of runs.slice(0, LIMIT)) {
    const item = el('details');
    const line = el('summary');
    line.append(el('span', {}, `${run.task} #${run.repetition}`), el('span', {}, run.harness), el('span', {}, run.model), state(run.status),
      el('span', {}, run.status === 'blocked' ? '–' : `${run.checks_passed}/${run.checks_total}`),
      el('span', {}, run.elapsed_seconds === null ? '–' : run.elapsed_seconds.toFixed(1)),
      el('span', {}, `${whole(run.input_tokens)} / ${whole(run.output_tokens)}`));
    const more = el('div', { class: 'more' });
    if (run.reason) more.append(el('p', {}, run.reason));
    if (run.failed && run.failed.length) {
      more.append(el('p', {}, 'Failed checks:'));
      const list = el('ul');
      for (const check of run.failed) {
        const entry = el('li', {}, check.name);
        if (check.detail) entry.append(document.createTextNode(': '), el('code', {}, check.detail));
        list.append(entry);
      }
      more.append(list);
    } else if (run.failed) more.append(el('p', {}, 'Every hidden check passed.'));
    const facts = [['Changed', run.files_changed === null ? null : `${run.files_changed} files, +${run.lines_added} −${run.lines_removed} lines` + (run.change_ratio === null ? '' : ` (${run.change_ratio.toFixed(1)}× the reference solution)`)],
      ['Turns', run.turns], ['Tool calls', run.tool_calls], ['Subagents started', run.subagents],
      ['Cached input tokens', run.cached_input_tokens === null ? null : whole(run.cached_input_tokens)],
      ['Reported cost', run.cost_usd === null ? null : money(run.cost_usd)], ['List-price cost', run.list_price_usd === null ? null : money(run.list_price_usd)],
      ['Exit code', run.exit_code]].filter(([, value]) => value !== null && value !== undefined);
    more.append(el('p', {}, facts.map(([name, value]) => `${name}: ${value}`).join(' · ')));
    const where = el('p', {}, 'Files: ');
    where.append(el('code', {}, run.folder));
    more.append(where);
    item.append(line, more);
    host.append(item);
  }
  $('runs-note').textContent = runs.length > LIMIT ? `Showing the first ${LIMIT} of ${runs.length} runs. Narrow the selection to see the rest.` : `${runs.length} run${runs.length === 1 ? '' : 's'}.`;
}

function draw() {
  const rows = selected();
  drawOverall();
  drawHard();
  drawGallery();
  drawRuns();
  drawPairs();
  drawRates(rows);
  drawScatter(rows);
  drawTasks(rows);
  drawTable(rows);
}

$('title').textContent = DATA.suite_id;
$('status').textContent = `${DATA.recorded} of ${DATA.planned} runs recorded · ${DATA.repetitions} repeat${DATA.repetitions > 1 ? 's' : ''} per task and configuration · plan ${DATA.plan_id.slice(0, 12)}`;
$('mock').hidden = !DATA.has_mock;
for (const id of ['run-task', 'run-harness', 'run-status']) $(id).addEventListener('change', drawRuns);
$('mode').addEventListener('change', draw);
$('model').addEventListener('change', draw);
dark.addEventListener('change', draw);
draw();
</script>
</body>
</html>
"""
