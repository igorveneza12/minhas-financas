from datetime import date
from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def create_goal(name: str, target_cents: int, reserved_cents: int, start_date: str | date, target_date: str | date | None = None, monthly_plan_cents: int | None = None, notes: str = "", database_path: str | Path = DEFAULT_DATABASE_PATH) -> int:
    if not name.strip() or target_cents <= 0 or reserved_cents < 0:
        raise ValueError("Nome, objetivo e valor reservado devem ser válidos.")
    def iso(value): return value.isoformat() if isinstance(value, date) else value
    with get_connection(database_path) as connection:
        cursor = connection.execute("INSERT INTO financial_goals (name, target_cents, reserved_cents, start_date, target_date, monthly_plan_cents, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", (name.strip(), target_cents, reserved_cents, iso(start_date), iso(target_date), monthly_plan_cents, notes.strip()))
        return int(cursor.lastrowid)


def update_goal(goal_id: int, name: str, target_cents: int, reserved_cents: int, target_date: str | None, monthly_plan_cents: int | None, notes: str, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    if not name.strip() or target_cents <= 0 or reserved_cents < 0:
        raise ValueError("Dados inválidos para a meta.")
    with get_connection(database_path) as connection:
        if connection.execute("UPDATE financial_goals SET name = ?, target_cents = ?, reserved_cents = ?, target_date = ?, monthly_plan_cents = ?, notes = ? WHERE id = ?", (name.strip(), target_cents, reserved_cents, target_date, monthly_plan_cents, notes.strip(), goal_id)).rowcount != 1: raise ValueError("Meta não encontrada.")


def list_goals(database_path: str | Path = DEFAULT_DATABASE_PATH, include_archived: bool = False) -> list[sqlite3.Row]:
    where = "" if include_archived else "WHERE active = 1"
    with get_connection(database_path) as connection:
        return connection.execute(f"SELECT * FROM financial_goals {where} ORDER BY target_date IS NULL, target_date", ()).fetchall()


def archive_goal(goal_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        if connection.execute("UPDATE financial_goals SET active = 0 WHERE id = ?", (goal_id,)).rowcount != 1: raise ValueError("Meta não encontrada.")


def delete_goal(goal_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Exclui apenas metas sem valores reservados; reserva manual exige arquivamento."""
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT reserved_cents FROM financial_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Meta não encontrada.")
        if row["reserved_cents"] > 0:
            raise ValueError("Meta com valor reservado: arquive-a para preservar o histórico.")
        connection.execute("DELETE FROM financial_goals WHERE id = ?", (goal_id,))


def reactivate_goal(goal_id: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        if connection.execute(
            "UPDATE financial_goals SET active = 1 WHERE id = ? AND active = 0", (goal_id,)
        ).rowcount != 1:
            raise ValueError("Meta arquivada não encontrada.")


def goal_progress(row: sqlite3.Row | dict) -> dict[str, int | float]:
    target = int(row["target_cents"])
    reserved = int(row["reserved_cents"])
    percent = min(reserved / target * 100, 100) if target else 0
    remaining = max(target - reserved, 0)
    monthly = None
    if row["target_date"] and remaining:
        end = date.fromisoformat(row["target_date"])
        start = date.today()
        months = max((end.year - start.year) * 12 + end.month - start.month + (1 if end.day >= start.day else 0), 1)
        monthly = (remaining + months - 1) // months
    return {"percent": percent, "remaining_cents": remaining, "monthly_needed_cents": monthly}


def goals_summary(database_path: str | Path = DEFAULT_DATABASE_PATH) -> dict[str, int]:
    rows = list_goals(database_path)
    return {"target_cents": sum(r["target_cents"] for r in rows), "reserved_cents": sum(r["reserved_cents"] for r in rows)}
