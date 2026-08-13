"""Amesim RPyC worker entry point, run inside AMEPython.exe (see amesim_api.py).

Siemens' own scripting/python/serve_api.py uses rpyc's ThreadedServer, which
serves each client connection on its own background thread. Simcenter Amesim's
run-management code (AMERunSimulation and friends) hangs indefinitely when
called from anything other than the process's main thread (verified: the same
compiled model runs instantly from a plain console, but hangs forever when
invoked through a ThreadedServer client thread). OneShotServer instead serves
its single connection synchronously on the calling (main) thread, which fixes
this — and fits this project anyway, since exactly one client (our MCP server)
talks to a given worker for the life of one connect()/disconnect() session.
"""

import sys

import ame_apy  # noqa: F401  (imported so it's available in the served namespace)
import amesim  # noqa: F401

import rpyc
from rpyc.utils.server import OneShotServer

if __name__ == "__main__":
    port = int(sys.argv[1])
    server = OneShotServer(rpyc.SlaveService, hostname="localhost", port=port, reuse_addr=True)
    server.start()
