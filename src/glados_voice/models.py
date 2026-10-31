"""Download and verify the ONNX model files that the upstream package expects.

Models live in a per-user data directory (see ``models_dir``). Run
``glados-voice download-models`` to fetch them ahead of time.
"""

import hashlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from urllib.request import urlopen

from platformdirs import user_data_dir

RELEASE_URL = "https://github.com/dnhkng/GlaDOS/releases/download/0.1"

# name -> sha256 of the release assets
MODELS = {
    "glados.onnx": "17ea16dd18e1bac343090b8589042b4052f1e5456d42cad8842a4f110de25095",
    "phomenizer_en.onnx": "b64dbbeca8b350927a0b6ca5c4642e0230173034abd0b5bb72c07680d700c5a0",
}


def package_models_dir() -> Path:
    """Models directory of the installed upstream package (holds the small bundled files)."""
    spec = importlib.util.find_spec("glados_voice._glados")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("The upstream GLaDOS package (glados_voice._glados) is not installed")
    return Path(list(spec.submodule_search_locations)[0]) / "models"


def models_dir() -> Path:
    """Per-user model cache, so reinstalling or upgrading the package never re-downloads them.

    Override with GLADOS_MODELS_DIR. Default: the user data directory of the OS
    (for example %LOCALAPPDATA%\\glados-voice\\models or ~/.local/share/glados-voice/models).
    """
    override = os.environ.get("GLADOS_MODELS_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir("glados-voice", appauthor=False)) / "models"


def model_file() -> Path:
    return models_dir() / "glados.onnx"


def use_models_dir() -> None:
    """Point the upstream phonemizer at the user model cache.

    Upstream binds its default config (with a path inside the package) when the module is
    imported, so the bound default is updated instead of editing the submodule.
    """
    from ._glados import phonemizer

    phonemizer.Phonemizer.__init__.__defaults__[0].MODEL_NAME = models_dir() / "phomenizer_en.onnx"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(name: str, expected: str, target: Path) -> None:
    part = target.with_suffix(target.suffix + ".part")
    print(f"Downloading {name}...", file=sys.stderr, flush=True)
    with urlopen(f"{RELEASE_URL}/{name}", timeout=60) as resp, part.open("wb") as out:
        while block := resp.read(1 << 20):
            out.write(block)
    if _sha256(part) != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {name}; the download was discarded")
    part.replace(target)


def ensure_models() -> Path:
    """Make sure every model file is present and valid. Returns the models directory."""
    directory = models_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in MODELS.items():
        target = directory / name
        if target.exists() and _sha256(target) == expected:
            continue
        _download(name, expected, target)
    # The upstream loader reads "<model path>.json" next to the model.
    config = directory / "glados.onnx.json"
    if not config.exists():
        shutil.copyfile(package_models_dir() / "glados.onnx.json", config)
    return directory
