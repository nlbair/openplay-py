import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

DATA_REPO = os.environ.get("OPENPLAY_REPO", "nlbair/openplay")
DATA_TAG = os.environ.get("OPENPLAY_DATA_TAG", "data-v0.1.0")
CHECKSUM_FILE = "checksums.json"

_state = {"data_dir": None, "checksums": None}


def set_data_dir(path):
    """Read tables from a local folder instead of downloading them.

    The folder must hold the release files side by side, for example
    ``matches.parquet`` and ``events_eng_2425.parquet``. Pass ``None`` to go
    back to downloading from the GitHub release.
    """
    _state["data_dir"] = None if path is None else Path(path)
    _state["checksums"] = None


def data_dir():
    if _state["data_dir"] is not None:
        return _state["data_dir"]
    env = os.environ.get("OPENPLAY_DATA_DIR")
    return Path(env) if env else None


def cache_dir():
    """Folder where downloaded files are kept between sessions."""
    env = os.environ.get("OPENPLAY_CACHE_DIR")
    if env:
        base = Path(env)
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "openplay" / "cache"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "openplay"
    path = base / DATA_TAG
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_cache():
    """Delete every downloaded file for the current data release."""
    path = cache_dir()
    shutil.rmtree(path, ignore_errors=True)
    _state["checksums"] = None


def _token():
    return os.environ.get("OPENPLAY_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _request(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "openplay-python"})
    token = _token()
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    return urllib.request.urlopen(req, timeout=120)


def _asset_urls():
    if "assets" in _state and _state.get("assets_tag") == DATA_TAG:
        return _state["assets"]
    api = f"https://api.github.com/repos/{DATA_REPO}/releases/tags/{DATA_TAG}"
    with _request(api, accept="application/vnd.github+json") as r:
        release = json.load(r)
    _state["assets"] = {a["name"]: a["url"] for a in release.get("assets", [])}
    _state["assets_tag"] = DATA_TAG
    return _state["assets"]


def _download(name, dest):
    if _token():
        urls = _asset_urls()
        if name not in urls:
            raise FileNotFoundError(f"{name} is not in release {DATA_TAG} of {DATA_REPO}")
        resp = _request(urls[name], accept="application/octet-stream")
    else:
        resp = _request(f"https://github.com/{DATA_REPO}/releases/download/{DATA_TAG}/{name}")
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh, resp:
            shutil.copyfileobj(resp, fh, length=1 << 20)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def checksums():
    if _state["checksums"] is not None:
        return _state["checksums"]
    local = data_dir()
    if local is not None:
        path = local / CHECKSUM_FILE
        _state["checksums"] = json.loads(path.read_text()) if path.exists() else {}
        return _state["checksums"]
    path = cache_dir() / CHECKSUM_FILE
    if not path.exists():
        _download(CHECKSUM_FILE, path)
    _state["checksums"] = json.loads(path.read_text())
    return _state["checksums"]


def available_files():
    local = data_dir()
    if local is not None:
        return sorted(p.name for p in local.iterdir() if p.is_file())
    return sorted(checksums())


def fetch(name):
    """Return a local path to one release file, downloading it if needed."""
    local = data_dir()
    if local is not None:
        path = local / name
        if not path.exists():
            raise FileNotFoundError(f"{name} not found in {local}")
        return path
    sums = checksums()
    if name not in sums:
        raise FileNotFoundError(f"{name} is not part of data release {DATA_TAG}")
    path = cache_dir() / name
    if path.exists() and _sha256(path) == sums[name]["sha256"]:
        return path
    _download(name, path)
    got = _sha256(path)
    if got != sums[name]["sha256"]:
        path.unlink(missing_ok=True)
        raise IOError(f"checksum mismatch for {name}; the download was removed, please try again")
    return path
