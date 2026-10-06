"""Bounded execution of agent and evaluator commands.

Commands see their directories through named mounts. Each mount is exposed as an
environment variable (HB_WORK, HB_EVAL, ...), so the same command works in either backend.
"""

import contextlib
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid


@dataclass(frozen=True)
class Outcome:
    exit_code: int | None
    timed_out: bool
    elapsed_seconds: float
    launch_error: str | None = None


class DockerSandbox:
    """Runs each command in a fresh container. The only backend allowed for real harnesses."""

    name = "docker"

    def __init__(self, image, cpus="2", memory="4g"):
        self.image, self.cpus, self.memory = image, cpus, memory

    def path(self, mount):
        return f"/hb/{mount}"

    @staticmethod
    def remove(container):
        """Force the container away. True once it is certain not to be running."""
        subprocess.run(["docker", "rm", "--force", container], capture_output=True)
        listed = subprocess.run(["docker", "ps", "--quiet", "--filter", f"name=^{container}$"], capture_output=True, text=True)
        return listed.returncode == 0 and not listed.stdout.strip()

    def run(self, argv, *, mounts, cwd, env=None, network=False, timeout, stdout, stderr):
        container = f"hb-{uuid.uuid4().hex[:12]}"
        command = ["docker", "run", "--rm", "--init", "--name", container,
                   "--network", "bridge" if network else "none",
                   "--cpus", self.cpus, "--memory", self.memory, "--workdir", self.path(cwd)]
        identity = None
        if sys.platform.startswith("linux"):
            # On Linux, files in the mounts belong to this user, so the container must run as this user.
            # It also needs a name: tools that look themselves up fail for a user id with no passwd entry.
            descriptor, identity = tempfile.mkstemp(prefix="hb-passwd-")
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(f"root:x:0:0:root:/root:/bin/sh\nbench:x:{os.getuid()}:{os.getgid()}::/tmp:/bin/sh\n")
            os.chmod(identity, 0o644)
            command += ["--user", f"{os.getuid()}:{os.getgid()}", "--volume", f"{identity}:/etc/passwd:ro"]
        # Elsewhere (Docker Desktop) mounts are writable by any container user, so the image's own user is used.
        environment = {
            "HOME": "/tmp",
            # Mounted files can look foreign to git inside the container; it must still work there.
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*",
            "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@localhost",
            "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@localhost",
            **(env or {}),
        }
        for mount, (host, writable) in mounts.items():
            command += ["--volume", f"{Path(host).resolve()}:{self.path(mount)}{'' if writable else ':ro'}"]
            environment[f"HB_{mount.upper()}"] = self.path(mount)
        if "home" in mounts:
            environment["HOME"] = self.path("home")
        # The container's variables go through a private file: not the process list (they can be
        # secrets), and not the docker client's own environment (it needs the real HOME).
        descriptor, variables = tempfile.mkstemp(prefix="hb-env-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for key, value in environment.items():
                    if "\n" in value or "\n" in key or "=" in key:
                        raise ValueError(f"cannot pass {key} into the container: unsupported characters")
                    handle.write(f"{key}={value}\n")
            command += ["--env-file", variables, self.image, *argv]
            return _execute(command, None, None, timeout, stdout, stderr, lambda: self.remove(container),
                            launch_codes=(125, 126, 127))
        finally:
            os.unlink(variables)
            if identity:
                os.unlink(identity)


class LocalSandbox:
    """Runs directly on this machine with no isolation.

    Only for the built-in mock agent and for validating tasks you wrote yourself.
    The runner refuses to use it with a real harness.
    """

    name = "local"

    def __init__(self):
        self._mounts = {}

    def path(self, mount):
        return str(self._mounts[mount])

    def run(self, argv, *, mounts, cwd, env=None, network=False, timeout, stdout, stderr):
        self._mounts = {mount: Path(host).resolve() for mount, (host, _) in mounts.items()}
        environment = {**os.environ, **(env or {})}
        for mount, host in self._mounts.items():
            environment[f"HB_{mount.upper()}"] = str(host)
        if "home" in mounts:
            environment["HOME"] = str(self._mounts["home"])
        return _execute(list(argv), environment, self._mounts[cwd], timeout, stdout, stderr, None,
                        launch_codes=(126, 127))


SIGNALS = [getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, name)]


@contextlib.contextmanager
def shielded():
    """Finish a clean-up even if the user presses Ctrl-C again or the terminal closes meanwhile."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {number: signal.signal(number, signal.SIG_IGN) for number in SIGNALS}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


class StopFailed(RuntimeError):
    """The agent could not be confirmed stopped. Nothing it can still reach may be trusted."""


def _execute(command, environment, cwd, timeout, stdout, stderr, kill, launch_codes):
    started = time.monotonic()
    process = None

    def stop():
        with shielded():
            stopped = kill() if kill else True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:  # already gone; macOS reports that as a permission error
                pass
            process.wait()
        if not stopped:
            raise StopFailed("the container could not be removed; check `docker ps --filter name=hb-`")

    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        try:
            try:
                process = subprocess.Popen(command, env=environment, cwd=cwd, stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=err, start_new_session=True)
            except OSError as error:
                return Outcome(None, False, 0.0, str(error))
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            stop()
            code = process.returncode
        except BaseException:
            # Interrupted (Ctrl-C, a closed terminal): never leave an agent running with nobody watching.
            if process is not None:
                stop()
            raise
    elapsed = time.monotonic() - started
    if not timed_out and code in launch_codes:
        lines = [line.strip() for line in Path(stderr).read_text(errors="replace").splitlines() if line.strip()]
        # Docker puts the reason first and a usage hint last; a missing command says it once.
        return Outcome(code, False, elapsed, lines[0][:300] if lines else f"exit {code}")
    return Outcome(code, timed_out, elapsed)


def make(kind, image=None):
    if kind == "local":
        return LocalSandbox()
    if kind == "docker":
        if not image:
            raise ValueError("docker sandbox needs --image")
        return DockerSandbox(image)
    raise ValueError(f"unknown sandbox: {kind}")
