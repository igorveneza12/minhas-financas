from datetime import date
from pathlib import Path

from .database import DEFAULT_DATABASE_PATH, get_connection


def create_manual_payroll(
    employer: str,
    competence: str,
    payment_date: str | date,
    gross_cents: int,
    discounts_cents: int,
    net_cents: int,
    account_id: int,
    category_id: int,
    notes: str = "",
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    if not employer.strip() or not competence.strip():
        raise ValueError("Empregador e competência são obrigatórios.")
    if min(gross_cents, discounts_cents, net_cents) < 0:
        raise ValueError("Os valores do holerite não podem ser negativos.")
    if gross_cents - discounts_cents != net_cents:
        raise ValueError("Salário líquido deve ser igual ao bruto menos os descontos.")
    payment_text = payment_date.isoformat() if isinstance(payment_date, date) else payment_date
    with get_connection(database_path) as connection:
        account = connection.execute("SELECT id FROM accounts WHERE id = ? AND active = 1", (account_id,)).fetchone()
        category = connection.execute("SELECT id FROM categories WHERE id = ? AND category_type = 'receita' AND active = 1", (category_id,)).fetchone()
        if account is None:
            raise ValueError("A conta selecionada não é válida.")
        if category is None:
            raise ValueError("Selecione uma categoria de receita válida.")
        cursor = connection.execute("INSERT INTO transactions (account_id, category_id, description, amount_cents, transaction_type, transaction_date, notes) VALUES (?, ?, ?, ?, 'receita', ?, ?)", (account_id, category_id, f"Salário líquido - {employer.strip()}", net_cents, payment_text, "Receita originada de holerite; " + notes.strip()))
        transaction_id = int(cursor.lastrowid)
        slip = connection.execute("INSERT INTO payroll_slips (employer, competence, payment_date, gross_cents, discounts_cents, net_cents, transaction_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (employer.strip(), competence.strip(), payment_text, gross_cents, discounts_cents, net_cents, transaction_id, notes.strip()))
        return int(slip.lastrowid)
