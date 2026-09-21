from calendar import monthrange
from datetime import date
from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def _safe_due(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def _month_range(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def create_recurring(description: str, category_id: int, account_id: int, expected_amount_cents: int, due_day: int, start_date: str | date, end_date: str | date | None = None, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    if not description.strip() or expected_amount_cents <= 0 or not 1 <= due_day <= 31:
        raise ValueError("Descrição, valor e dia de vencimento devem ser válidos.")
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end = date.fromisoformat(end_date) if isinstance(end_date, str) and end_date else end_date
    if end and end < start:
        raise ValueError("A data de término não pode ser anterior ao início.")
    with get_connection(database_path) as connection:
        if connection.execute("SELECT 1 FROM accounts WHERE id = ? AND active = 1", (account_id,)).fetchone() is None:
            raise ValueError("A conta selecionada não é válida.")
        if connection.execute("SELECT 1 FROM categories WHERE id = ? AND category_type = 'despesa' AND active = 1", (category_id,)).fetchone() is None:
            raise ValueError("A categoria selecionada não é uma despesa válida.")
        cursor = connection.execute("INSERT INTO recurring_expenses (description, category_id, account_id, expected_amount_cents, due_day, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)", (description.strip(), category_id, account_id, expected_amount_cents, due_day, start.isoformat(), end.isoformat() if end else None))
        return int(cursor.lastrowid)


def update_recurring(recurring_id: int, description: str, category_id: int, account_id: int, expected_amount_cents: int, due_day: int, end_date: str | None, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    if not description.strip() or expected_amount_cents <= 0 or not 1 <= due_day <= 31:
        raise ValueError("Dados inválidos para a recorrência.")
    with get_connection(database_path) as connection:
        if connection.execute("UPDATE recurring_expenses SET description = ?, category_id = ?, account_id = ?, expected_amount_cents = ?, due_day = ?, end_date = ? WHERE id = ? AND status != 'canceled'", (description.strip(), category_id, account_id, expected_amount_cents, due_day, end_date, recurring_id)).rowcount != 1:
            raise ValueError("Recorrência não encontrada ou cancelada.")


def set_recurring_status(recurring_id: int, status: str, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    if status not in {"active", "paused", "canceled"}:
        raise ValueError("Status inválido.")
    with get_connection(database_path) as connection:
        if connection.execute("UPDATE recurring_expenses SET status = ? WHERE id = ?", (status, recurring_id)).rowcount != 1:
            raise ValueError("Recorrência não encontrada.")


def archive_recurring(recurring_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Arquiva uma recorrência sem remover previsões ou histórico pago."""
    set_recurring_status(recurring_id, "paused", database_path)


def reactivate_recurring(recurring_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    set_recurring_status(recurring_id, "active", database_path)


def delete_recurring(recurring_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Remove o cadastro e previsões não pagas, preservando despesas já lançadas."""
    with get_connection(database_path) as connection:
        recurring = connection.execute(
            "SELECT id FROM recurring_expenses WHERE id = ?", (recurring_id,)
        ).fetchone()
        if recurring is None:
            raise ValueError("Recorrência não encontrada.")
        paid = connection.execute(
            """
            SELECT 1 FROM recurring_occurrences
            WHERE recurring_id = ? AND transaction_id IS NOT NULL
            LIMIT 1
            """,
            (recurring_id,),
        ).fetchone()
        if paid is not None:
            raise ValueError(
                "A recorrência possui pagamentos ou despesas vinculadas. Arquive ou cancele para preservar o histórico."
            )
        connection.execute(
            "DELETE FROM recurring_occurrences WHERE recurring_id = ? AND transaction_id IS NULL",
            (recurring_id,),
        )
        connection.execute("DELETE FROM recurring_expenses WHERE id = ?", (recurring_id,))


def generate_occurrences(year: int, month: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    created = 0
    with get_connection(database_path) as connection:
        rows = connection.execute("SELECT * FROM recurring_expenses WHERE status = 'active' AND start_date <= ? AND (end_date IS NULL OR end_date >= ?)", (month_end.isoformat(), month_start.isoformat())).fetchall()
        for row in rows:
            occurrence_month = f"{year:04d}-{month:02d}"
            due = _safe_due(year, month, row["due_day"])
            cursor = connection.execute("INSERT OR IGNORE INTO recurring_occurrences (recurring_id, reference_month, due_date, expected_amount_cents) VALUES (?, ?, ?, ?)", (row["id"], occurrence_month, due.isoformat(), row["expected_amount_cents"]))
            created += cursor.rowcount
    return created


def list_recurring(
    status: str = "Todos",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    """Lista as recorrências cadastradas, independentemente do mês selecionado."""
    filters = ""
    parameters: list[object] = []
    if status == "Ativas":
        filters = "WHERE r.status = 'active'"
    elif status == "Inativas":
        filters = "WHERE r.status IN ('paused', 'canceled')"
    elif status != "Todos":
        raise ValueError("Filtro de status inválido.")
    with get_connection(database_path) as connection:
        return connection.execute(
            f"""
            SELECT r.*, c.name AS category_name, a.name AS account_name
            FROM recurring_expenses AS r
            JOIN categories AS c ON c.id = r.category_id
            JOIN accounts AS a ON a.id = r.account_id
            {filters}
            ORDER BY r.status, r.description COLLATE NOCASE
            """,
            parameters,
        ).fetchall()


def list_occurrences(year: int, month: int, status: str | None = None, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    generate_occurrences(year, month, database_path)
    query = """SELECT o.*, r.description, r.category_id, r.account_id, r.status AS recurring_status, c.name category_name, a.name account_name
               FROM recurring_occurrences o JOIN recurring_expenses r ON r.id=o.recurring_id
               JOIN categories c ON c.id=r.category_id JOIN accounts a ON a.id=r.account_id
               WHERE o.reference_month = ?"""
    params: list[object] = [f"{year:04d}-{month:02d}"]
    if status == "Paga":
        query += " AND o.transaction_id IS NOT NULL"
    elif status == "Prevista":
        query += " AND o.transaction_id IS NULL AND o.due_date >= date('now')"
    elif status == "Vencida":
        query += " AND o.transaction_id IS NULL AND o.due_date < date('now')"
    query += " ORDER BY o.due_date, o.id"
    with get_connection(database_path) as connection:
        return connection.execute(query, params).fetchall()


def occurrence_status(row: sqlite3.Row, as_of: date | None = None) -> str:
    if row["transaction_id"] is not None:
        return "Paga"
    return "Vencida" if date.fromisoformat(row["due_date"]) < (as_of or date.today()) else "Prevista"


def pay_occurrence(occurrence_id: int, amount_cents: int, payment_date: str | date, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    if amount_cents <= 0:
        raise ValueError("O valor pago deve ser maior que zero.")
    payment_text = payment_date.isoformat() if isinstance(payment_date, date) else payment_date
    with get_connection(database_path) as connection:
        row = connection.execute("SELECT o.*, r.description, r.category_id, r.account_id FROM recurring_occurrences o JOIN recurring_expenses r ON r.id=o.recurring_id WHERE o.id = ?", (occurrence_id,)).fetchone()
        if row is None or row["transaction_id"] is not None:
            raise ValueError("Previsão inexistente ou já paga.")
        if connection.execute("SELECT 1 FROM accounts WHERE id = ? AND active = 1", (row["account_id"],)).fetchone() is None:
            raise ValueError("A conta da recorrência está arquivada.")
        cursor = connection.execute("INSERT INTO transactions (account_id, category_id, description, amount_cents, transaction_type, transaction_date, notes) VALUES (?, ?, ?, ?, 'despesa', ?, ?)", (row["account_id"], row["category_id"], row["description"], amount_cents, payment_text, f"Pagamento de recorrência; referência {row['reference_month']}"))
        connection.execute("UPDATE recurring_occurrences SET transaction_id = ? WHERE id = ?", (cursor.lastrowid, occurrence_id))
        return int(cursor.lastrowid)


def link_occurrence(occurrence_id: int, transaction_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        if connection.execute("SELECT 1 FROM transactions WHERE id = ? AND transaction_type = 'despesa'", (transaction_id,)).fetchone() is None:
            raise ValueError("Despesa não encontrada.")
        if connection.execute("UPDATE recurring_occurrences SET transaction_id = ?, linked_external = 1 WHERE id = ? AND transaction_id IS NULL", (transaction_id, occurrence_id)).rowcount != 1:
            raise ValueError("Previsão inexistente ou já vinculada.")


def recurring_summary(year: int, month: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> dict[str, int]:
    rows = list_occurrences(year, month, database_path=database_path)
    return {"previstas_cents": sum(r["expected_amount_cents"] for r in rows if r["transaction_id"] is None), "pagas_cents": sum(r["expected_amount_cents"] for r in rows if r["transaction_id"] is not None), "pendentes_cents": sum(r["expected_amount_cents"] for r in rows if r["transaction_id"] is None)}
