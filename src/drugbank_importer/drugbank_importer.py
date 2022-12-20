#!/usr/bin/env python3
import csv
import logging
import lzma
import os
import re
from enum import Enum
from io import BytesIO
from itertools import islice
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Tuple, Type

import click
from lxml import etree  # nosec: B410
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from .models import (
    Base,
    Carrier,
    Description,
    Drug,
    Enzyme,
    Partner,
    Target,
    Transporter,
)

PARTNER_CATEGORIES = ("target", "enzyme", "transporter", "carrier")


class RecordType(str, Enum):
    CARRIER = "carrier"
    DESCRIPTION = "description"
    DRUG = "drug"
    ENZYME = "enzyme"
    PARTNER = "partner"
    TARGET = "target"
    TRANSPORTER = "transporter"


FILES: Dict[RecordType, str] = {
    RecordType.CARRIER: "drug2carrier.csv",
    RecordType.DESCRIPTION: "description.csv",
    RecordType.DRUG: "drugs.csv",
    RecordType.ENZYME: "drug2enzyme.csv",
    RecordType.PARTNER: "partner_protein.csv",
    RecordType.TARGET: "drug2target.csv",
    RecordType.TRANSPORTER: "drug2transporter.csv",
}

DBMODELS: Dict[RecordType, Type[DeclarativeBase]] = {
    RecordType.CARRIER: Carrier,
    RecordType.DESCRIPTION: Description,
    RecordType.DRUG: Drug,
    RecordType.ENZYME: Enzyme,
    RecordType.PARTNER: Partner,
    RecordType.TARGET: Target,
    RecordType.TRANSPORTER: Transporter,
}

HEADERS: Dict[RecordType, Tuple[str, ...]] = {
    RecordType.CARRIER: ("drugbank_id", "partner_id", "action"),
    RecordType.DESCRIPTION: ("drugbank_id", "drug_name", "description", "SMILES"),
    RecordType.DRUG: (
        "drugbank_id",
        "drugname",
        "drug_type",
        "ATC_codes",
        "approved",
        "experimental",
        "illicit",
        "investigational",
        "nutraceutical",
        "withdrawn",
    ),
    RecordType.ENZYME: ("drugbank_id", "partner_id", "action"),
    RecordType.PARTNER: (
        "partner_id",
        "partner_name",
        "gene_name",
        "uniprot_id",
        "genbank_gene_id",
        "genbank_protein_id",
        "hgnc_id",
        "organism",
        "taxonomy_id",
    ),
    RecordType.TARGET: ("drugbank_id", "partner_id", "action"),
    RecordType.TRANSPORTER: ("drugbank_id", "partner_id", "action"),
}


def get_drugbank_records(
    filename: Path,
) -> Generator[etree.ElementTree, None, None]:
    # Parse XML

    start_pattern: re.Pattern[str] = re.compile("^<drug type=")
    stop_pattern: re.Pattern[str] = re.compile("^</drug>$")

    acc: List[str] = []
    match_state: bool = False
    is_compressed: bool = filename.suffix == ".xz"
    open_file = lzma.open if is_compressed else open
    with open_file(filename) as f_handler:
        line_generator: Generator[str, None, None] = (
            (line.decode() for line in f_handler)  # type: ignore
            if is_compressed
            else f_handler
        )

        for line in line_generator:

            if start_pattern.match(line):

                if acc:
                    raise ValueError(
                        "New entity starting while the previous is not yielded yet"
                    )
                match_state = True

            if match_state:
                acc.append(line)

            if stop_pattern.match(line):
                if not acc:
                    raise ValueError("New entity has no lines")

                yield etree.parse(BytesIO("".join(acc).encode()))  # nosec: B320
                match_state = False
                acc = []


def is_human(organism: str | None, taxonomy_id: str | None) -> bool:
    return (taxonomy_id is not None and taxonomy_id == "9606") or (
        organism is not None
        and organism.lower()
        in (
            "human",
            "homo sapiens",
        )
    )


def extract_drug_fields(child: etree.ElementTree) -> Dict[str, Any]:
    groups: List[str] = [s.text for s in child.find("groups").findall("group")]
    to_return: Dict[str, str | int] = {  # type: ignore
        "drugname": child.findall("name")[0].text,
        "drug_type": child.getroot().attrib["type"],
        "ATC_codes": child.findall("atc-codes")[0].text is not None,
    } | {
        field_name: field_name in groups
        for field_name in (
            "approved",
            "experimental",
            "illicit",
            "investigational",
            "nutraceutical",
            "withdrawn",
        )
    }
    try:
        to_return["SMILES"] = [
            prop.find("value").text
            for prop in child.find("calculated-properties")
            if prop.find("kind").text == "SMILES"
        ][0]
    except (KeyError, IndexError, TypeError):
        to_return["SMILES"] = ""

    return to_return


def parse_drugbank_record(  # noqa: C901
    child: etree.ElementTree,
    partners_already_seen: Set[str],
) -> Generator[Tuple[RecordType, Any], None, None]:

    drugbank_id: str = [
        s.text for s in child.findall("drugbank-id") if "primary" in s.attrib
    ][0]
    drug_data: Dict[str, Any] = extract_drug_fields(child) | {
        "drugbank_id": drugbank_id
    }

    # yield drug
    yield (
        RecordType.DRUG,
        {field: drug_data[field] for field in HEADERS[RecordType.DRUG]},
    )

    # yield description
    description_data: Dict[str, Any] = {
        "drugbank_id": drugbank_id,
        "drug_name": drug_data["drugname"],
        "description": child.find("description").text,
        "SMILES": drug_data["SMILES"],
    }
    yield (
        RecordType.DESCRIPTION,
        {field: description_data[field] for field in HEADERS[RecordType.DESCRIPTION]},
    )

    # Get targets, enzymes, transporters, carriers

    for record_type in (e for e in RecordType if e.value in PARTNER_CATEGORIES):
        template: str = record_type.value
        drug_data[template] = []

        for res in child.find(f"{template}s").findall(template):

            if res.find("polypeptide") is None:
                continue

            template_id: str = res.find("id").text
            template_actions: List[str] = [
                s.text.lower() for s in res.find("actions").findall("action")
            ]

            # Get gene, organism and taxonomy_id as they are required to know whether
            # the tempalte is a valid partner for its drug

            template_gene: str | None = res.find("polypeptide").find("gene-name").text
            template_organism: str | None = res.find("organism").text
            template_taxonomy_id: str | None = (
                res.find("polypeptide").find("organism").attrib["ncbi-taxonomy-id"]
            )

            if is_human(template_organism, template_taxonomy_id):
                template_organism = "Human"
                template_taxonomy_id = "9606"

            # If gene, or organism or taxonomy_id is missing, don't register it as a
            # partner

            if (
                template_gene is None
                or template_organism is None
                or template_taxonomy_id is None
            ):

                continue

            interactions: List[Dict[str, str]] = [
                {
                    "drugbank_id": drugbank_id,
                    "partner_id": template_id,
                    "action": template_action,
                }
                for template_action in (template_actions or [""])
            ]

            # yield interaction
            yield from [
                (
                    record_type,
                    {field: interaction[field] for field in HEADERS[record_type]},
                )
                for interaction in interactions
            ]

            if template_id in partners_already_seen:

                continue

            template_name: str = res.find("name").text
            template_external_ids: List[str] = (
                res.find("polypeptide")
                .find("external-identifiers")
                .findall("external-identifier")
            )

            # Set cross reference defaults
            cross_references: Dict[str, str] = {
                "uniprot_id": "",
                "genbank_gene_id": "",
                "genbank_protein_id": "",
                "hgnc_id": "",
            }

            # Iterate over cross references that are found, and update the proper one
            # accordingly
            cross_references_labels: Dict[str, str] = {
                "UniProtKB": "uniprot_id",
                "GenBank Gene Database": "genbank_gene_id",
                "GenBank Protein Database": "genbank_protein_id",
                "HUGO Gene Nomenclature Committee (HGNC)": "hgnc_id",
            }

            for external_id in template_external_ids:
                for label, field in cross_references_labels.items():

                    if external_id.find("resource").text == label:  # type: ignore
                        cross_references[field] = external_id.find(
                            "identifier"
                        ).text  # type: ignore

            # yield partner_data
            partner_data: Dict[str, str] = {
                "partner_id": template_id,
                "gene_name": template_gene,
                "partner_name": template_name,
                "organism": template_organism,
                "taxonomy_id": template_taxonomy_id,
            } | cross_references

            yield (
                RecordType.PARTNER,
                {field: partner_data[field] for field in HEADERS[RecordType.PARTNER]},
            )
            partners_already_seen.add(template_id)


def serialize_to_file(
    record_type: RecordType,
    records: Iterable[Tuple[str] | Dict[str, str | bool | int]],
    filename: Path,
    append: Optional[bool] = False,
    headers: Optional[bool] = False,
) -> None:
    with filename.open("a" if append else "w", newline="") as f_handler:
        writer = csv.writer(f_handler, lineterminator=os.linesep)

        for record in records:

            if headers:
                writer.writerow(record)
            else:
                writer.writerow(
                    [record[field] for field in HEADERS[record_type]]  # type: ignore
                )


def serialize_to_files(
    target: str,
    business_entity_generator: Generator[Tuple[RecordType, Any], None, None],
) -> None:
    target_path: Path = Path(target)

    for record_type, headers in HEADERS.items():
        serialize_to_file(
            record_type,
            [headers],
            target_path / FILES[record_type],
            headers=True,
        )

    for record_type, record_value in business_entity_generator:
        serialize_to_file(
            record_type,
            [record_value],
            target_path / FILES[record_type],
            append=True,
        )


def serialize_to_sqlite(
    target: str,
    business_entity_generator: Generator[Tuple[RecordType, Any], None, None],
) -> None:
    engine = create_engine(target)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for record_type, record_value in business_entity_generator:
            session.add(DBMODELS[record_type](**record_value))

        session.commit()


def get_drugbank_entities(
    file_path: Path, take_first: Optional[int] = None
) -> Generator[Tuple[RecordType, Any], None, None]:
    """Create business_entity_generator, limited to `take_first` drugs."""
    partners_already_seen: Set[str] = set()

    return (
        drugbank_entity
        for drugbank_record in islice(get_drugbank_records(file_path), take_first)
        for drugbank_entity in parse_drugbank_record(
            drugbank_record, partners_already_seen
        )
    )


def import_drugbank(
    file_path: Optional[Path] = None,
    target: Optional[str] = None,
    take_first: Optional[int] = None,
) -> None:

    # Set unspecified parameter values

    if file_path is None:
        file_path = Path("drugbank.xml")

    if target is None:
        target = str(Path.cwd())

    # Choose whether to dump CSV files or sqlite database
    dump_csv: bool = Path(target).is_dir()
    dump_sqlite: bool = not dump_csv

    # Retrieve business entity generator
    drugbank_entities: Generator[
        Tuple[RecordType, Any], None, None
    ] = get_drugbank_entities(file_path, take_first)

    if dump_csv:
        serialize_to_files(target, drugbank_entities)

    if dump_sqlite:
        serialize_to_sqlite(target, drugbank_entities)


@click.command()
@click.option(
    "--file-path",
    "-f",
    type=Path,
    default="drugbank.xml",
    help="Path to the DrugBank XML dump",
)
@click.option(
    "--target",
    "-t",
    type=str,
    default="sqlite://",
    help="Where to save the import, either a path to a directory (for CSV) or a "
    "sqlalchemy ressource locator, e.g. `sqlite://` for memory or "
    "`sqlite:///tmp/database.db` for `/tmp/database.db`",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Limit the number of records to proceed",
)
def cli(
    file_path: Optional[Path] = None,
    target: Optional[str] = None,
    limit: Optional[int] = None,
) -> None:

    return import_drugbank(file_path, target, limit)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    cli()
