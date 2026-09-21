from pathlib import Path
import sqlite3

from .database import DEFAULT_DATABASE_PATH, get_connection


CATEGORY_TYPES = {"Receita": "receita", "Despesa": "despesa"}
DEFAULT_CATEGORIES = {
    "receita": ("Salário", "Aulas particulares", "Rendimentos", "Outros recebimentos"),
    "despesa": (
        "Moradia",
        "Alimentação",
        "Transporte",
        "Saúde",
        "Educação",
        "Lazer",
        "Assinaturas",
        "Compras",
        "Outras despesas",
    ),
}


def seed_default_categories(database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    with get_connection(database_path) as connection:
        for category_type, names in DEFAULT_CATEGORIES.items():
            connection.executemany(
                "INSERT OR IGNORE INTO categories (name, category_type) VALUES (?, ?)",
                [(name, category_type) for name in names],
            )


def create_category(
    name: str,
    category_type: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("O nome da categoria é obrigatório.")
    if category_type not in DEFAULT_CATEGORIES:
        raise ValueError("Tipo de categoria inválido.")

    try:
        with get_connection(database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO categories (name, category_type) VALUES (?, ?)",
                (clean_name, category_type),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        if "UNIQUE" in str(error).upper():
            raise ValueError("Já existe uma categoria com esse nome e tipo.") from error
        raise


def list_categories(
    category_type: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[sqlite3.Row]:
    query = "SELECT id, name, category_type, active FROM categories WHERE active = 1"
    parameters: tuple[str, ...] = ()
    if category_type is not None:
        if category_type not in DEFAULT_CATEGORIES:
            raise ValueError("Tipo de categoria inválido.")
        query += " AND category_type = ?"
        parameters = (category_type,)
    query += " ORDER BY name COLLATE NOCASE"

    with get_connection(database_path) as connection:
        return connection.execute(query, parameters).fetchall()
