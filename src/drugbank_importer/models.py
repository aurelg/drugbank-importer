from sqlalchemy import Boolean, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.properties import ForeignKey


class Base(DeclarativeBase):
    pass


class Drug(Base):

    __tablename__: str = "drugs"

    drugbank_id: Mapped[str] = mapped_column(
        String(6),
        primary_key=True,
        index=True,
    )
    drugname: Mapped[str] = mapped_column(String())
    drug_type: Mapped[str] = mapped_column(String())
    ATC_codes: Mapped[bool] = mapped_column(Boolean())
    approved: Mapped[bool] = mapped_column(Boolean())
    experimental: Mapped[bool] = mapped_column(Boolean())
    illicit: Mapped[bool] = mapped_column(Boolean())
    investigational: Mapped[bool] = mapped_column(Boolean())
    nutraceutical: Mapped[bool] = mapped_column(Boolean())
    withdrawn: Mapped[bool] = mapped_column(Boolean())


class Description(Base):

    __tablename__: str = "descriptions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    drugbank_id: Mapped[str] = mapped_column(
        ForeignKey("drugs.drugbank_id"),
        index=True,
    )
    drug_name: Mapped[str] = mapped_column(String())
    description: Mapped[str] = mapped_column(
        String(),
        nullable=True,
    )
    SMILES: Mapped[str] = mapped_column(String())


class Partner(Base):

    __tablename__: str = "partners"

    partner_id: Mapped[str] = mapped_column(
        String(6),
        primary_key=True,
        index=True,
    )
    partner_name: Mapped[str] = mapped_column(String())
    gene_name: Mapped[str] = mapped_column(String())
    uniprot_id: Mapped[str] = mapped_column(String())
    genbank_gene_id: Mapped[str] = mapped_column(String())
    genbank_protein_id: Mapped[str] = mapped_column(String())
    hgnc_id: Mapped[str] = mapped_column(String())
    organism: Mapped[str] = mapped_column(String())
    taxonomy_id: Mapped[str] = mapped_column(String())


class Carrier(Base):

    __tablename__: str = "carriers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    drugbank_id: Mapped[str] = mapped_column(
        ForeignKey("drugs.drugbank_id"),
        index=True,
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("partners.partner_id"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String())


class Transporter(Base):

    __tablename__: str = "transporters"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    drugbank_id: Mapped[str] = mapped_column(
        ForeignKey("drugs.drugbank_id"),
        index=True,
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("partners.partner_id"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String())


class Target(Base):

    __tablename__: str = "targets"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    drugbank_id: Mapped[str] = mapped_column(
        ForeignKey("drugs.drugbank_id"),
        index=True,
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("partners.partner_id"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String())


class Enzyme(Base):

    __tablename__: str = "enzymes"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    drugbank_id: Mapped[str] = mapped_column(
        ForeignKey("drugs.drugbank_id"),
        index=True,
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("partners.partner_id"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String())
