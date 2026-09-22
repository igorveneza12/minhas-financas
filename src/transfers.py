"""Transferências internas entre contas, sem receitas ou despesas fictícias."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def create_transfer(
    source_account_id: int,
    destination_account_id: int,
    amount_cents: int,
    transfer_date: str | date,
    notes: str = "",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    if (
        not isinstance(source_account_id, int)
        or isinstance(source_account_id, bool)
        or not isinstance(destination_account_id, int)
        or isinstance(destination_account_id, bool)
        or source_account_id == destination_account_id
    ):
        raise ValueError("Selecione duas contas diferentes.")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise ValueError("O valor da transferência deve ser maior que zero.")
    try:
        day = transfer_date if isinstance(transfer_date, date) else date.fromisoformat(str(transfer_date))
    except ValueError as error:
        raise ValueError("Informe uma data válida.") from error

    with get_connection(database_path) as connection:
        rows = connection.execute(
            "SELECT id FROM accounts WHERE id IN (?, ?) AND active = 1",
            (source_account_id, destination_account_id),
        ).fetchall()
        if len(rows) != 2:
            raise ValueError("As contas de origem e destino precisam estar ativas.")
        cursor = connection.execute(
            """INSERT INTO transfers
               (source_account_id, destination_account_id, amount_cents, transfer_date, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (source_account_id, destination_account_id, amount_cents, day.isoformat(), notes.strip()),
        )
        return int(cursor.lastrowid)


def list_transfers(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """SELECT tr.*, src.name AS source_name, dst.name AS destination_name
               FROM transfers AS tr
               JOIN accounts AS src ON src.id = tr.source_account_id
               JOIN accounts AS dst ON dst.id = tr.destination_account_id
               ORDER BY tr.transfer_date DESC, tr.id DESC"""
        ).fetchall()


def delete_transfer(
    transfer_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    with get_connection(database_path) as connection:
        result = connection.execute("DELETE FROM transfers WHERE id = ?", (transfer_id,))
        if result.rowcount != 1:
            raise ValueError("Transferência não encontrada.")
