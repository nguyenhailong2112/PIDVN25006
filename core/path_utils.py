from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
