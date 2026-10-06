# The visual track

Hidden tests separate weaker configurations well. Strong models pass most of them, and what then differs is the quality of open-ended output: how a scene looks and moves. The visual track measures that with people's eyes, kept honest by blinding and by statistics.

## What happens to a visual task

1. **Capture.** After the agent exits, the page is opened in a headless Chromium inside the no-network sandbox. The helper records stills, a short clip of small frames, every request the page made, uncaught errors, the frame rate and the value of a task-specific probe.
2. **Automatic checks.** The task's evaluator reads that report. It checks only what can be measured: one file, no outside requests, no console errors, a canvas filling the window, a picture that is not blank and that moves. These give the run its pass or fail.
3. **Blind judging.** `judge-prepare` copies each attempt's still and clip into a folder under opaque names and writes a page showing two attempts side by side. The judge picks left, right or about the same.
4. **Ranking.** `rank` turns picks into a rating per harness, model and mode with intervals, and reports how far judges agree.

The same capture step also serves scored tasks that are pages. A task can name a hidden script of interaction steps (`click`, `dblclick`, `type`, `press`, `reload`, `eval`); they are carried out with real input events, and the evaluator reads what was observed after each one. `todo-app` and `tabs-keyboard` are graded this way, with no person involved.

## Commands

```sh
# after `run` has finished for a plan that includes a visual task
python3 -m harness_bench judge-prepare --plan runs/<plan>/plan.json --task pirate-ship-3d
open runs/<plan>/judging/pirate-ship-3d/index.html        # judge with the arrow keys, then Save picks

# optional: a model answers the same pairs (each pair is asked twice, sides swapped)
python3 -m harness_bench judge-model --folder runs/<plan>/judging/pirate-ship-3d \
  --command 'claude -p {prompt} --model haiku --allowedTools Read' --label claude-haiku --output picks-haiku.json

python3 -m harness_bench rank --folder runs/<plan>/judging/pirate-ship-3d --picks picks-you.json picks-haiku.json
```

The judging folder holds only the page and media under random names, so it can be zipped and sent to a judge as it is. The key that says which attempt is which is written beside it, as `<task>.key.json`. Picks are tied to one exact set of pairs. `judge-prepare` refuses to overwrite a folder it has already written unless given `--replace`, and after a replace earlier picks are rejected rather than silently matched to different pairs.

A model judge is shown each pair in an empty folder containing only `left.png` and `right.png`, so it cannot find the key or the run folders.

## Judging well

- Judge at least every pair once. With eight configurations and three repeats that is 84 pairs, about ten minutes.
- Watch the clip, not only the still (space toggles). Motion is part of the brief.
- Ask a second person if you can. One judge's ranking is one person's taste.
- Trust a model judge on a task only after it agrees with people there. Look at Cohen's kappa, not only the percentage: two judges who both pick "left" most of the time agree often by chance.
- If a model judge changes its answer when the sides are swapped on many pairs, its picks are mostly noise for this task.

## Limits

- Stills and clips come from software rendering at 1280×800. A scene that needs a GPU to look right is at a disadvantage.
- The clip is about 20 frames over a few seconds at half size. It shows that things move and roughly how, not smoothness.
- Interaction (orbiting the camera, for example) is asked for in the brief but is not exercised by the capture.
