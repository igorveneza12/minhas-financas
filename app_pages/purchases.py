from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, money_to_cents
from src.categories import list_categories
from src.credit_cards import (
    cancel_purchase,
    create_purchase,
    list_cards,
    list_purchases,
    purchase_installments,
    update_purchase,
)
from src.database import DEFAULT_DATABASE_PATH


st.header("Compras no cartão")
active_cards = list_cards(DEFAULT_DATABASE_PATH)
categories = list_categories("despesa", DEFAULT_DATABASE_PATH)

if not active_cards:
    st.warning("Cadastre um cartão ativo antes de registrar compras.")
elif not categories:
    st.warning("Cadastre ao menos uma categoria de despesa.")
else:
    card_options = {card["name"]: card["id"] for card in active_cards}
    category_options = {category["name"]: category["id"] for category in categories}
    with st.form("purchase_form", clear_on_submit=True):
        card_name = st.selectbox("Cartão utilizado", list(card_options))
        description = st.text_input("Descrição da compra")
        total = st.text_input("Valor total", placeholder="0,00")
        purchase_date = st.date_input("Data da compra", value=date.today())
        category_name = st.selectbox("Categoria da despesa", list(category_options))
        installments = st.number_input("Número de parcelas", min_value=1, max_value=120, value=1, step=1)
        notes = st.text_area("Observações (opcional)")
        submitted = st.form_submit_button("Registrar compra", type="primary")
    if submitted:
        try:
            create_purchase(
                card_options[card_name], description, money_to_cents(total), purchase_date,
                category_options[category_name], int(installments), notes, DEFAULT_DATABASE_PATH,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))
        else:
            st.success("Compra registrada e parcelas distribuídas nas faturas.")
            st.rerun()

st.divider()
st.subheader("Compras registradas")
all_purchases = list_purchases(DEFAULT_DATABASE_PATH)
if all_purchases:
    st.dataframe(
        pd.DataFrame([
            {
                "Cartão": row["card_name"],
                "Descrição": row["description"],
                "Data": row["purchase_date"],
                "Categoria": row["category_name"],
                "Valor total": cents_to_brl(row["total_amount_cents"]),
                "Parcelas": row["installment_count"],
            }
            for row in all_purchases
        ]),
        hide_index=True,
        width="stretch",
    )
    purchase_options = {
        f"#{row['id']} | {row['description']} | {row['card_name']} | {cents_to_brl(row['total_amount_cents'])}": row
        for row in all_purchases
    }
    selected_label = st.selectbox("Compra para consultar ou editar", list(purchase_options))
    selected = purchase_options[selected_label]
    with st.expander("Detalhes das parcelas", expanded=True):
        installments_rows = purchase_installments(selected["id"], DEFAULT_DATABASE_PATH)
        st.dataframe(
            pd.DataFrame([
                {
                    "Parcela": row["installment_number"],
                    "Valor": cents_to_brl(row["amount_cents"]),
                    "Vencimento": row["due_date"],
                    "Status": "Paga" if row["invoice_paid_cents"] >= row["amount_cents"] else "Em aberto",
                }
                for row in installments_rows
            ]),
            hide_index=True,
            width="stretch",
        )

    card_by_name = {card["name"]: card["id"] for card in active_cards}
    category_by_name = {category["name"]: category["id"] for category in categories}
    with st.form("edit_purchase_form"):
        edit_description = st.text_input("Descrição", value=selected["description"])
        edit_total = st.text_input("Valor total", value=cents_to_brl(selected["total_amount_cents"]).replace("R$ ", ""))
        edit_date = st.date_input("Data da compra", value=date.fromisoformat(selected["purchase_date"]))
        edit_category = st.selectbox("Categoria", list(category_by_name), index=list(category_by_name.values()).index(selected["category_id"]))
        edit_installments = st.number_input("Parcelas", min_value=1, max_value=120, value=selected["installments_count"], step=1)
        edit_notes = st.text_area("Observações", value=selected["notes"] or "")
        edit_submitted = st.form_submit_button("Salvar alterações")
    if edit_submitted:
        try:
            update_purchase(selected["id"], edit_description, money_to_cents(edit_total), edit_date, category_by_name[edit_category], int(edit_installments), edit_notes, DEFAULT_DATABASE_PATH)
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))
        else:
            st.success("Compra atualizada.")
            st.rerun()

    if st.button("Cancelar compra", key=f"cancel_purchase_{selected['id']}"):
        st.session_state["purchase_pending_cancel"] = selected["id"]
    if st.session_state.get("purchase_pending_cancel") == selected["id"]:
        st.warning("O cancelamento remove as parcelas ainda não pagas, mas nunca apaga pagamentos existentes.")
        confirmed = st.checkbox("Confirmo o cancelamento desta compra.", key=f"confirm_cancel_{selected['id']}")
        if st.button("Confirmar cancelamento", key=f"confirm_cancel_button_{selected['id']}", disabled=not confirmed):
            try:
                cancel_purchase(selected["id"], DEFAULT_DATABASE_PATH)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Compra cancelada.")
                st.session_state.pop("purchase_pending_cancel", None)
                st.rerun()
else:
    st.info("Nenhuma compra de cartão cadastrada.")
