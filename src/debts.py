from datetime import date
from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def create_debt(name: str, creditor: str, initial_amount_cents: int, principal_remaining_cents: int, reference_date: str | date, contracted_date: str | date | None = None, due_date: str | date | None = None, installments_count: int | None = None, installment_amount_cents: int | None = None, interest_rate: str | None = None, notes: str = "", database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    if not name.strip() or not creditor.strip():
        raise ValueError("Nome e credor são obrigatórios.")
    if initial_amount_cents < 0 or principal_remaining_cents < 0 or principal_remaining_cents > initial_amount_cents:
        raise ValueError("Os valores da dívida são inválidos.")
    def iso(value): return value.isoformat() if isinstance(value, date) else value
    with get_connection(database_path) as connection:
        cursor = connection.execute("""INSERT INTO debts (name, creditor, initial_amount_cents, principal_remaining_cents, reference_date, contracted_date, due_date, installments_count, installment_amount_cents, interest_rate, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (name.strip(), creditor.strip(), initial_amount_cents, principal_remaining_cents, iso(reference_date), iso(contracted_date), iso(due_date), installments_count, installment_amount_cents, interest_rate, notes.strip()))
        return int(cursor.lastrowid)


def update_debt(debt_id: int, name: str, creditor: str, principal_remaining_cents: int, due_date: str | None, notes: str, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    if not name.strip() or not creditor.strip() or principal_remaining_cents < 0:
        raise ValueError("Informe dados válidos para a dívida.")
    with get_connection(database_path) as connection:
        if connection.execute("UPDATE debts SET name = ?, creditor = ?, principal_remaining_cents = ?, due_date = ?, notes = ? WHERE id = ?", (name.strip(), creditor.strip(), principal_remaining_cents, due_date, notes.strip(), debt_id)).rowcount != 1:
            raise ValueError("Dívida não encontrada.")


def list_debts(database_path: str | Path = DEFAULT_DATABASE_PATH, include_archived: bool = False) -> list[sqlite3.Row]:
    where = "" if include_archived else "WHERE d.active = 1"
    with get_connection(database_path) as connection:
        return connection.execute(f"""SELECT d.*, COALESCE((SELECT SUM(amount_cents) FROM debt_payments p WHERE p.debt_id = d.id), 0) paid_cents,
            COALESCE((SELECT SUM(principal_cents) FROM debt_payments p WHERE p.debt_id = d.id), 0) principal_paid_cents
            FROM debts d {where} ORDER BY d.due_date IS NULL, d.due_date""").fetchall()


def archive_debt(debt_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        if connection.execute("UPDATE debts SET active = 0 WHERE id = ?", (debt_id,)).rowcount != 1:
            raise ValueError("Dívida não encontrada.")


def create_debt_payment(debt_id: int, account_id: int, amount_cents: int, principal_cents: int, interest_cents: int, payment_date: str | date, notes: str = "", operation_key: str | None = None, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    if amount_cents <= 0 or principal_cents < 0 or interest_cents < 0 or principal_cents + interest_cents != amount_cents:
        raise ValueError("O pagamento deve separar corretamente principal e juros.")
    def iso(value): return value.isoformat() if isinstance(value, date) else value
    key = operation_key or f"debt-{debt_id}-{account_id}-{iso(payment_date)}-{amount_cents}"
    with get_connection(database_path) as connection:
        debt = connection.execute("SELECT principal_remaining_cents FROM debts WHERE id = ? AND active = 1", (debt_id,)).fetchone()
        account = connection.execute("SELECT id FROM accounts WHERE id = ? AND active = 1", (account_id,)).fetchone()
        if debt is None: raise ValueError("Dívida ativa não encontrada.")
        if account is None: raise ValueError("A conta está arquivada ou não existe.")
        if principal_cents > debt["principal_remaining_cents"]: raise ValueError("A amortização supera o saldo devedor.")
        if connection.execute("SELECT 1 FROM debt_payments WHERE operation_key = ?", (key,)).fetchone(): raise ValueError("Este pagamento já foi registrado.")
        cursor = connection.execute("""INSERT INTO debt_payments (debt_id, account_id, amount_cents, principal_cents, interest_cents, payment_date, notes, operation_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (debt_id, account_id, amount_cents, principal_cents, interest_cents, iso(payment_date), notes.strip(), key))
        connection.execute("UPDATE debts SET principal_remaining_cents = principal_remaining_cents - ? WHERE id = ?", (principal_cents, debt_id))
        return int(cursor.lastrowid)


def list_debt_payments(debt_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute("SELECT p.*, a.name account_name FROM debt_payments p JOIN accounts a ON a.id = p.account_id WHERE debt_id = ? ORDER BY payment_date DESC, p.id DESC", (debt_id,)).fetchall()


def debt_totals(database_path: str | Path = DEFAULT_DATABASE_PATH) -> dict[str, int]:
    return {"principal_cents": sum(r["principal_remaining_cents"] for r in list_debts(database_path))}
