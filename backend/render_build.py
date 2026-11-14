"""Render build: require the existing Torch pin from the CPU-only index.

Does not connect to the database, run migrations, or execute repository code.
Fails rather than silently changing a missing Torch version or using CUDA.
"""
from importlib.metadata import version
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def partition_requirements(source):
    torch_pin = None
    runtime = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[]", stripped, maxsplit=1)[0].lower()
        if name == "torch":
            match = re.fullmatch(r"torch==([0-9]+\.[0-9]+\.[0-9]+)", stripped)
            if not match or torch_pin is not None:
                raise ValueError("Expected one exact stable torch==X.Y.Z pin")
            torch_pin = match.group(1)
        elif name != "pytest":
            runtime.append(line)
    if torch_pin is None:
        raise ValueError("Original requirements must contain an exact Torch pin")
    return torch_pin, runtime


def main():
    if sys.platform != "linux" or sys.version_info[:2] != (3, 11):
        raise RuntimeError("This deployment build targets Linux / Python 3.11")
    if shutil.which("git") is None:
        raise RuntimeError("Git is required by ingestion")
    root = Path(__file__).resolve().parent
    pin, remaining = partition_requirements((root / "requirements.txt").read_text(encoding="utf-8-sig"))
    pip = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check"]
    subprocess.check_call(pip + ["--index-url", "https://download.pytorch.org/whl/cpu", f"torch=={pin}"])
    if version("torch") != pin + "+cpu":
        raise RuntimeError("Expected the pinned CPU-only PyTorch distribution")
    with tempfile.TemporaryDirectory(prefix="reposcope-build-") as directory:
        requirements = Path(directory) / "requirements-runtime.txt"
        requirements.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        subprocess.check_call(pip + ["-r", str(requirements)])
    if version("torch") != pin + "+cpu":
        raise RuntimeError("Dependency resolution changed the requested CPU-only Torch build")
    subprocess.check_call([sys.executable, "-m", "pip", "check"])
    subprocess.check_call([sys.executable, "-c",
        "import torch; assert torch.version.cuda is None; print('CPU PyTorch import verified')"])


if __name__ == "__main__":
    main()
