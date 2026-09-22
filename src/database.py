from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "financeiro.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    account_type TEXT NOT NULL CHECK (
        account_type IN ('conta_corrente', 'poupanca', 'dinheiro', 'carteira_digital')
    ),
    initial_balance_cents INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_account_id INTEGER NOT NULL,
    destination_account_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    transfer_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_account_id <> destination_account_id),
    FOREIGN KEY (source_account_id) REFERENCES accounts (id),
    FOREIGN KEY (destination_account_id) REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    category_type TEXT NOT NULL CHECK (category_type IN ('receita', 'despesa')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name, category_type)
);

INSERT OR IGNORE INTO categories (name, category_type) VALUES
    ('Salário', 'receita'),
    ('Aulas particulares', 'receita'),
    ('Rendimentos', 'receita'),
    ('Outros recebimentos', 'receita'),
    ('Moradia', 'despesa'),
    ('Alimentação', 'despesa'),
    ('Transporte', 'despesa'),
    ('Saúde', 'despesa'),
    ('Educação', 'despesa'),
    ('Lazer', 'despesa'),
    ('Assinaturas', 'despesa'),
    ('Compras', 'despesa'),
    ('Outras despesas', 'despesa');

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('receita', 'despesa')),
    transaction_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts (id),
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

CREATE TRIGGER IF NOT EXISTS transactions_category_type_match_insert
BEFORE INSERT ON transactions
WHEN (SELECT category_type FROM categories WHERE id = NEW.category_id) <> NEW.transaction_type
BEGIN
    SELECT RAISE(ABORT, 'A categoria e a movimentação devem ter o mesmo tipo.');
END;

CREATE TRIGGER IF NOT EXISTS transactions_category_type_match_update
BEFORE UPDATE OF category_id, transaction_type ON transactions
WHEN (SELECT category_type FROM categories WHERE id = NEW.category_id) <> NEW.transaction_type
BEGIN
    SELECT RAISE(ABORT, 'A categoria e a movimentação devem ter o mesmo tipo.');
END;

CREATE TABLE IF NOT EXISTS credit_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    institution TEXT NOT NULL CHECK (length(trim(institution)) > 0),
    brand TEXT,
    limit_cents INTEGER NOT NULL CHECK (limit_cents >= 0),
    closing_day INTEGER NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    color TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS card_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    total_amount_cents INTEGER NOT NULL CHECK (total_amount_cents > 0),
    purchase_date TEXT NOT NULL,
    installments_count INTEGER NOT NULL CHECK (installments_count BETWEEN 1 AND 120),
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'canceled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES credit_cards (id),
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

CREATE TABLE IF NOT EXISTS card_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    billing_year INTEGER NOT NULL CHECK (billing_year BETWEEN 2000 AND 2100),
    billing_month INTEGER NOT NULL CHECK (billing_month BETWEEN 1 AND 12),
    closing_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    UNIQUE (card_id, billing_year, billing_month),
    FOREIGN KEY (card_id) REFERENCES credit_cards (id)
);

CREATE TABLE IF NOT EXISTS card_installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL,
    invoice_id INTEGER NOT NULL,
    installment_number INTEGER NOT NULL CHECK (installment_number >= 1),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    FOREIGN KEY (purchase_id) REFERENCES card_purchases (id),
    FOREIGN KEY (invoice_id) REFERENCES card_invoices (id),
    UNIQUE (purchase_id, installment_number)
);

CREATE TABLE IF NOT EXISTS card_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    payment_date TEXT NOT NULL,
    notes TEXT,
    operation_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES card_invoices (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    budget_year INTEGER NOT NULL CHECK (budget_year BETWEEN 2000 AND 2100),
    budget_month INTEGER NOT NULL CHECK (budget_month BETWEEN 1 AND 12),
    limit_cents INTEGER NOT NULL CHECK (limit_cents >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category_id, budget_year, budget_month),
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    creditor TEXT NOT NULL CHECK (length(trim(creditor)) > 0),
    initial_amount_cents INTEGER NOT NULL CHECK (initial_amount_cents >= 0),
    principal_remaining_cents INTEGER NOT NULL CHECK (principal_remaining_cents >= 0),
    reference_date TEXT NOT NULL,
    contracted_date TEXT,
    due_date TEXT,
    installments_count INTEGER CHECK (installments_count IS NULL OR installments_count > 0),
    installment_amount_cents INTEGER CHECK (installment_amount_cents IS NULL OR installment_amount_cents >= 0),
    interest_rate TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    principal_cents INTEGER NOT NULL CHECK (principal_cents >= 0),
    interest_cents INTEGER NOT NULL DEFAULT 0 CHECK (interest_cents >= 0),
    payment_date TEXT NOT NULL,
    notes TEXT,
    operation_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY (debt_id) REFERENCES debts (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS financial_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    target_cents INTEGER NOT NULL CHECK (target_cents > 0),
    reserved_cents INTEGER NOT NULL DEFAULT 0 CHECK (reserved_cents >= 0),
    start_date TEXT NOT NULL,
    target_date TEXT,
    monthly_plan_cents INTEGER CHECK (monthly_plan_cents IS NULL OR monthly_plan_cents >= 0),
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_hash TEXT NOT NULL UNIQUE,
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    transaction_id INTEGER NOT NULL,
    account_id INTEGER,
    external_id TEXT,
    FOREIGN KEY (batch_id) REFERENCES import_batches (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS payroll_slips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer TEXT NOT NULL CHECK (length(trim(employer)) > 0),
    competence TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    gross_cents INTEGER NOT NULL CHECK (gross_cents >= 0),
    discounts_cents INTEGER NOT NULL CHECK (discounts_cents >= 0),
    net_cents INTEGER NOT NULL CHECK (net_cents >= 0),
    transaction_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions (id)
);

CREATE TABLE IF NOT EXISTS recurring_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    category_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    expected_amount_cents INTEGER NOT NULL CHECK (expected_amount_cents > 0),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    start_date TEXT NOT NULL,
    end_date TEXT,
    frequency_months INTEGER NOT NULL DEFAULT 1 CHECK (frequency_months = 1),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'canceled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS recurring_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recurring_id INTEGER NOT NULL,
    reference_month TEXT NOT NULL,
    due_date TEXT NOT NULL,
    expected_amount_cents INTEGER NOT NULL CHECK (expected_amount_cents > 0),
    transaction_id INTEGER,
    linked_external INTEGER NOT NULL DEFAULT 0 CHECK (linked_external IN (0, 1)),
    UNIQUE (recurring_id, reference_month),
    FOREIGN KEY (recurring_id) REFERENCES recurring_expenses (id),
    FOREIGN KEY (transaction_id) REFERENCES transactions (id)
);
"""


def get_connection(database_path: str | Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Abre uma conexão SQLite com integridade referencial ativada."""
    path = Path(database_path)
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Cria as tabelas ausentes sem modificar registros existentes."""
    with get_connection(database_path) as connection:
        connection.executescript(SCHEMA)
