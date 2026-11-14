"""Render hosted-embedding build: no Torch, sentence-transformers, or ONNX.

Only run main on Render. It removes cached local-ML installations, installs
non-ML requirements, and checks the application imports without an API key.
No provider request, database connection, or migration is performed.
"""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

_LOCAL_PACKAGES = {"torch", "sentence-transformers", "fastembed", "onnxruntime",
                   "onnxruntime-gpu", "torchvision", "torchaudio", "transformers"}


def partition_requirements(source):
    """Return the old Torch pin for audit and a hosted-runtime dependency list.

    The original worker requirements stay intact; this builder no longer
    installs the Torch pin. Keeping this return shape avoids unrelated callers.
    """
    torch_pin = None
    runtime = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[]", stripped, maxsplit=1)[0].lower().replace("_", "-")
        if name == "torch":
            match = re.fullmatch(r"torch==([0-9]+\.[0-9]+\.[0-9]+)", stripped)
            if not match or torch_pin is not None:
                raise ValueError("Expected one exact stable torch==X.Y.Z pin")
            torch_pin = match.group(1)
        elif name != "pytest" and name not in _LOCAL_PACKAGES:
            runtime.append(line)
    if torch_pin is None:
        raise ValueError("Original requirements must contain an exact Torch pin")
    return torch_pin, runtime


def main():
    if os.getenv("RENDER") != "true":
        raise RuntimeError("This installer is only for Render; do not run it in your development environment")
    if sys.platform != "linux" or sys.version_info[:2] != (3, 11):
        raise RuntimeError("This deployment build targets Linux / Python 3.11")
    if shutil.which("git") is None:
        raise RuntimeError("Git is required by ingestion")
    root = Path(__file__).resolve().parent
    _, runtime = partition_requirements((root / "requirements.txt").read_text(encoding="utf-8-sig"))
    pip = [sys.executable, "-m", "pip"]
    subprocess.check_call(pip + ["uninstall", "--yes", *sorted(_LOCAL_PACKAGES)])
    with tempfile.TemporaryDirectory(prefix="reposcope-hosted-build-") as directory:
        path = Path(directory) / "requirements-runtime.txt"
        path.write_text("\n".join(runtime) + "\n", encoding="utf-8")
        subprocess.check_call(pip + ["install", "--no-cache-dir", "--disable-pip-version-check", "-r", str(path)])
    subprocess.check_call(pip + ["check"])
    environment = os.environ.copy()
    environment["DATABASE_URL"] = "postgresql+psycopg://offline:offline@127.0.0.1:1/build_check?connect_timeout=1"
    environment.pop("GEMINI_API_KEY", None)
    check = (
        "import importlib.util, sys; "
        "assert all(importlib.util.find_spec(n) is None for n in "
        "('torch','sentence_transformers','fastembed','onnxruntime')); "
        "from reposcope.main import app; "
        "from reposcope.ingestion.index_preparation import INDEX_VERSION; "
        "assert 'gemini-embedding-001' in INDEX_VERSION; "
        "assert not any(n in sys.modules for n in ('torch','sentence_transformers','fastembed','onnxruntime')); "
        "print('Hosted Gemini API import verified; local embedding runtimes absent')"
    )
    subprocess.check_call([sys.executable, "-c", check], cwd=root, env=environment)


if __name__ == "__main__":
    main()
