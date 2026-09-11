"""Load local credentials only when an operation explicitly needs them."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_project_environment() -> bool:
    """Read only this checkout's .env; exported variables keep precedence.

    Importing this module does not read a file or environment variable. Call it
    after the dry-run return. Values are parsed as data without interpolation or
    shell execution. Missing files are allowed when keys are already exported.
    """
    path = PROJECT_ROOT / ".env"
    if path.is_symlink():
        raise ValueError("The project .env must be a regular local file, not a symlink.")
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError("The project .env must be a regular local file.")

    from dotenv import load_dotenv

    return load_dotenv(dotenv_path=path, override=False, interpolate=False, encoding="utf-8")
