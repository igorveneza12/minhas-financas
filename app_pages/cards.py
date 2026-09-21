import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import cents_to_brl, money_to_cents
from src.credit_cards import (
    archive_card,
    create_card,
    delete_card,
    list_cards,
    reactivate_card,
    update_card,
)
from src.database import DEFAULT_DATABASE_PATH


st.header("Cartões de crédito")
st.caption("Cartões são obrigações separadas das contas bancárias e das despesas diretas.")

with st.form("card_form", clear_on_submit=True):
    name = st.text_input("Nome do cartão")
    institution = st.text_input("Instituição financeira")
    brand = st.text_input("Bandeira (opcional)")
    limit = st.text_input("Limite total", placeholder="0,00")
    closing_day = st.number_input("Dia de fechamento", min_value=1, max_value=31, value=20)
    due_day = st.number_input("Dia de vencimento", min_value=1, max_value=31, value=10)
    color = st.color_picker("Cor de identificação", value="#2E7D6F")
    submitted = st.form_submit_button("Cadastrar cartão", type="primary")

if submitted:
    try:
        create_card(
            name,
            institution,
            brand,
            money_to_cents(limit),
            int(closing_day),
            int(due_day),
            color,
            DEFAULT_DATABASE_PATH,
        )
    except (ValueError, sqlite3.IntegrityError) as error:
        st.error(str(error))
    else:
        st.success("Cartão cadastrado com sucesso.")
        st.rerun()

cards = list_cards(DEFAULT_DATABASE_PATH, include_archived=True)
active_cards = [card for card in cards if card["active"]]
if active_cards:
    st.subheader("Cartões ativos")
    st.dataframe(
        pd.DataFrame([
            {
                "Cartão": card["name"],
                "Instituição": card["institution"],
                "Limite total": cents_to_brl(card["limit_cents"]),
                "Limite disponível": cents_to_brl(card["available_cents"]),
                "Ainda não pago": cents_to_brl(card["unpaid_cents"]),
                "Fatura atual": cents_to_brl(card["current_invoice_cents"]),
                "Próximo vencimento": card["next_due_date"] or "-",
            }
            for card in active_cards
        ]),
        hide_index=True,
        width="stretch",
    )

    selected_name = st.selectbox("Cartão para editar ou arquivar", [card["name"] for card in active_cards])
    selected = next(card for card in active_cards if card["name"] == selected_name)
    with st.form("edit_card_form"):
        edit_name = st.text_input("Nome", value=selected["name"])
        edit_institution = st.text_input("Instituição", value=selected["institution"])
        edit_brand = st.text_input("Bandeira", value=selected["brand"] or "")
        edit_limit = st.text_input("Limite total", value=cents_to_brl(selected["limit_cents"]).replace("R$ ", ""))
        edit_closing = st.number_input("Fechamento", min_value=1, max_value=31, value=selected["closing_day"])
        edit_due = st.number_input("Vencimento", min_value=1, max_value=31, value=selected["due_day"])
        edit_color = st.color_picker("Cor", value=selected["color"] or "#2E7D6F")
        edit_submitted = st.form_submit_button("Salvar cartão")
    if edit_submitted:
        try:
            update_card(selected["id"], edit_name, edit_institution, edit_brand, money_to_cents(edit_limit), int(edit_closing), int(edit_due), edit_color, DEFAULT_DATABASE_PATH)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Cartão atualizado.")
            st.rerun()

    action_col, confirm_col = st.columns(2)
    with action_col:
        if st.button("Arquivar cartão", key=f"archive_{selected['id']}"):
            st.session_state["card_pending_archive"] = selected["id"]
    with confirm_col:
        if st.button("Excluir cartão", key=f"delete_{selected['id']}"):
            st.session_state["card_pending_delete"] = selected["id"]

    if st.session_state.get("card_pending_archive") == selected["id"]:
        st.warning(f"Confirme o arquivamento de '{selected['name']}'. Compras futuras serão bloqueadas.")
        if st.checkbox("Confirmo arquivar este cartão.", key=f"confirm_archive_{selected['id']}") and st.button("Confirmar arquivamento", key=f"confirm_archive_button_{selected['id']}"):
            try:
                archive_card(selected["id"], DEFAULT_DATABASE_PATH)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Cartão arquivado; o histórico foi preservado.")
                st.rerun()

    if st.session_state.get("card_pending_delete") == selected["id"]:
        st.warning(f"A exclusão de '{selected['name']}' é permanente e só é permitida sem histórico.")
        if st.checkbox("Confirmo a exclusão permanente.", key=f"confirm_delete_card_{selected['id']}") and st.button("Confirmar exclusão", key=f"confirm_delete_card_button_{selected['id']}"):
            try:
                delete_card(selected["id"], DEFAULT_DATABASE_PATH)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Cartão excluído permanentemente.")
                st.rerun()
else:
    st.info("Nenhum cartão ativo cadastrado.")

archived = [card for card in cards if not card["active"]]
if archived:
    st.divider()
    st.subheader("Cartões arquivados")
    for card in archived:
        col, action = st.columns([4, 1])
        with col:
            st.write(f"**{card['name']}** | Ainda não pago: {cents_to_brl(card['unpaid_cents'])}")
        with action:
            if st.button("Reativar", key=f"reactivate_card_{card['id']}"):
                try:
                    reactivate_card(card["id"], DEFAULT_DATABASE_PATH)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.success("Cartão reativado.")
                    st.rerun()
