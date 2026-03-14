from pathlib import Path
import os
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "PIDVN25006"


def resolve_project_path(path_str: str | Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def ensure_exists(path_str: str | Path, label: str = "Path") -> Path:
    path = resolve_project_path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def user_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    target = base / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def user_config_path(filename: str) -> Path:
    return user_config_dir() / filename


def ensure_user_file(filename: str, default_rel_path: str | None = None) -> Path:
    target = user_config_path(filename)
    if target.exists():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    if default_rel_path:
        src = resolve_project_path(default_rel_path)
        if src.exists():
            shutil.copy2(src, target)
            return target
    target.write_text("{}", encoding="utf-8")
    return target
