from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def recent_transactions(
    limit: int = 10,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT t.*, a.name AS account_name, c.name AS category_name
            FROM transactions AS t
            JOIN accounts AS a ON a.id = t.account_id
            JOIN categories AS c ON c.id = t.category_id
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
