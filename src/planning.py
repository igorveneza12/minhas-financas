from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


def monthly_planning(year: int, database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[sqlite3.Row]:
    with get_connection(database_path) as connection:
        return connection.execute("""
            WITH months(month_number) AS (VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12))
            SELECT printf('%04d-%02d', ?, month_number) AS month,
                   COALESCE((SELECT SUM(limit_cents) FROM budgets WHERE budget_year = ? AND budget_month = month_number), 0) AS budget_cents,
                   COALESCE((SELECT SUM(i.amount_cents) FROM card_installments i JOIN card_invoices inv ON inv.id=i.invoice_id JOIN card_purchases p ON p.id=i.purchase_id WHERE p.status='active' AND strftime('%Y-%m', inv.due_date)=printf('%04d-%02d', ?, month_number)), 0) AS card_cents,
                   COALESCE((SELECT SUM(d.installment_amount_cents) FROM debts d WHERE d.active=1 AND d.installment_amount_cents IS NOT NULL AND d.due_date IS NOT NULL AND strftime('%Y-%m', d.due_date)=printf('%04d-%02d', ?, month_number)), 0) AS debt_cents,
                   COALESCE((SELECT SUM(g.monthly_plan_cents) FROM financial_goals g WHERE g.active=1 AND g.monthly_plan_cents IS NOT NULL), 0) AS goals_cents
            FROM months ORDER BY month_number
        """, (year, year, year, year)).fetchall()
