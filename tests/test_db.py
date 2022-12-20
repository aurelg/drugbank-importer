import json
import sqlite3
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Dict, List

import pytest

from drugbank_importer.drugbank_importer import import_drugbank

DRUGBANK_FILE = Path("tests/drugbank.xml.xz")
TMP_PATH = Path(gettempdir())


def _check_produced_db(reference_path: Path, db_path: str) -> None:

    con: sqlite3.Connection = sqlite3.connect(db_path[10:])
    tests: List[Dict[str, Any]] = json.loads(reference_path.read_text())

    for test in tests:
        res = con.execute(test["statement"])
        actual = [list(item) for item in res.fetchall()]
        assert actual == test["expected"]


@pytest.fixture
def target() -> str:
    database_path = TMP_PATH / "database.db"

    if database_path.exists():
        database_path.unlink()

    return f"sqlite:///{database_path}"


@pytest.mark.short
def test_short_db(target: str) -> None:
    import_drugbank(
        file_path=DRUGBANK_FILE,
        target=target,
        take_first=50,
    )
    _check_produced_db(Path("tests/db/short.json"), target)


@pytest.mark.long
def test_long_db(target: str) -> None:
    import_drugbank(
        file_path=DRUGBANK_FILE,
        target=target,
    )
    _check_produced_db(Path("tests/db/long.json"), target)
