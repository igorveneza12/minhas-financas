from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, list_accounts, money_to_cents
from src.categories import list_categories
from src.database import DEFAULT_DATABASE_PATH
from src.transactions import (
    TRANSACTION_TYPES,
    create_transaction,
    delete_transaction,
    list_transactions,
    update_transaction,
)


st.header("Movimentações")
accounts = list_accounts(DEFAULT_DATABASE_PATH)

def clear_category(key: str) -> None:
    st.session_state.pop(key, None)


if not accounts:
    st.warning("Cadastre uma conta antes de registrar uma movimentação.")
else:
    account_options = {row["name"]: row["id"] for row in accounts}
    type_label = st.selectbox(
        "Tipo",
        list(TRANSACTION_TYPES),
        key="new_transaction_type",
        on_change=clear_category,
        args=("new_transaction_category",),
    )
    transaction_type = TRANSACTION_TYPES[type_label]
    categories = list_categories(transaction_type, DEFAULT_DATABASE_PATH)
    category_options = {row["name"]: row["id"] for row in categories}
    with st.form("transaction_form", clear_on_submit=True):
        description = st.text_input("Descrição")
        amount = st.text_input("Valor", placeholder="0,00")
        movement_date = st.date_input("Data da movimentação", value=date.today())
        account_name = st.selectbox("Conta financeira", list(account_options))
        category_name = st.selectbox("Categoria", list(category_options), key="new_transaction_category")
        notes = st.text_area("Observações (opcional)")
        submitted = st.form_submit_button("Cadastrar movimentação", type="primary")

    if submitted:
        try:
            create_transaction(
                description,
                money_to_cents(amount),
                transaction_type,
                movement_date,
                account_options[account_name],
                category_options[category_name],
                notes,
                DEFAULT_DATABASE_PATH,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))
        else:
            st.success("Movimentação cadastrada com sucesso.")

st.divider()
st.subheader("Lançamentos")
filter_year = st.number_input("Ano", min_value=2000, max_value=2100, value=date.today().year, step=1)
filter_month = st.selectbox("Mês", ["Todos"] + list(range(1, 13)), format_func=lambda value: value if value == "Todos" else f"{value:02d}")
filter_type_label = st.selectbox("Tipo", ["Todos"] + list(TRANSACTION_TYPES))
filter_account = st.selectbox("Conta", ["Todas"] + list({row["name"] for row in accounts}))
filter_category = st.selectbox("Categoria", ["Todas"] + [row["name"] for row in list_categories(database_path=DEFAULT_DATABASE_PATH)])

account_id = next((row["id"] for row in accounts if row["name"] == filter_account), None) if filter_account != "Todas" else None
category_id = next((row["id"] for row in list_categories(database_path=DEFAULT_DATABASE_PATH) if row["name"] == filter_category), None) if filter_category != "Todas" else None
rows = list_transactions(
    DEFAULT_DATABASE_PATH,
    year=int(filter_year) if filter_month != "Todos" else None,
    month=int(filter_month) if filter_month != "Todos" else None,
    transaction_type=TRANSACTION_TYPES.get(filter_type_label),
    account_id=account_id,
    category_id=category_id,
)

if rows:
    st.dataframe(
        pd.DataFrame([
            {
                "Data": row["transaction_date"],
                "Tipo": "Receita" if row["transaction_type"] == "receita" else "Despesa",
                "Descrição": row["description"],
                "Conta": row["account_name"],
                "Categoria": row["category_name"],
                "Valor": cents_to_brl(row["amount_cents"]),
                "Observações": row["notes"] or "",
            }
            for row in rows
        ]),
        hide_index=True,
        width="stretch",
    )

    transaction_options = {
        f"{row['transaction_date']} | {row['description']} | {cents_to_brl(row['amount_cents'])} | #{row['id']}": row
        for row in rows
    }
    selected_label = st.selectbox("Movimentação para editar ou excluir", list(transaction_options))
    selected = transaction_options[selected_label]
    selected_type_label = "Receita" if selected["transaction_type"] == "receita" else "Despesa"

    edit_type_key = f"edit_transaction_type_{selected['id']}"
    edit_category_key = f"edit_transaction_category_{selected['id']}"
    if edit_type_key not in st.session_state:
        st.session_state[edit_type_key] = selected_type_label
    edit_type_label = st.selectbox(
        "Tipo",
        list(TRANSACTION_TYPES),
        key=edit_type_key,
        on_change=clear_category,
        args=(edit_category_key,),
    )
    edit_categories = list_categories(TRANSACTION_TYPES[edit_type_label], DEFAULT_DATABASE_PATH)
    edit_category_options = {row["name"]: row["id"] for row in edit_categories}
    if edit_category_key not in st.session_state:
        st.session_state[edit_category_key] = (
            next(
                name for name, category_id in edit_category_options.items()
                if category_id == selected["category_id"]
            )
            if selected["category_id"] in edit_category_options.values()
            else next(iter(edit_category_options), "")
        )

    with st.form("edit_transaction_form"):
        edit_description = st.text_input("Descrição", value=selected["description"])
        edit_amount = st.text_input("Valor", value=cents_to_brl(selected["amount_cents"]).replace("R$ ", ""))
        edit_date = st.date_input("Data da movimentação", value=date.fromisoformat(selected["transaction_date"]))
        edit_account_name = st.selectbox(
            "Conta financeira",
            list(account_options),
            index=list(account_options.values()).index(selected["account_id"]),
        )
        edit_category_name = st.selectbox(
            "Categoria",
            list(edit_category_options),
            key=edit_category_key,
        )
        edit_notes = st.text_area("Observações (opcional)", value=selected["notes"] or "")
        edit_submitted = st.form_submit_button("Salvar alterações", type="primary")

    if edit_submitted:
        try:
            update_transaction(
                selected["id"],
                edit_description,
                money_to_cents(edit_amount),
                TRANSACTION_TYPES[edit_type_label],
                edit_date,
                account_options[edit_account_name],
                edit_category_options[edit_category_name],
                edit_notes,
                DEFAULT_DATABASE_PATH,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))
        else:
            st.success("Movimentação atualizada com sucesso.")
            st.rerun()

    confirm_delete = st.checkbox("Confirmo a exclusão desta movimentação.", key="confirm_delete")
    if st.button("Excluir movimentação", type="secondary", disabled=not confirm_delete):
        try:
            delete_transaction(selected["id"], DEFAULT_DATABASE_PATH)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Movimentação excluída com sucesso.")
            st.rerun()
else:
    st.info("Nenhuma movimentação encontrada para os filtros selecionados.")
