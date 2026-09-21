from datetime import date
from pathlib import Path
import sqlite3

from .accounts import money_to_cents
from .database import DEFAULT_DATABASE_PATH, get_connection


TRANSACTION_TYPES = {"Receita": "receita", "Despesa": "despesa"}


def _validate_transaction(
    description: str,
    amount_cents: int,
    transaction_type: str,
    account_id: int,
    category_id: int,
) -> str:
    clean_description = description.strip()
    if not clean_description:
        raise ValueError("A descrição é obrigatória.")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise ValueError("O valor deve ser maior que zero.")
    if transaction_type not in TRANSACTION_TYPES.values():
        raise ValueError("Tipo de movimentação inválido.")
    if not isinstance(account_id, int) or not isinstance(category_id, int):
        raise ValueError("Informe uma conta e uma categoria válidas.")
    return clean_description


def create_transaction(
    description: str,
    amount_cents: int,
    transaction_type: str,
    transaction_date: str | date,
    account_id: int,
    category_id: int,
    notes: str = "",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    clean_description = _validate_transaction(
        description, amount_cents, transaction_type, account_id, category_id
    )
    date_text = transaction_date.isoformat() if isinstance(transaction_date, date) else str(transaction_date)

    with get_connection(database_path) as connection:
        account = connection.execute(
            "SELECT id FROM accounts WHERE id = ? AND active = 1", (account_id,)
        ).fetchone()
        category = connection.execute(
            "SELECT category_type FROM categories WHERE id = ? AND active = 1", (category_id,)
        ).fetchone()
        if account is None:
            raise ValueError("A conta selecionada não é válida.")
        if category is None or category["category_type"] != transaction_type:
            raise ValueError("A categoria precisa ser compatível com o tipo da movimentação.")

        cursor = connection.execute(
            """
            INSERT INTO transactions
                (account_id, category_id, description, amount_cents, transaction_type,
                 transaction_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, category_id, clean_description, amount_cents, transaction_type, date_text, notes.strip()),
        )
        return int(cursor.lastrowid)


def update_transaction(
    transaction_id: int,
    description: str,
    amount_cents: int,
    transaction_type: str,
    transaction_date: str | date,
    account_id: int,
    category_id: int,
    notes: str = "",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    clean_description = _validate_transaction(
        description, amount_cents, transaction_type, account_id, category_id
    )
    date_text = transaction_date.isoformat() if isinstance(transaction_date, date) else str(transaction_date)

    with get_connection(database_path) as connection:
        category = connection.execute(
            "SELECT category_type FROM categories WHERE id = ? AND active = 1", (category_id,)
        ).fetchone()
        if category is None or category["category_type"] != transaction_type:
            raise ValueError("A categoria precisa ser compatível com o tipo da movimentação.")
        cursor = connection.execute(
            """
            UPDATE transactions
            SET description = ?, amount_cents = ?, transaction_type = ?, transaction_date = ?,
                account_id = ?, category_id = ?, notes = ?
            WHERE id = ?
            """,
            (clean_description, amount_cents, transaction_type, date_text, account_id, category_id, notes.strip(), transaction_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Movimentação não encontrada.")


def delete_transaction(transaction_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        if cursor.rowcount != 1:
            raise ValueError("Movimentação não encontrada.")


def list_transactions(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    year: int | None = None,
    month: int | None = None,
    transaction_type: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
) -> list[sqlite3.Row]:
    query = """
        SELECT t.*, a.name AS account_name, c.name AS category_name
        FROM transactions AS t
        JOIN accounts AS a ON a.id = t.account_id
        JOIN categories AS c ON c.id = t.category_id
        WHERE 1 = 1
    """
    parameters: list[object] = []
    if year is not None and month is not None:
        query += " AND strftime('%Y-%m', t.transaction_date) = ?"
        parameters.append(f"{year:04d}-{month:02d}")
    if transaction_type:
        query += " AND t.transaction_type = ?"
        parameters.append(transaction_type)
    if account_id:
        query += " AND t.account_id = ?"
        parameters.append(account_id)
    if category_id:
        query += " AND t.category_id = ?"
        parameters.append(category_id)
    query += " ORDER BY t.transaction_date DESC, t.id DESC"

    with get_connection(database_path) as connection:
        return connection.execute(query, parameters).fetchall()


def monthly_totals(
    year: int,
    month: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> dict[str, int]:
    rows = list_transactions(database_path, year=year, month=month)
    return {
        "receita": sum(row["amount_cents"] for row in rows if row["transaction_type"] == "receita"),
        "despesa": sum(row["amount_cents"] for row in rows if row["transaction_type"] == "despesa"),
    }


def total_balance_cents(database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE((SELECT SUM(initial_balance_cents) FROM accounts), 0)
                + COALESCE((
                    SELECT SUM(CASE
                        WHEN t.transaction_type = 'receita' THEN t.amount_cents
                        WHEN t.transaction_type = 'despesa' THEN -t.amount_cents
                        ELSE 0
                    END)
                    FROM transactions AS t
                    JOIN accounts AS a ON a.id = t.account_id
                ), 0)
                - COALESCE((SELECT SUM(amount_cents) FROM card_payments), 0)
                - COALESCE((SELECT SUM(amount_cents) FROM debt_payments), 0) AS total
            """
        ).fetchone()
        return int(row["total"])


def monthly_expenses_by_category(
    year: int,
    month: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT c.name AS category_name, COALESCE(SUM(t.amount_cents), 0) AS total_cents
            FROM categories AS c
            LEFT JOIN transactions AS t ON t.category_id = c.id
                AND t.transaction_type = 'despesa'
                AND strftime('%Y-%m', t.transaction_date) = ?
            WHERE c.category_type = 'despesa' AND c.active = 1
            GROUP BY c.id
            HAVING total_cents > 0
            ORDER BY total_cents DESC
            """,
            (f"{year:04d}-{month:02d}",),
        ).fetchall()


def monthly_comparison(
    year: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            WITH months(month_number) AS (
                VALUES (1), (2), (3), (4), (5), (6),
                       (7), (8), (9), (10), (11), (12)
            )
            SELECT
                printf('%04d-%02d', ?, months.month_number) AS month,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'receita' THEN t.amount_cents ELSE 0 END), 0) AS receitas_cents,
                COALESCE(SUM(CASE WHEN t.transaction_type = 'despesa' THEN t.amount_cents ELSE 0 END), 0) AS despesas_cents
            FROM months
            LEFT JOIN transactions AS t
                ON strftime('%Y', t.transaction_date) = printf('%04d', ?)
                AND CAST(strftime('%m', t.transaction_date) AS INTEGER) = months.month_number
            GROUP BY months.month_number
            ORDER BY months.month_number
            """,
            (year, year),
        ).fetchall()
