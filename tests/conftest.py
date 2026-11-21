"""Test setup shared by every test module: the exercise packages come from a
throwaway copy of tests/fixtures/data, never from the lecturer's private
../ReinsPrivateData. Runs before any test module imports backend (which reads
REINS_DATA_DIR at import time)."""
import os
import shutil
import tempfile
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "data"
_DATA = Path(tempfile.mkdtemp(prefix="reins-data-")) / "data"
shutil.copytree(_FIXTURE, _DATA)
os.environ["REINS_DATA_DIR"] = str(_DATA)

# The settings page writes the API key to .env: tests get a throwaway file.
os.environ["REINS_ENV_FILE"] = str(_DATA.parent / "test.env")
