from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir

import pytest

from drugbank_importer.drugbank_importer import import_drugbank

DRUGBANK_FILE = Path("tests/drugbank.xml.xz")
TMPDIR = gettempdir()


def _check_produced_files(reference_path: Path) -> None:

    for output_file in reference_path.glob("*.csv"):
        ref: str = sha256(output_file.read_bytes()).hexdigest()
        got: str = sha256((Path(TMPDIR) / output_file.name).read_bytes()).hexdigest()
        assert ref == got, f"Files {output_file} are different!"


@pytest.mark.short
def test_short() -> None:
    import_drugbank(
        file_path=DRUGBANK_FILE,
        target=TMPDIR,
        take_first=50,
    )
    _check_produced_files(Path("tests/csv/short"))


@pytest.mark.long
def test_long() -> None:
    import_drugbank(
        file_path=DRUGBANK_FILE,
        target=TMPDIR,
    )

    _check_produced_files(Path("tests/csv/long"))
