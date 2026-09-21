from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def upsert_budget(category_id: int, year: int, month: int, limit_cents: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    if limit_cents < 0 or month not in range(1, 13):
        raise ValueError("Informe um limite válido e um mês entre 1 e 12.")
    with get_connection(database_path) as connection:
        category = connection.execute("SELECT id FROM categories WHERE id = ? AND category_type = 'despesa' AND active = 1", (category_id,)).fetchone()
        if category is None:
            raise ValueError("A categoria de orçamento deve ser uma categoria de despesa ativa.")
        connection.execute("""INSERT INTO budgets (category_id, budget_year, budget_month, limit_cents) VALUES (?, ?, ?, ?)
            ON CONFLICT(category_id, budget_year, budget_month) DO UPDATE SET limit_cents = excluded.limit_cents""", (category_id, year, month, limit_cents))
        return int(connection.execute("SELECT id FROM budgets WHERE category_id = ? AND budget_year = ? AND budget_month = ?", (category_id, year, month)).fetchone()[0])


def delete_budget(budget_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        if connection.execute("DELETE FROM budgets WHERE id = ?", (budget_id,)).rowcount != 1:
            raise ValueError("Orçamento não encontrado.")


def copy_budgets(year: int, month: int, target_year: int, target_month: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    with get_connection(database_path) as connection:
        rows = connection.execute("SELECT category_id, limit_cents FROM budgets WHERE budget_year = ? AND budget_month = ?", (year, month)).fetchall()
        connection.executemany("""INSERT INTO budgets (category_id, budget_year, budget_month, limit_cents) VALUES (?, ?, ?, ?)
            ON CONFLICT(category_id, budget_year, budget_month) DO UPDATE SET limit_cents = excluded.limit_cents""", [(r["category_id"], target_year, target_month, r["limit_cents"]) for r in rows])
        return len(rows)


def list_budget_status(year: int, month: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute("""
            SELECT b.id, b.category_id, c.name AS category_name, b.limit_cents,
                   COALESCE(d.direct_cents, 0) + COALESCE(card.card_cents, 0) AS spent_cents
            FROM budgets b JOIN categories c ON c.id = b.category_id
            LEFT JOIN (SELECT category_id, SUM(amount_cents) direct_cents FROM transactions
                       WHERE transaction_type = 'despesa' AND strftime('%Y-%m', transaction_date) = ? GROUP BY category_id) d ON d.category_id = b.category_id
            LEFT JOIN (SELECT p.category_id, SUM(i.amount_cents) card_cents FROM card_installments i
                       JOIN card_invoices inv ON inv.id = i.invoice_id JOIN card_purchases p ON p.id = i.purchase_id
                       WHERE p.status = 'active' AND strftime('%Y-%m', inv.due_date) = ? GROUP BY p.category_id) card ON card.category_id = b.category_id
            WHERE b.budget_year = ? AND b.budget_month = ? ORDER BY c.name COLLATE NOCASE
        """, (f"{year:04d}-{month:02d}", f"{year:04d}-{month:02d}", year, month)).fetchall()


def budget_summary(year: int, month: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> dict[str, int]:
    rows = list_budget_status(year, month, database_path)
    return {"limit_cents": sum(r["limit_cents"] for r in rows), "spent_cents": sum(r["spent_cents"] for r in rows)}
