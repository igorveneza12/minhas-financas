from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile

from .categories import DEFAULT_CATEGORIES
from .database import DEFAULT_DATABASE_PATH, get_connection, initialize_database


BACKUP_DIR = DEFAULT_DATABASE_PATH.parent.parent / "backups"
REQUIRED_TABLES = {"accounts", "categories", "transactions"}
ALL_DATA_TABLES = (
    "transfers",
    "recurring_occurrences",
    "recurring_expenses",
    "import_records",
    "import_batches",
    "payroll_slips",
    "card_payments",
    "card_installments",
    "card_invoices",
    "card_purchases",
    "credit_cards",
    "debt_payments",
    "debts",
    "budgets",
    "financial_goals",
    "transactions",
    "accounts",
    "categories",
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def create_backup(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    backup_path: str | Path | None = None,
) -> Path:
    source_path = Path(database_path)
    if not source_path.exists():
        raise ValueError("O banco de dados não existe.")
    destination = (
        Path(backup_path)
        if backup_path
        else (BACKUP_DIR if source_path == DEFAULT_DATABASE_PATH else source_path.parent / "backups")
        / f"financeiro-{_timestamp()}.db"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def backup_bytes(database_path: str | Path = DEFAULT_DATABASE_PATH) -> bytes:
    source = sqlite3.connect(database_path)
    target = sqlite3.connect(":memory:")
    try:
        source.backup(target)
        return target.serialize()
    finally:
        target.close()
        source.close()


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def validate_backup_bytes(data: bytes) -> tuple[bool, str]:
    if not data:
        return False, "O arquivo de backup está vazio."
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temporary:
            temporary.write(data)
            temporary_path = temporary.name
        connection = sqlite3.connect(temporary_path)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                return False, "A integridade do backup não foi confirmada."
            missing = REQUIRED_TABLES - _table_names(connection)
            if missing:
                return False, f"Backup incompatível; faltam tabelas: {', '.join(sorted(missing))}."
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False, "O arquivo selecionado não é um banco SQLite válido."
    finally:
        if temporary_path:
            os.unlink(temporary_path)
    return True, "Backup válido."


def reset_database(database_path: str | Path = DEFAULT_DATABASE_PATH) -> Path:
    backup_path = create_backup(database_path)
    with get_connection(database_path) as connection:
        for table in ALL_DATA_TABLES:
            connection.execute(f"DELETE FROM {table}")
        connection.executemany(
            "INSERT INTO categories (name, category_type) VALUES (?, ?)",
            [item for category_type, names in DEFAULT_CATEGORIES.items() for item in ((name, category_type) for name in names)],
        )
    return backup_path


def restore_database(
    backup_data: bytes,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> Path:
    valid, message = validate_backup_bytes(backup_data)
    if not valid:
        raise ValueError(message)
    current_backup = create_backup(database_path)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temporary:
            temporary.write(backup_data)
            temporary_path = temporary.name
        source = sqlite3.connect(temporary_path)
        target = sqlite3.connect(database_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        initialize_database(database_path)
    finally:
        if temporary_path:
            os.unlink(temporary_path)
    return current_backup
