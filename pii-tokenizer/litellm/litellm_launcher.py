# Invoked via: pythonw.exe litellm_launcher.py <config> <port>
# pythonw.exe (Windows-subsystem Python) has no console, so it is not in any console
# group and cannot receive CTRL+C/SIGINT events from the calling terminal.
import os
import subprocess
import sys

# Suppress console windows for ALL child processes (Prisma query-engine, etc.).
# pythonw.exe has no console; without this, Windows allocates a new visible console
# window every time a console-subsystem binary (like prisma-query-engine-windows.exe)
# is spawned via subprocess.Popen.
if sys.platform == "win32":
    _orig_popen_init = subprocess.Popen.__init__
    def _silent_popen_init(self, *args, **kwargs):
        kwargs.setdefault("creationflags", 0)
        kwargs["creationflags"] |= subprocess.CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _silent_popen_init

# Make the PII tokenization modules (pii_guardrail, pii_vault) importable so the
# LiteLLM guardrail configured in the YAML can be loaded. They live in the parent
# dir (pii-tokenizer/), one level up from this litellm/ folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if len(sys.argv) < 3:
    sys.exit("Usage: litellm_launcher.py <config_path> <port>")

sys.argv = ["litellm", "--config", sys.argv[1], "--port", sys.argv[2]]

from litellm import run_server
run_server()
