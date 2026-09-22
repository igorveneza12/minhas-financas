from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


ACCOUNT_TYPES = {
    "Conta corrente": "conta_corrente",
    "Poupança": "poupanca",
    "Dinheiro": "dinheiro",
    "Carteira digital": "carteira_digital",
}


def money_to_cents(value: object) -> int:
    """Converte um valor decimal em reais para centavos sem usar float."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Informe um valor monetário válido.")

    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        raise ValueError("Informe um valor monetário válido.")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Informe um valor monetário válido.") from error

    if not amount.is_finite():
        raise ValueError("Informe um valor monetário finito.")

    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(rounded * 100)


def cents_to_brl(cents: int) -> str:
    """Formata centavos como moeda brasileira."""
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    reais, centavos = divmod(absolute, 100)
    reais_text = f"{reais:,}".replace(",", ".")
    return f"{sign}R$ {reais_text},{centavos:02d}"


def create_account(
    name: str,
    account_type: str,
    initial_balance_cents: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """Cadastra uma conta e retorna o identificador criado."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("O nome da conta é obrigatório.")
    if account_type not in ACCOUNT_TYPES.values():
        raise ValueError("Tipo de conta inválido.")
    if not isinstance(initial_balance_cents, int) or isinstance(initial_balance_cents, bool):
        raise ValueError("O saldo inicial deve ser informado em centavos inteiros.")

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO accounts (name, account_type, initial_balance_cents)
            VALUES (?, ?, ?)
            """,
            (clean_name, account_type, initial_balance_cents),
        )
        return int(cursor.lastrowid)


def list_accounts(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    include_archived: bool = False,
) -> list[sqlite3.Row]:
    """Retorna contas com saldo calculado; por padrão, somente contas ativas."""
    active_filter = "" if include_archived else "WHERE a.active = 1"
    with get_connection(database_path) as connection:
        return connection.execute(
            f"""
            SELECT
                a.id,
                a.name,
                a.account_type,
                a.active,
                a.initial_balance_cents,
                COUNT(t.id) AS transaction_count,
                a.initial_balance_cents
                + COALESCE((
                    SELECT SUM(CASE
                        WHEN t.transaction_type = 'receita' THEN t.amount_cents
                        WHEN t.transaction_type = 'despesa' THEN -t.amount_cents
                        ELSE 0
                    END)
                    FROM transactions AS t WHERE t.account_id = a.id
                ), 0)
                - COALESCE((
                    SELECT SUM(tr.amount_cents)
                    FROM transfers AS tr WHERE tr.source_account_id = a.id
                ), 0)
                + COALESCE((
                    SELECT SUM(tr.amount_cents)
                    FROM transfers AS tr WHERE tr.destination_account_id = a.id
                ), 0)
                - COALESCE((
                    SELECT SUM(p.amount_cents)
                    FROM card_payments AS p WHERE p.account_id = a.id
                ), 0)
                - COALESCE((
                    SELECT SUM(p.amount_cents)
                    FROM debt_payments AS p WHERE p.account_id = a.id
                ), 0) AS balance_cents
            FROM accounts AS a
            LEFT JOIN transactions AS t ON t.account_id = a.id
            {active_filter}
            GROUP BY a.id
            ORDER BY a.name COLLATE NOCASE
            """
        ).fetchall()


def _account_transaction_count(connection: sqlite3.Connection, account_id: int) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS total FROM transactions WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    return int(row["total"])


def delete_account(
    account_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Exclui permanentemente somente contas sem movimentações."""
    with get_connection(database_path) as connection:
        account = connection.execute(
            "SELECT id, name FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if account is None:
            raise ValueError("Conta não encontrada.")
        if _account_transaction_count(connection, account_id):
            raise ValueError(
                "Esta conta possui movimentações e não pode ser excluída. Arquive-a para preservar o histórico."
            )
        connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def archive_account(
    account_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Arquiva uma conta sem remover seus registros financeiros."""
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "UPDATE accounts SET active = 0 WHERE id = ? AND active = 1",
            (account_id,),
        )
        if cursor.rowcount != 1:
            raise ValueError("Conta ativa não encontrada.")


def reactivate_account(
    account_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Reativa uma conta arquivada para novos lançamentos."""
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "UPDATE accounts SET active = 1 WHERE id = ? AND active = 0",
            (account_id,),
        )
        if cursor.rowcount != 1:
            raise ValueError("Conta arquivada não encontrada.")
