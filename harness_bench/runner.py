"""Executes planned runs: fresh workspace, sandboxed agent, separate hidden evaluation."""

from collections import Counter
import copy
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

from . import adapters, tasks
from .adapters import Launch
from .core import require, validate_plan
from .sandbox import shielded

MOCK_DIRECTORY = Path(__file__).parent / "mock"
CAPTURE_DIRECTORY = Path(__file__).parent / "capture"

# The agent's own repository is set aside under this name once the run is over, so that no
# later git command in the kept workspace (a shell prompt, an editor) obeys settings it wrote.
AGENT_GIT = ".git-as-left-by-agent"

# A run that ends in an error this quickly, having changed nothing, never really started (a
# missing login, a bad flag). Anything longer counts as an attempt. The rule deliberately
# ignores token counts, which only some harnesses report, so that all are treated alike.
NEVER_STARTED_SECONDS = 20

# Folders left out of the change size and of copies.
SKIPPED_FOLDERS = {".git", AGENT_GIT, "node_modules", ".venv", "__pycache__"}

# Files beyond this size are not copied, archived or compared line by line.
LARGEST_FILE = 50 * 1024 * 1024


def run_directory(base, run):
    """Where a run's files live. Ids cannot contain a dot, so the name is unique."""
    return base / run["run_id"].split(":", 1)[1].replace(":", ".")


def remove_tree(path):
    """Delete a directory whatever an agent left in it: read-only entries, unreadable ones, paths too long to name.

    The system tools are used because they work down the tree by relative steps, which copes
    with paths longer than the operating system lets a program spell out.
    """
    path = Path(path)
    if not path.is_symlink() and not path.exists():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    subprocess.run(["chmod", "-R", "u+rwX", str(path)], capture_output=True)
    subprocess.run(["rm", "-rf", str(path)], capture_output=True)
    if path.exists():
        shutil.rmtree(path)  # raises with the reason if it truly cannot be removed


def copy_tree(source, target):
    """Copy files, directories and links, skipping git metadata and anything that is none of those.

    An agent can leave pipes, sockets, unreadable files, enormous files or paths too long to
    open; none of them may stop the run. Links are copied as links and never followed.
    """
    for folder, directories, files in os.walk(source):
        relative = Path(folder).relative_to(source)
        try:
            (target / relative).mkdir(parents=True, exist_ok=True)
        except OSError:
            directories[:] = []
            continue
        for name in list(directories):
            path = Path(folder) / name
            try:
                if name.lower() in (".git", AGENT_GIT):
                    directories.remove(name)
                elif path.is_symlink():
                    directories.remove(name)
                    os.symlink(os.readlink(path), target / relative / name)
            except OSError:
                directories.remove(name)
        for name in files:
            path = Path(folder) / name
            try:
                if path.is_symlink():
                    os.symlink(os.readlink(path), target / relative / name)
                elif path.is_file() and path.stat().st_size <= LARGEST_FILE:
                    shutil.copyfile(path, target / relative / name)
            except OSError:
                continue


def archive_workspace(workspace, archive):
    """Pack the agent's files into one archive and remove the live folder.

    A folder an agent wrote can act on whoever opens it: git settings, editor tasks, shell
    hooks. An archive cannot. Unpack it somewhere deliberate to look inside.
    Returns the names left out because they were too large.
    """
    skipped = []
    subprocess.run(["chmod", "-R", "u+rwX", str(workspace)], capture_output=True)

    def keep(entry):
        if entry.isreg() and entry.size > LARGEST_FILE:
            skipped.append(entry.name)
            return None
        return entry

    try:
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(workspace, arcname="workspace", filter=keep)
    except (OSError, tarfile.TarError, ValueError) as error:
        skipped.append(f"(archive incomplete: {type(error).__name__}: {error})"[:200])
    remove_tree(workspace)
    return skipped


def version_of(adapter, sandbox, scratch):
    """Ask the harness for its version inside the sandbox it will run in."""
    scratch.mkdir(parents=True, exist_ok=True)
    outcome = sandbox.run(list(adapter.version), mounts={"work": (scratch, True)}, cwd="work",
                          timeout=60, stdout=scratch / "version.out", stderr=scratch / "version.err")
    lines = (scratch / "version.out").read_text(errors="replace").strip().splitlines()
    if outcome.launch_error or outcome.timed_out or outcome.exit_code != 0 or not lines:
        return None
    return lines[0].strip()


def pin(suite, root, sandbox):
    """Fill in task revisions from disk and harness versions from the sandbox."""
    pinned = copy.deepcopy(suite)
    for entry in pinned["tasks"]:
        task = tasks.load(root, entry)
        entry.update(seed_revision=task.seed_revision, evaluator_revision=task.evaluator_revision)
    with tempfile.TemporaryDirectory() as scratch:
        for entry in pinned["harnesses"]:
            adapter = adapters.get(entry["adapter"])
            if adapter.id == "manual":
                entry["version"] = entry.get("version") or "desktop app, version not recorded"
                continue
            entry["version"] = version_of(adapter, sandbox, Path(scratch) / entry["id"])
    return pinned


def evaluate(task, workspace, directory, sandbox):
    """Run the hidden evaluator on a copy of the workspace, with no network.

    Returns (checks passed, checks total, error, setup_fault). setup_fault is True when the
    evaluation machinery itself could not run, which must not be held against the candidate.
    """
    space, out = directory / "evalspace", directory / "evaluation"
    copy_tree(workspace, space)
    out.mkdir()
    mounts = {"work": (space, True), "eval": (task.evaluator, False), "out": (out, True)}
    try:
        if task.capture:
            # Screenshot the page first, in the same no-network sandbox, so the evaluator can read the frames.
            frames = directory / "capture"
            frames.mkdir()
            shots = {"work": (space, True), "capture": (frames, True), "tool": (CAPTURE_DIRECTORY, False),
                     "eval": (task.evaluator, False)}
            settings = task.capture
            clip = settings["clip"]
            inside = _paths(sandbox, shots)
            shot = sandbox.run(["python3", "-B", f"{inside['tool']}/capture.py", "--path", settings["path"],
                                "--width", str(settings["width"]), "--height", str(settings["height"]),
                                "--times", ",".join(map(str, settings["times_ms"])),
                                *(["--probe", settings["probe"]] if settings["probe"] else []),
                                *(["--script", f"{inside['eval']}/{settings['script']}"] if settings["script"] else []),
                                *(["--clip-ms", str(clip["duration_ms"]), "--clip-frames", str(clip["frames"]),
                                   "--clip-scale", str(clip["scale"]), "--clip-quality", str(clip["quality"])] if clip else [])],
                               mounts=shots, cwd="work", network=False,
                               timeout=90 + (max(settings["times_ms"]) + (clip["duration_ms"] if clip else 0)) // 1000,
                               stdout=directory / "capture.stdout", stderr=directory / "capture.stderr")
            if shot.launch_error:
                return 0, 0, f"the capture step could not start: {shot.launch_error}", True
            report = frames / "capture.json"
            if report.is_file() and json.loads(report.read_text()).get("infrastructure"):
                return 0, 0, f"the capture step could not run: {json.loads(report.read_text()).get('error')}", True
            mounts["capture"] = (frames, False)
        outcome = sandbox.run(["sh", "-c", task.command], mounts=mounts, cwd="work", network=False,
                              timeout=task.timeout, stdout=directory / "evaluator.stdout",
                              stderr=directory / "evaluator.stderr")
    finally:
        remove_tree(space)
    if outcome.launch_error:
        return 0, 0, f"the evaluator could not start: {outcome.launch_error}", True
    # From here on a missing result may be the candidate's doing (an endless loop, a killed process).
    if outcome.timed_out:
        return 0, 0, "evaluator timed out", False
    try:
        checks = json.loads((out / "result.json").read_text(encoding="utf-8"))["checks"]
        verdicts = [check["passed"] for check in checks]
        require(checks and all(type(v) is bool for v in verdicts), "checks must carry boolean verdicts")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return 0, 0, f"evaluator produced no usable result: {error}", False
    return sum(verdicts), len(verdicts), None, False


def validate_task(root, entry, sandbox):
    """A task is usable only if its seed fails and its reference passes."""
    task = tasks.load(root, entry)
    require(task.reference, f"task {task.id}: add reference/ to prove the evaluator can pass")
    verdicts = {}
    with tempfile.TemporaryDirectory() as scratch:
        for label in ("seed", "reference"):
            directory = Path(scratch) / label
            workspace = directory / "workspace"
            shutil.copytree(task.seed, workspace)
            if label == "reference":
                shutil.copytree(task.reference, workspace, dirs_exist_ok=True)
            verdicts[label] = evaluate(task, workspace, directory, sandbox)
    for label, (passed, total, error, _) in verdicts.items():
        require(not error, f"task {task.id}: {label}: {error}")
    require(verdicts["seed"][0] < verdicts["seed"][1], f"task {task.id}: the untouched seed already passes")
    require(verdicts["reference"][0] == verdicts["reference"][1],
            f"task {task.id}: reference passes only {verdicts['reference'][0]}/{verdicts['reference'][1]} checks")
    return {label: f"{passed}/{total}" for label, (passed, total, _, _) in verdicts.items()}


def grade(root, task_directory, workspace, sandbox, output=None):
    """Grade any folder against a task: for work produced outside the runner, by hand or by a hosted agent.

    Returns (checks, error). With `output`, the evaluation files (and screenshots) are kept there.
    """
    task_directory = Path(task_directory)
    task = tasks.load(root, {"id": task_directory.name, "spec": str(task_directory)})
    require(Path(workspace).is_dir(), f"{workspace} is not a folder")
    if output:
        here, there = Path(workspace).resolve(), Path(output).resolve()
        require(here != there and here not in there.parents and there not in here.parents,
                "--output must not be inside the workspace, or the other way round")
    with tempfile.TemporaryDirectory() as scratch:
        directory = Path(output) if output else Path(scratch) / "grading"
        require(not directory.exists() or not any(directory.iterdir()), f"{directory} is not empty")
        directory.mkdir(parents=True, exist_ok=True)
        passed, total, error, _ = evaluate(task, Path(workspace), directory, sandbox)
        result = directory / "evaluation" / "result.json"
        checks = json.loads(result.read_text(encoding="utf-8"))["checks"] if result.is_file() and not error else []
    return checks, error


def seed_repository(workspace):
    """Give the agent an ordinary git repository holding the seed, untouched by this machine's git settings."""
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    for arguments in (["init", "-q", "--template="], ["add", "-A"], ["commit", "-q", "--allow-empty", "-m", "Initial commit"]):
        subprocess.run(["git", "-c", "user.name=dev", "-c", "user.email=dev@localhost", "-c", "commit.gpgsign=false",
                        "-c", "core.hooksPath=/dev/null", *arguments],
                       cwd=workspace, env=environment, check=True, capture_output=True)


def set_aside_repositories(workspace):
    """Rename every .git the run left, so git no longer treats the folder around it as a repository."""
    for folder, directories, files in os.walk(workspace):
        for name in [n for n in directories + files if n.lower() == ".git"]:
            try:
                target, attempt = Path(folder) / AGENT_GIT, 0
                while target.exists() or target.is_symlink():
                    attempt += 1
                    target = Path(folder) / f"{AGENT_GIT}-{attempt}"
                os.replace(Path(folder) / name, target)
            except OSError:
                continue
        directories[:] = [name for name in directories if not name.lower().startswith(".git")]


def tree_files(root):
    """Relative name -> path for every file and link under root, outside the skipped folders."""
    found = {}
    for folder, directories, names in os.walk(root):
        for name in list(directories):
            try:
                linked = (Path(folder) / name).is_symlink()
            except OSError:
                linked = False
            if name.lower() in SKIPPED_FOLDERS or name.lower().startswith(AGENT_GIT):
                directories.remove(name)
            elif linked:
                directories.remove(name)
                names.append(name)
        for name in names:
            path = Path(folder) / name
            try:
                listed = path.is_symlink() or path.is_file()
            except OSError:
                listed = True  # it is there, even if it cannot be examined
            if listed:
                found[path.relative_to(root).as_posix()] = path
    return found


def text_lines(path):
    """A file's lines, or None if it is binary, very large or cannot be read. A link reads as where it points.

    Each line keeps its own ending, so a change of line endings or of the final newline shows.
    """
    try:
        if path.is_symlink():
            return [f"link to {os.readlink(path)}\n"]
        if path.stat().st_size > LARGEST_FILE:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return re.findall(r"[^\n]*\n|[^\n]+", data.decode("utf-8", errors="replace"))


def same_content(first, second):
    """Whether two files hold the same bytes, read in pieces so that size does not matter."""
    try:
        if first.stat().st_size != second.stat().st_size:
            return False
        with open(first, "rb") as one, open(second, "rb") as other:
            while True:
                piece = one.read(1 << 20)
                if piece != other.read(1 << 20):
                    return False
                if not piece:
                    return True
    except OSError:
        return False


def change_stats(seed, workspace, patch):
    """Files changed and lines added and removed against the seed, written out as a readable patch.

    The two trees are compared directly, file by file. Nothing here consults git, so neither an
    ignore file, an attribute file, a nested repository nor this machine's git settings can
    hide or distort a change.
    """
    before, after = tree_files(seed), tree_files(workspace)
    files = added = removed = 0
    pieces = []
    for name in sorted(set(before) | set(after)):
        old = text_lines(before[name]) if name in before else []
        new = text_lines(after[name]) if name in after else []
        if old is None or new is None:
            if not (name in before and name in after and same_content(before[name], after[name])):
                files += 1
                pieces.append(f"Binary, very large or unreadable file differs: {name}\n")
            continue
        if old == new:
            continue
        files += 1
        if len(old) + len(new) > 20000:
            # Too long to line up; count lines that appear in one version and not the other.
            plus, minus = Counter(new) - Counter(old), Counter(old) - Counter(new)
            added += sum(plus.values())
            removed += sum(minus.values())
            pieces.append(f"Large file differs (not shown line by line): {name}\n")
            continue
        difference = list(difflib.unified_diff(old, new, f"a/{name}", f"b/{name}"))
        body = difference[2:]  # after the two header lines; a changed line may itself begin with ++ or --
        added += sum(line.startswith("+") for line in body)
        removed += sum(line.startswith("-") for line in body)
        pieces.append("".join(line if line.endswith("\n") else line + "\n" for line in difference))
    patch.write_text("".join(pieces), encoding="utf-8", errors="backslashreplace")
    return files, added, removed


def list_price(usage, prices):
    """Tokens multiplied by the suite's price table; None unless every priced part is known."""
    if not prices:
        return None
    cost = 0.0
    for tokens, price in (("input_tokens", "input"), ("cached_input_tokens", "cached_input"),
                          ("cache_write_tokens", "cache_write"), ("output_tokens", "output")):
        amount = usage.get(tokens)
        if amount is None:
            # Unknown is not zero. It only stops the estimate where the table says this kind is charged.
            if price in prices or price in ("input", "output"):
                return None
            continue
        if amount:
            if price not in prices:
                return None
            cost += amount * prices[price] / 1_000_000
    return round(cost, 6)


def resolve_environment(settings):
    """`NAME` passes a variable through from this shell; `NAME=value` sets a literal."""
    environment, absent = {}, []
    for setting in settings:
        name, separator, value = setting.partition("=")
        if separator:
            environment[name] = value
        elif name in os.environ:
            environment[name] = os.environ[name]
        else:
            absent.append(name)
    return environment, absent


def preflight(suite, root, sandbox):
    """Everything that can be checked without calling a model. Returns (lines, problem count)."""
    lines, problems = [], 0

    def note(ok, text):
        nonlocal problems
        problems += not ok
        lines.append(f"{'ok  ' if ok else 'FAIL'} {text}")

    if sandbox.name == "docker":
        daemon = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
        note(daemon, "docker daemon is running")
        image = daemon and subprocess.run(["docker", "image", "inspect", sandbox.image],
                                          capture_output=True).returncode == 0
        note(image, f"image {sandbox.image} exists")
        if not image:
            return lines + ["     (harness versions not checked without the image)"], problems
    for entry in suite["tasks"]:
        try:
            verdict = validate_task(root, entry, sandbox)
            task = tasks.load(root, entry)
            pins = (entry.get("seed_revision"), entry.get("evaluator_revision"))
            current = pins in ((None, None), (task.seed_revision, task.evaluator_revision))
            note(current, f"task {entry['id']}: seed {verdict['seed']}, reference {verdict['reference']}"
                 + ("" if current else "; files changed since pinning"))
        except (ValueError, OSError) as error:
            note(False, str(error))
    with tempfile.TemporaryDirectory() as scratch:
        for entry in suite["harnesses"]:
            try:
                adapter = adapters.get(entry["adapter"])
            except ValueError as error:
                note(False, f"harness {entry['id']}: {error}")
                continue
            if adapter.id == "manual":
                lines.append(f"ok   harness {entry['id']}: run by hand (manual-start, then manual-finish)")
                continue
            version = version_of(adapter, sandbox, Path(scratch) / entry["id"])
            pinned = entry.get("version")
            note(bool(version) and pinned in (None, version),
                 f"harness {entry['id']}: " + (f"version {version}" if version else "not found in the sandbox")
                 + (f" (pinned {pinned})" if version and pinned not in (None, version) else ""))
            settings = list(entry.get("env", []))
            for model in suite.get("models", []):
                settings += model.get("harness_env", {}).get(entry["id"], [])
            absent = sorted(set(resolve_environment(settings)[1]))
            if settings:
                note(not absent, f"harness {entry['id']}: environment "
                     + (f"missing {', '.join(absent)}" if absent else "set"))
            for item in entry.get("credentials", []):
                source, target = credential_paths(item)
                note(source.is_file() and target is not None, f"harness {entry['id']}: credential file {source}"
                     + ("" if target is not None else " has an unusable destination"))
                if not entry.get("write_back_logins"):
                    lines.append("     the agent can read this login, and a refresh made during a run is not copied back: "
                                 "your own login may then stop working. A separate login kept for this purpose avoids both.")
    return lines, problems


def credential_paths(item):
    """Split `host file:path under the container home`. The destination is None if it is not safely inside the home."""
    source, _, target = item.partition(":")
    inside = Path(target)
    usable = bool(target) and not inside.is_absolute() and ".." not in inside.parts
    return Path(source).expanduser(), inside if usable else None


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


BACKUPS_KEPT = 5


def plausible_refresh(original, new):
    """Would a harness plausibly have turned `original` into `new` by refreshing a login?

    This narrows what can be written back; it cannot prove the content is genuine. Whoever
    turns write-back on is trusting the agent with the login, which is why it is off by default.
    """
    if not new.strip() or len(new) > max(65536, 20 * len(original)):
        return False
    try:
        before = json.loads(original)
    except Exception:  # not JSON at all: nothing more can be checked
        return True
    try:
        after = json.loads(new)
    except Exception:  # the original was JSON and this is not: half-written, or not a login
        return False
    if type(after) is not type(before):
        return False
    return not isinstance(before, dict) or set(after) == set(before)


def write_private(path, data, mode):
    """Create a file that is never readable by others, not even for a moment, and is safely on disk."""
    if path.is_symlink() or path.exists():
        path.unlink()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, mode)


def changed_logins(copies, home):
    """How many login copies the run altered, replaced or removed."""
    changed = 0
    for _, copy_path, before in copies:
        try:
            same = (not copy_path.is_symlink() and copy_path.is_file()
                    and copy_path.stat().st_size <= 1 << 20 and digest(copy_path) == before)
        except OSError:
            same = False
        changed += not same
    return changed


def return_credentials(copies, home):
    """Write back login files the harness refreshed while it ran. Only used when a suite asks for it.

    Some logins replace their refresh token on use. Throwing the container's copy away would
    then leave the file on this machine holding a dead token. But the copy comes back from a
    place the agent could write to, so it is accepted only if all of this holds:

    - it is a plain file inside the throwaway home, reached through no link;
    - it changed, and the original on this machine has not been touched since it was copied;
    - it is not empty and, if the original was JSON, it is JSON with the same top-level keys.

    Each original is kept beside the login as <name>.harness-bench-backup-<time>; the newest few are kept.
    Returns (files written back, files refused).
    """
    written = refused = 0
    inside = Path(home).resolve()
    for source, copy_path, before in copies:
        try:
            if not copy_path.is_symlink() and not copy_path.exists():
                continue  # the harness removed its login; leave this machine's alone
            if (copy_path.is_symlink() or not copy_path.is_file() or inside not in copy_path.resolve().parents
                    or copy_path.stat().st_size > 1 << 20):
                refused += 1
                continue
            new = copy_path.read_bytes()
            if hashlib.sha256(new).hexdigest() == before:
                continue
            target = source.resolve()  # if the login is itself a link (a dotfiles setup), keep the link
            original = target.read_bytes() if target.is_file() else None
            if original is None or hashlib.sha256(original).hexdigest() != before or not plausible_refresh(original, new):
                refused += 1
                continue
            mode = stat.S_IMODE(target.stat().st_mode)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            write_private(target.with_name(f"{target.name}.harness-bench-backup-{stamp}"), original, mode)
            for stale in sorted(target.parent.glob(f"{target.name}.harness-bench-backup-*"))[:-BACKUPS_KEPT]:
                stale.unlink()
            staging = target.with_name(target.name + ".harness-bench-new")
            write_private(staging, new, mode)
            os.replace(staging, target)
            written += 1
        except OSError:
            refused += 1
    return written, refused


def cleanup(log=print):
    """Remove what a killed runner can leave behind: containers, throwaway homes and their login copies."""
    removed = 0
    for pattern in ("hb-home-*", "hb-env-*", "hb-passwd-*", "hb-judge-*"):
        for path in Path(tempfile.gettempdir()).glob(pattern):
            remove_tree(path)
            removed += 1
            log(f"removed {path}")
    listed = subprocess.run(["docker", "ps", "--all", "--quiet", "--filter", "name=^hb-"], capture_output=True, text=True)
    for container in listed.stdout.split() if listed.returncode == 0 else []:
        subprocess.run(["docker", "rm", "--force", container], capture_output=True)
        removed += 1
        log(f"removed container {container}")
    return removed


def blocked(run, reason, evidence, extra):
    return {"run_id": run["run_id"], "status": "blocked", "elapsed_seconds": None,
            "human_interventions": 0, "human_minutes": 0, "attempts": 0,
            "checks_passed": 0, "checks_total": 0, "evidence_ref": evidence,
            "input_tokens": None, "output_tokens": None, "cost_usd": None,
            "blocked_reason": reason, **extra}


def execute_run(run, configuration, root, directory, sandbox, version):
    harness = next(h for h in configuration["harnesses"] if h["id"] == run["harness_id"])
    entry = next(t for t in configuration["tasks"] if t["id"] == run["task_id"])
    model = next((m for m in configuration.get("models", []) if m["id"] == run.get("model_id")), None)
    mode = next((m for m in configuration.get("modes", []) if m["id"] == run.get("mode_id")), None)
    adapter = adapters.get(harness["adapter"])
    evidence = directory.relative_to(root).as_posix()
    extra = {"mock": adapter.id == "mock", "sandbox": sandbox.name, "harness_version": version,
             "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    task = tasks.load(root, entry)
    if (task.seed_revision, task.evaluator_revision) != (entry["seed_revision"], entry["evaluator_revision"]):
        return blocked(run, "task files differ from the pinned revisions", evidence, extra)
    if version != harness["version"]:
        return blocked(run, f"harness version {version!r} differs from pinned {harness['version']!r}", evidence, extra)
    settings = harness.get("env", []) + (model or {}).get("harness_env", {}).get(harness["id"], [])
    environment, absent = resolve_environment(settings)
    if absent:
        return blocked(run, f"environment variables not set: {', '.join(absent)}", evidence, extra)
    credentials = [credential_paths(item) for item in harness.get("credentials", [])]
    unusable = [str(source) for source, target in credentials if target is None or not source.is_file()]
    if unusable:
        return blocked(run, f"credential files not usable: {', '.join(unusable)}", evidence, extra)

    workspace, telemetry = directory / "workspace", directory / "telemetry"
    shutil.copytree(task.seed, workspace)
    telemetry.mkdir()
    seed_repository(workspace)

    home = Path(tempfile.mkdtemp(prefix="hb-home-"))
    copies, finished = [], False
    try:
        for source, target in credentials:
            (home / target).parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes()
            write_private(home / target, content, stat.S_IRUSR | stat.S_IWUSR)
            # Remember exactly what was handed over, so a change on either side is noticed.
            copies.append((source, home / target, hashlib.sha256(content).hexdigest()))
        mounts = {"work": (workspace, True), "home": (home, True), "telemetry": (telemetry, True)}
        if adapter.id == "mock":
            mounts["mock"] = (MOCK_DIRECTORY, False)
            if task.reference:
                mounts["reference"] = (task.reference, False)
            if (task.seed.parent / "variants").is_dir():
                mounts["variants"] = (task.seed.parent / "variants", False)
            # Seeds the fake agent. Real harnesses are told nothing about the experiment.
            environment["HB_RUN_ID"] = run["run_id"]
        environment = {**adapter.env, **environment}
        prompt = task.prompt + (mode or {}).get("prompt_suffix", "")
        name = model.get("harness_names", {}).get(harness["id"], model["name"]) if model else configuration.get("model")
        effort = model.get("reasoning_effort") if model else configuration.get("reasoning_effort")
        extra_arguments = harness.get("args", []) + (model or {}).get("harness_args", {}).get(harness["id"], [])
        # Mount paths are fixed per backend, so they can be computed before launch.
        argv = adapter.command(Launch(prompt, name, effort, run.get("mode_id", "single"),
                                      tuple(extra_arguments), _paths(sandbox, mounts)))
        outcome = sandbox.run(argv, mounts=mounts, cwd="work", env=environment, network=True,
                              timeout=configuration["budget"]["timeout_seconds"],
                              stdout=directory / "agent.stdout", stderr=directory / "agent.stderr")
        finished = True
    finally:
        # Nothing may interrupt this: it is what removes the copied logins.
        with shielded():
            try:
                altered = changed_logins(copies, home)
                if altered:
                    extra["logins_changed_in_run"] = altered
                # Only once the agent is known to have stopped, and only if the suite asked for it.
                if finished and harness.get("write_back_logins"):
                    refreshed, refused = return_credentials(copies, home)
                    if refreshed:
                        extra["credentials_refreshed"] = refreshed
                    if refused:
                        extra["credentials_refused"] = refused
            finally:
                for _, copy_path, _ in copies:
                    try:
                        copy_path.unlink()  # the logins first, by name, in case the folder resists
                    except OSError:
                        pass
                remove_tree(home)

    if outcome.launch_error:
        return blocked(run, f"harness did not start: {outcome.launch_error}", evidence, extra)
    files, added, removed = change_stats(task.seed, workspace, directory / "changes.patch")
    set_aside_repositories(workspace)
    try:
        usage = adapter.parse((directory / "agent.stdout").read_text(errors="replace"), telemetry)
    except Exception as error:  # a parser that meets output it did not expect must not cost the run
        usage = adapters.empty()
        extra["usage_error"] = f"{type(error).__name__}: {error}"[:200]
    elapsed = round(outcome.elapsed_seconds, 3)
    extra.update(exit_code=outcome.exit_code, files_changed=files, lines_added=added, lines_removed=removed)
    if usage.get("error"):
        extra["harness_error"] = usage["error"]
    if usage.get("error") and files == 0 and not usage["output_tokens"] and not outcome.timed_out:
        # The harness itself says it could not reach the model, and nothing was produced: an expired
        # login, say. It can exit cleanly after that, so the exit code alone would not show it.
        archive_workspace(workspace, directory / "workspace.tar.gz")
        return {**blocked(run, f"the harness reported an error before doing any work: {usage['error']}", evidence, extra),
                "attempts": 1, "elapsed_seconds": elapsed}
    never_started = (not outcome.timed_out and outcome.exit_code != 0 and files == 0
                     and outcome.elapsed_seconds < NEVER_STARTED_SECONDS)
    if never_started:
        # Typically a login or configuration failure, which says nothing about the harness's ability.
        archive_workspace(workspace, directory / "workspace.tar.gz")
        return {**blocked(run, f"harness exited {outcome.exit_code} within {NEVER_STARTED_SECONDS}s "
                               "without changing the workspace", evidence, extra),
                "attempts": 1, "elapsed_seconds": elapsed}

    # How a model is paid for can differ from the harness's default (one login, one API key).
    billing = (model or {}).get("billing", harness.get("billing", "api"))
    passed, total, error, setup_fault = evaluate(task, workspace, directory, sandbox)
    left_out = archive_workspace(workspace, directory / "workspace.tar.gz")
    if left_out:
        extra["not_archived"] = left_out[:20]
    if setup_fault:
        # The agent did its work but it could not be graded. Keep the run out of the pass rate; retry it.
        return {**blocked(run, error, evidence, extra), "attempts": 1, "elapsed_seconds": elapsed}
    status = "timed_out" if outcome.timed_out else "passed" if total and passed == total else "failed"
    record = {"run_id": run["run_id"], "status": status, "elapsed_seconds": elapsed,
              "human_interventions": 0, "human_minutes": 0, "attempts": 1,
              "checks_passed": passed, "checks_total": total, "evidence_ref": evidence,
              "input_tokens": usage["input_tokens"], "cached_input_tokens": usage["cached_input_tokens"],
              "cache_write_tokens": usage["cache_write_tokens"], "output_tokens": usage["output_tokens"],
              "turns": usage["turns"], "tool_calls": usage["tool_calls"], "subagents": usage["subagents"],
              # A subscription's included usage is not a dollar invoice.
              "cost_usd": usage["reported_cost_usd"] if billing == "api" else None,
              "list_price_usd": list_price(usage, (model or {}).get("price_per_mtok")),
              **extra}
    if error:
        record["evaluator_error"] = error
    return record


def _paths(sandbox, mounts):
    if sandbox.name == "local":
        return {mount: str(Path(host).resolve()) for mount, (host, _) in mounts.items()}
    return {mount: sandbox.path(mount) for mount in mounts}


def read_results(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# Fields of a harness entry that say which runs it has, not how any one run is made.
WHICH_RUNS = ("tasks", "models", "modes", "repetitions")


def run_inputs(configuration, run):
    """Everything that decides how one run is made. Two plans agree about a run when these are equal."""
    find = lambda items, wanted: next((item for item in items if item["id"] == wanted), None)
    harness = find(configuration["harnesses"], run["harness_id"])
    model = find(configuration.get("models", []), run.get("model_id"))
    if model:
        # A model entry also holds other harnesses' names and options for it; only this harness's apply to this run.
        per_harness = ("harness_names", "harness_args", "harness_env")
        model = {**{key: value for key, value in model.items() if key not in per_harness},
                 "name": model.get("harness_names", {}).get(harness["id"], model["name"]),
                 "args": model.get("harness_args", {}).get(harness["id"], []),
                 "env": model.get("harness_env", {}).get(harness["id"], [])}
    return {"task": find(configuration["tasks"], run["task_id"]),
            "harness": {key: value for key, value in harness.items() if key not in WHICH_RUNS},
            "model": model,
            "mode": find(configuration.get("modes", []), run.get("mode_id")),
            "budget": configuration.get("budget"), "schema_version": configuration.get("schema_version")}


def only_the_limit_was_raised(old, new):
    """Do two sets of run inputs differ in nothing but a longer time limit?

    A harness is never told its limit, so a run that ended on its own under the shorter limit is exactly
    the run it would have been under the longer one. A run that was cut off is not: it is carried too,
    so that it stays visible, but marked with the limit it was made under.
    """
    without = lambda inputs: {**inputs, "budget": {k: v for k, v in (inputs.get("budget") or {}).items() if k != "timeout_seconds"}}
    before, after = ((inputs.get("budget") or {}).get("timeout_seconds") for inputs in (old, new))
    return without(old) == without(new) and isinstance(before, (int, float)) and isinstance(after, (int, float)) and after > before


def carry_over(old_plan, new_plan, root):
    """Bring results into a plan that extends another. Returns (carried, skipped, refused).

    A plan's id covers the whole suite, so adding a harness, a task for one harness, or more repeats
    gives a new plan and an empty set of results. The runs already made are still valid for the new
    plan when nothing about them changed: the same pinned task, harness entry, model, mode and budget.
    Those are copied across with their stored files, each marked with the run it came from. A run
    whose inputs differ is refused and has to be made again, with one exception: a longer time limit
    (see `only_the_limit_was_raised`), where each record is marked with the limit it was made under.

    The new plan may list the runs in a different order from the one they were made in; each record
    keeps the time it really started.
    """
    validate_plan(old_plan)
    validate_plan(new_plan)
    root = Path(root).resolve()
    old_base, new_base = (root / "runs" / plan["plan_id"][:16] for plan in (old_plan, new_plan))
    require(old_base != new_base, "the two plans are the same")
    place = lambda run: tuple(run.get(key) for key in ("task_id", "harness_id", "model_id", "mode_id", "repetition"))
    old_runs = {run["run_id"]: run for run in old_plan["runs"]}
    new_runs = {place(run): run for run in new_plan["runs"]}
    new_base.mkdir(parents=True, exist_ok=True)
    (new_base / "plan.json").write_text(json.dumps(new_plan, indent=2) + "\n", encoding="utf-8")
    results = new_base / "results.jsonl"
    done = {record["run_id"] for record in read_results(results)}
    carried, skipped, refused = [], [], []
    for record in read_results(old_base / "results.jsonl"):
        old_run = old_runs.get(record["run_id"])
        new_run = new_runs.get(place(old_run)) if old_run else None
        if new_run is None:
            refused.append((record["run_id"], "the new plan has no such run"))
        elif new_run["run_id"] in done:
            skipped.append(record["run_id"])
        elif (before := run_inputs(old_plan["configuration"], old_run)) != (after := run_inputs(new_plan["configuration"], new_run)) \
                and not only_the_limit_was_raised(before, after):
            refused.append((record["run_id"], "its task, harness, model, mode or budget is not the same in the new plan"))
        else:
            moved = {**record, "run_id": new_run["run_id"], "carried_from": record["run_id"]}
            if before != after:
                moved.setdefault("made_under_timeout_seconds", before["budget"]["timeout_seconds"])
            source, target = run_directory(old_base, old_run), run_directory(new_base, new_run)
            if source.is_dir():
                remove_tree(target)
                shutil.copytree(source, target, symlinks=True)
                moved["evidence_ref"] = target.relative_to(root).as_posix()
            with results.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(moved) + "\n")
            carried.append(new_run["run_id"])
    return carried, skipped, refused


def execute(plan, root, sandbox, *, limit=None, harness=None, model=None, repetition=None, retry_blocked=False, log=print):
    validate_plan(plan)
    require(plan["ready"], "plan is not ready: " + "; ".join(plan["not_ready_reasons"]))
    configuration = plan["configuration"]
    require(configuration["schema_version"] == 2, "only schema 2 suites can be executed")
    real = [h["id"] for h in configuration["harnesses"] if h["adapter"] not in ("mock", "manual")]
    by_hand = {h["id"] for h in configuration["harnesses"] if h["adapter"] == "manual"}
    require(sandbox.name != "local" or not real,
            f"the local sandbox has no isolation and only runs the mock adapter; use --sandbox docker for {', '.join(real)}")
    root = Path(root).resolve()
    base = root / "runs" / plan["plan_id"][:16]
    base.mkdir(parents=True, exist_ok=True)
    (base / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    results = base / "results.jsonl"
    records = read_results(results)
    wanted = set(harness.split(",")) if harness else None
    unknown = (wanted or set()) - {h["id"] for h in configuration["harnesses"]}
    require(not unknown, f"no such harness in this plan: {', '.join(sorted(unknown))}")
    selected = {run["run_id"] for run in plan["runs"]
                if (wanted is None or run["harness_id"] in wanted) and model in (None, run.get("model_id"))
                and repetition in (None, run["repetition"])
                and run["harness_id"] not in by_hand}
    if retry_blocked:
        records = [r for r in records if not (r["status"] == "blocked" and r["run_id"] in selected)]
        results.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    done = {record["run_id"] for record in records}
    pending = [run for run in plan["runs"] if run["run_id"] in selected and run["run_id"] not in done][:limit]
    versions = {}
    for index, run in enumerate(pending, 1):
        entry = next(h for h in configuration["harnesses"] if h["id"] == run["harness_id"])
        if entry["id"] not in versions:
            versions[entry["id"]] = version_of(adapters.get(entry["adapter"]), sandbox, base / "_probe" / entry["id"])
        directory = run_directory(base, run)
        try:
            remove_tree(directory)
            directory.mkdir(parents=True)
            record = execute_run(run, configuration, root, directory, sandbox, versions[entry["id"]])
        except Exception as error:
            # Whatever an agent leaves behind, one bad run must not stop the batch or go unrecorded.
            record = blocked(run, f"the runner could not process this run: {type(error).__name__}: {error}"[:500],
                             directory.relative_to(root).as_posix(),
                             {"mock": entry["adapter"] == "mock", "sandbox": sandbox.name,
                              "harness_version": versions[entry["id"]]})
        with results.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        log(f"[{index}/{len(pending)}] {run['run_id'].split(':', 1)[1]}: {record['status']}"
            + (f" ({record['blocked_reason']})" if record["status"] == "blocked" else
               f" {record['checks_passed']}/{record['checks_total']} checks, {record['elapsed_seconds']}s"))
    shutil.rmtree(base / "_probe", ignore_errors=True)
    hand_runs = sum(run["harness_id"] in by_hand and run["run_id"] not in done for run in plan["runs"])
    if hand_runs:
        log(f"{hand_runs} run(s) by hand are still waiting: see `manual-list`.")
    # Say plainly how the batch went, so a batch that was entirely blocked cannot pass unnoticed.
    tally = Counter(record["status"] for record in read_results(results) if record["run_id"] in {run["run_id"] for run in pending})
    if pending:
        log(f"{len(pending)} run(s): " + ", ".join(f"{count} {status.replace('_', ' ')}" for status, count in sorted(tally.items())))
        if tally.get("blocked") == len(pending):
            log("Every run was blocked. Nothing was measured; see the reasons above.")
    return results
