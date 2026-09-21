from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
import csv
import re
from typing import BinaryIO

import pandas as pd

from .database import DEFAULT_DATABASE_PATH, get_connection


SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".pdf", ".ofx"}


@dataclass
class ImportRecord:
    transaction_date: str = ""
    description: str = ""
    amount_cents: int | None = None
    transaction_type: str = ""
    external_id: str = ""
    institution: str = ""
    category_name: str = ""
    status: str = "Revisão necessária"
    issue: str = ""
    is_duplicate: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def document_hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def parse_money(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    return int(amount * 100)


def parse_date(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="raise")
        return parsed.date().isoformat()
    except (ValueError, TypeError):
        return ""


def classify_description(description: str) -> tuple[str, str]:
    text = description.casefold()
    rules = (
        (("salário", "salario", "holerite", "payroll"), "receita", "Salário"),
        (("supermercado", "mercado", "carrefour", "assai", "ifood"), "despesa", "Alimentação"),
        (("energia", "luz", "aluguel", "condomínio", "condominio", "água", "agua"), "despesa", "Moradia"),
        (("combustível", "combustivel", "uber", "99", "posto"), "despesa", "Transporte"),
        (("escola", "curso", "mensalidade"), "despesa", "Educação"),
    )
    for keywords, kind, category in rules:
        if any(keyword in text for keyword in keywords):
            return kind, category
    return "", ""


def _finalize(record: ImportRecord) -> ImportRecord:
    if record.amount_cents is not None and not record.transaction_type:
        record.transaction_type = "despesa" if record.amount_cents < 0 else ""
        record.amount_cents = abs(record.amount_cents)
    if record.description and not record.transaction_type:
        record.transaction_type, record.category_name = classify_description(record.description)
    issues = []
    if not record.transaction_date:
        issues.append("data ausente ou inválida")
    if not record.description:
        issues.append("descrição ausente")
    if record.amount_cents is None or record.amount_cents <= 0:
        issues.append("valor ausente ou inválido")
    if not record.transaction_type:
        issues.append("tipo não identificado")
    record.issue = "; ".join(issues)
    record.status = "Pronto" if not issues else "Revisão necessária"
    return record


def parse_dataframe(dataframe: pd.DataFrame, mapping: dict[str, str]) -> list[ImportRecord]:
    records = []
    for _, row in dataframe.iterrows():
        raw_amount = parse_money(row.get(mapping.get("amount", ""))) if mapping.get("amount") else None
        record = ImportRecord(
            transaction_date=parse_date(row.get(mapping.get("date", ""))) if mapping.get("date") else "",
            description=str(row.get(mapping.get("description", ""), "")).strip() if mapping.get("description") else "",
            amount_cents=raw_amount,
            external_id=str(row.get(mapping.get("external_id", ""), "")).strip() if mapping.get("external_id") else "",
        )
        records.append(_finalize(record))
    return records


def parse_csv(data: bytes, delimiter: str | None = None, encoding: str = "utf-8-sig", mapping: dict[str, str] | None = None) -> tuple[list[str], list[ImportRecord]]:
    text = data.decode(encoding)
    dataframe = pd.read_csv(StringIO(text), sep=delimiter or None, engine="python")
    columns = [str(column) for column in dataframe.columns]
    if mapping is None:
        mapping = _detect_mapping(columns)
    return columns, parse_dataframe(dataframe, mapping)


def parse_excel(data: bytes, sheet_name: str | int = 0, mapping: dict[str, str] | None = None) -> tuple[list[str], list[str], list[ImportRecord]]:
    workbook = pd.ExcelFile(BytesIO(data))
    dataframe = pd.read_excel(BytesIO(data), sheet_name=sheet_name)
    columns = [str(column) for column in dataframe.columns]
    return workbook.sheet_names, columns, parse_dataframe(dataframe, mapping or _detect_mapping(columns))


def _detect_mapping(columns: list[str]) -> dict[str, str]:
    normalized = {column.casefold().strip(): column for column in columns}
    def find(names: tuple[str, ...]) -> str:
        for name in names:
            if name in normalized:
                return normalized[name]
        return ""
    return {"date": find(("data", "date", "dt")), "description": find(("descrição", "descricao", "description", "histórico", "historico")), "amount": find(("valor", "amount", "value", "valor líquido", "valor liquido")), "external_id": find(("fitid", "id", "identificador", "id transação"))}


def parse_pdf(data: bytes) -> tuple[str, list[ImportRecord]]:
    try:
        import fitz
        document = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
    except Exception as error:
        raise ValueError("Não foi possível ler o PDF localmente.") from error
    records: list[ImportRecord] = []
    pattern = re.compile(r"(?P<date>\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}).{0,100}?(?P<amount>-?R?\$?\s*[\d.]+[,\.]\d{2})", re.IGNORECASE)
    normalized_text = text.replace("\n", " ")
    for match in pattern.finditer(normalized_text):
        start = max(0, match.start() - 80)
        description = normalized_text[start:match.start()].strip() or "Operação extraída do PDF"
        record = ImportRecord(transaction_date=parse_date(match.group("date")), description=description, amount_cents=parse_money(match.group("amount")))
        records.append(_finalize(record))
    return text, records


def parse_ofx(data: bytes) -> tuple[str, list[ImportRecord]]:
    try:
        from ofxparse import OfxParser
        ofx = OfxParser.parse(BytesIO(data))
    except Exception as error:
        raise ValueError("Não foi possível interpretar o OFX localmente.") from error
    institution = getattr(getattr(ofx, "institution", None), "organization", "") or ""
    records = []
    for account in getattr(ofx, "accounts", []):
        for transaction in account.statement.transactions:
            amount = parse_money(str(transaction.amount))
            if amount is not None and float(transaction.amount) < 0:
                amount = -amount
            records.append(_finalize(ImportRecord(transaction_date=parse_date(transaction.date), description=transaction.payee or transaction.memo or "Transação OFX", amount_cents=amount, external_id=transaction.id or "", institution=institution)))
    return institution, records


def mark_duplicates(records: list[ImportRecord], account_id: int | None, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[ImportRecord]:
    with get_connection(database_path) as connection:
        for record in records:
            if record.external_id:
                found = connection.execute("SELECT 1 FROM import_records WHERE external_id = ? AND account_id IS ?", (record.external_id, account_id)).fetchone()
            else:
                found = connection.execute("""SELECT 1 FROM transactions WHERE account_id IS ? AND transaction_date = ? AND amount_cents = ? AND lower(trim(description)) = lower(trim(?))""", (account_id, record.transaction_date, record.amount_cents or 0, record.description)).fetchone()
            if found:
                record.is_duplicate = True
                record.status = "Possível duplicidade"
    return records


def import_records(records: list[ImportRecord], account_id: int, category_ids: dict[str, int], source_hash: str, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    valid = [record for record in records if record.status == "Pronto" and not record.is_duplicate]
    if not valid:
        raise ValueError("Nenhum registro pronto e não duplicado foi selecionado.")
    with get_connection(database_path) as connection:
        existing_document = connection.execute("SELECT 1 FROM import_batches WHERE source_hash = ?", (source_hash,)).fetchone()
        if existing_document:
            raise ValueError("Este documento já foi importado anteriormente.")
        connection.execute("INSERT INTO import_batches (source_hash, record_count) VALUES (?, ?)", (source_hash, len(valid)))
        batch_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        for record in valid:
            category_id = category_ids.get(record.category_name)
            if category_id is None:
                raise ValueError(f"Categoria ausente para: {record.description}")
            cursor = connection.execute("""INSERT INTO transactions (account_id, category_id, description, amount_cents, transaction_type, transaction_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?)""", (account_id, category_id, record.description, record.amount_cents, record.transaction_type, record.transaction_date, f"Importado; lote {batch_id}"))
            connection.execute("INSERT INTO import_records (batch_id, transaction_id, account_id, external_id) VALUES (?, ?, ?, ?)", (batch_id, cursor.lastrowid, account_id, record.external_id or None))
        return len(valid)
