"""The project's name wherever another program reads it: settings in the
environment, HTTP headers, and the default names of the database and of the
private folder.

Until November 2026 the project had another name. Installs made before then keep
their settings, database and private folder under it, and the IDE plugins that
students already installed send and read their headers under it. The second
spelling in each function below keeps all of those working. It can go once no
class runs a plugin built before the rename.
"""
import os
from pathlib import Path
from typing import Mapping, Optional

ENV_PREFIX = "REINS_"
HEADER_PREFIX = "X-Reins-"
DB_FILE = "reins.db"
PRIVATE_DIR = "ReinsPrivateData"
PLUGIN_NAME = "REINS Edu"

_OLD_ENV_PREFIX = "VERICLASS_"
_OLD_HEADER_PREFIX = "X-VeriClass-"
_OLD_DB_FILE = "vericlass.db"
_OLD_PRIVATE_DIR = "VeriClassPrivateData"


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    """The setting REINS_<name>. An empty value counts as not set."""
    return os.environ.get(ENV_PREFIX + name) or os.environ.get(_OLD_ENV_PREFIX + name) or default


def header(headers: Mapping[str, str], name: str) -> str:
    """The request header X-Reins-<name>, or "" when the client didn't send it."""
    return headers.get(HEADER_PREFIX + name) or headers.get(_OLD_HEADER_PREFIX + name) or ""


def response_headers(name: str, value: str) -> dict[str, str]:
    """X-Reins-<name> for a response, and the spelling plugins built before the rename read."""
    return {HEADER_PREFIX + name: value, _OLD_HEADER_PREFIX + name: value}


def default_db(folder: Path) -> Path:
    """The database's file in `folder` when DB_PATH isn't set: an install from
    before the rename keeps the database it has."""
    new, old = folder / DB_FILE, folder / _OLD_DB_FILE
    return old if old.exists() and not new.exists() else new


def private_dir(parent: Path) -> Optional[Path]:
    """The private data folder a lecturer keeps next to the code, if there is one."""
    for name in (PRIVATE_DIR, _OLD_PRIVATE_DIR):
        if (parent / name).is_dir():
            return parent / name
    return None


def plugin_name() -> str:
    """The name on the plugin's panels in the students' IDE, which is how the tutor
    refers to them. A plugin built before the rename shows its older name:
    REINS_PLUGIN_NAME in .env says so until the class has the new build."""
    return (env("PLUGIN_NAME") or PLUGIN_NAME).strip()
