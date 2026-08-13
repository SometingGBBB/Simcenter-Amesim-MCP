"""Wrapper around the Simcenter Amesim Circuit API, bridged over RPyC.

Two reasons this isn't a direct in-process import of ame_apy/amesim:

1. AMEPython.exe (the launcher that makes `ame_apy`/`amesim` importable) prints
   an unconditional "Starting Python ..." banner to stdout with no way to
   silence it. If used as the MCP server's own stdio child process, that
   banner would corrupt the JSON-RPC stream Claude Desktop expects.
2. AMERunSimulation (and likely other run-management calls) hangs forever when
   invoked from anything but the process's main thread — verified: the exact
   same compiled model runs instantly from a plain console, but hangs when
   called through rpyc's ThreadedServer (which services each connection on
   its own background thread). Siemens' own scripting/python/serve_api.py
   uses ThreadedServer, so it can't be used as-is either.

So instead we spawn AMEPython.exe as a separate background "worker" process
running our own worker_entry.py (an RPyC OneShotServer — single connection,
served synchronously on the main thread), and this module talks to it as an
ordinary RPyC client over a local TCP port. The worker's stdout/stderr
(banner included) is redirected to a log file and never touches our own
stdio.
"""

import os
import subprocess
import time
import winreg

import rpyc.utils.classic as rpyc_classic

# Machine-level env vars the worker needs that Claude Desktop's own process may be
# missing (env var changes don't propagate to already-running processes on Windows,
# and Claude Desktop is a long-lived background app — it can easily predate these
# being set). Read fresh from the registry instead of trusting inherited os.environ.
_MACHINE_ENV_FALLBACKS = ["LMS_LICENSE", "SC1D_LICENSING_TYPE"]


def _read_machine_env_var(name):
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None

VERSION_DIRS = {
    "2021.1": r"C:\Program Files\Simcenter\2021.1\Amesim",
    "2404": r"C:\Program Files\Simcenter\2404\Amesim",
}
DEFAULT_VERSION = "2021.1"
DEFAULT_PORT = 18861

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENDOR_DIR = os.path.join(_PROJECT_ROOT, "vendor")
_WORKER_LOG = os.path.join(_PROJECT_ROOT, "amesim_worker.log")

# Executed once (remotely) right after connecting, so execute_python() gets a
# persistent namespace with ame_apy/amesim pre-imported and output capture,
# mirroring inventor-mcp's execute_python but running in the worker process.
_REMOTE_BOOTSTRAP = r"""
import io as __mcp_io, contextlib as __mcp_contextlib, traceback as __mcp_traceback
import ame_apy, amesim

def __mcp_exec(_mcp_code):
    buf = __mcp_io.StringIO()
    try:
        with __mcp_contextlib.redirect_stdout(buf):
            exec(compile(_mcp_code, "<mcp>", "exec"), globals())
        out = buf.getvalue().strip()
        return out if out else "(ok, no output)"
    except Exception:
        partial = buf.getvalue().strip()
        tb = __mcp_traceback.format_exc(limit=3)
        return (partial + "\n" if partial else "") + "ERROR:\n" + tb
"""


class AmesimConnection:
    def __init__(self):
        self._conn = None
        self._worker_proc = None
        self._version = None
        self._port = None

    @property
    def api(self):
        """The remote `ame_apy` module (Circuit API) — raises if not connected."""
        if self._conn is None:
            raise RuntimeError("Not connected to Simcenter Amesim. Call connect() first.")
        return self._conn.modules["ame_apy"]

    @property
    def amesim(self):
        """The remote `amesim` module (Simulation Scripting helpers)."""
        if self._conn is None:
            raise RuntimeError("Not connected to Simcenter Amesim. Call connect() first.")
        return self._conn.modules["amesim"]

    # ---------- Connection ----------

    def connect(self, version: str = DEFAULT_VERSION, port: int = DEFAULT_PORT) -> str:
        if version not in VERSION_DIRS:
            raise ValueError(
                f"Unknown Amesim version '{version}'. Available: {', '.join(VERSION_DIRS)}"
            )

        attached = False
        try:
            conn = rpyc_classic.connect("localhost", port)
            conn.ping()
            attached = True
        except Exception:
            conn = None

        if conn is None:
            self._spawn_worker(version, port)
            last_err = None
            conn = None
            for _ in range(40):
                time.sleep(0.5)
                try:
                    conn = rpyc_classic.connect("localhost", port)
                    conn.ping()
                    break
                except Exception as e:
                    last_err = e
                    conn = None
            if conn is None:
                raise RuntimeError(
                    f"Started the Amesim worker but could not connect on port {port}: {last_err}"
                )

        conn._config["sync_request_timeout"] = 300  # compiling/running a model can be slow
        self._conn = conn
        self._version = version
        self._port = port

        try:
            conn.execute(_REMOTE_BOOTSTRAP)
        except Exception as e:
            self._reset()
            raise RuntimeError(f"Connected to worker but failed to load ame_apy/amesim: {e}")

        init_note = ""
        try:
            conn.modules["ame_apy"].AMEInitAPI(False)
        except Exception as e:
            init_note = f" (AMEInitAPI warning — may already be initialized: {e})"

        verb = "Attached to already-running" if attached else "Started"
        return f"{verb} Amesim {version} worker on port {port}. Circuit API ready.{init_note}"

    def is_connected(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.ping()
            return True
        except Exception:
            self._reset()
            return False

    def disconnect(self) -> str:
        if self._conn is None:
            return "Not connected."
        try:
            try:
                self._conn.modules["ame_apy"].AMECloseAPI()
            except Exception:
                pass
            self._conn.close()
        finally:
            if self._worker_proc is not None:
                try:
                    self._worker_proc.terminate()
                except Exception:
                    pass
            self._reset()
        return "Disconnected and released the Amesim license token."

    def _reset(self):
        self._conn = None
        self._worker_proc = None
        self._version = None
        self._port = None

    def _spawn_worker(self, version: str, port: int):
        version_dir = VERSION_DIRS[version]
        ame_exe = os.path.join(version_dir, "win64", "AMEPython.exe")
        if not os.path.isfile(ame_exe):
            raise RuntimeError(f"AMEPython.exe not found for version {version}: {ame_exe}")
        worker_entry_py = os.path.join(_PROJECT_ROOT, "amesim_mcp", "worker_entry.py")
        if not os.path.isfile(worker_entry_py):
            raise RuntimeError(f"worker_entry.py not found: {worker_entry_py}")

        env = os.environ.copy()
        env["AME"] = version_dir
        for name in _MACHINE_ENV_FALLBACKS:
            if not env.get(name):
                value = _read_machine_env_var(name)
                if value:
                    env[name] = value
        env["PATH"] = (
            version_dir + os.pathsep
            + os.path.join(version_dir, "win64") + os.pathsep
            + os.path.join(version_dir, "win32") + os.pathsep
            + env.get("PATH", "")
        )
        env["PYTHONPATH"] = _VENDOR_DIR + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )

        log = open(_WORKER_LOG, "w")
        self._worker_proc = subprocess.Popen(
            [ame_exe, "-s", worker_entry_py, str(port)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.DETACHED_PROCESS,
        )

    # ---------- Escape hatch ----------

    def execute_python(self, code: str) -> str:
        if self._conn is None:
            raise RuntimeError("Not connected to Simcenter Amesim. Call connect() first.")
        remote_exec = self._conn.namespace["__mcp_exec"]
        return remote_exec(code)
