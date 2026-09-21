import sqlite3

import pandas as pd
import streamlit as st

from src.accounts import (
    ACCOUNT_TYPES,
    archive_account,
    cents_to_brl,
    create_account,
    delete_account,
    list_accounts,
    money_to_cents,
    reactivate_account,
)
from src.database import DEFAULT_DATABASE_PATH


st.header("Contas")
with st.form("account_form", clear_on_submit=True):
    name = st.text_input("Nome da conta", placeholder="Ex.: Conta principal")
    account_type_label = st.selectbox("Tipo de conta", list(ACCOUNT_TYPES))
    initial_balance = st.text_input("Saldo inicial", value="0,00", help="Use o formato brasileiro, como 1.234,56.")
    submitted = st.form_submit_button("Cadastrar conta", type="primary")

if submitted:
    try:
        initial_balance_cents = money_to_cents(initial_balance)
        if initial_balance_cents < 0:
            raise ValueError("O saldo inicial não pode ser negativo.")
        create_account(name, ACCOUNT_TYPES[account_type_label], initial_balance_cents, DEFAULT_DATABASE_PATH)
    except (ValueError, sqlite3.IntegrityError) as error:
        st.error(str(error))
    else:
        st.success("Conta cadastrada com sucesso.")

accounts = list_accounts(DEFAULT_DATABASE_PATH)
if accounts:
    st.dataframe(
        pd.DataFrame([
            {
                "Nome": account["name"],
                "Tipo": next(label for label, value in ACCOUNT_TYPES.items() if value == account["account_type"]),
                "Saldo": cents_to_brl(account["balance_cents"]),
            }
            for account in accounts
        ]),
        hide_index=True,
        width="stretch",
    )

    for account in accounts:
        with st.container(border=True):
            action_col, info_col = st.columns([1, 4])
            with info_col:
                st.markdown(f"**{account['name']}**  ")
                st.caption(
                    f"Saldo: {cents_to_brl(account['balance_cents'])} | "
                    f"Movimentações: {account['transaction_count']}"
                )
            with action_col:
                if st.button("Excluir", key=f"delete_account_{account['id']}"):
                    st.session_state["account_pending_action"] = account["id"]
                    st.rerun()

            if st.session_state.get("account_pending_action") == account["id"]:
                has_transactions = account["transaction_count"] > 0
                if has_transactions:
                    st.warning(
                        f"A conta '{account['name']}' possui {account['transaction_count']} "
                        "movimentação(ões) e não pode ser excluída permanentemente. "
                        "Arquive-a para preservar o histórico."
                    )
                    action_label = "Arquivar conta"
                else:
                    st.warning(
                        f"Confirme a exclusão permanente da conta '{account['name']}'. "
                        "Esta conta não possui movimentações."
                    )
                    action_label = "Confirmar exclusão"

                confirmed = st.checkbox(
                    f"Confirmo a ação para a conta '{account['name']}'.",
                    key=f"confirm_account_{account['id']}",
                )
                confirm_col, cancel_col = st.columns(2)
                with confirm_col:
                    if st.button(action_label, key=f"confirm_action_{account['id']}", disabled=not confirmed):
                        try:
                            if has_transactions:
                                archive_account(account["id"], DEFAULT_DATABASE_PATH)
                                message = f"Conta '{account['name']}' arquivada. O histórico foi preservado."
                            else:
                                delete_account(account["id"], DEFAULT_DATABASE_PATH)
                                message = f"Conta '{account['name']}' excluída permanentemente."
                        except ValueError as error:
                            st.error(str(error))
                        else:
                            st.success(message)
                            st.session_state.pop("account_pending_action", None)
                            st.rerun()
                with cancel_col:
                    if st.button("Cancelar", key=f"cancel_action_{account['id']}"):
                        st.session_state.pop("account_pending_action", None)
                        st.rerun()
else:
    st.info("Nenhuma conta cadastrada ainda.")

archived_accounts = list_accounts(DEFAULT_DATABASE_PATH, include_archived=True)
archived_accounts = [account for account in archived_accounts if not account["active"]]
if archived_accounts:
    st.divider()
    st.subheader("Contas arquivadas")
    st.caption("Contas arquivadas preservam o histórico e não aparecem em novos lançamentos.")
    for account in archived_accounts:
        with st.container(border=True):
            info_col, action_col = st.columns([4, 1])
            with info_col:
                st.markdown(f"**{account['name']}**")
                st.caption(
                    f"Saldo histórico: {cents_to_brl(account['balance_cents'])} | "
                    f"Movimentações: {account['transaction_count']}"
                )
            with action_col:
                if st.button("Reativar", key=f"reactivate_account_{account['id']}"):
                    try:
                        reactivate_account(account["id"], DEFAULT_DATABASE_PATH)
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        st.success(f"Conta '{account['name']}' reativada.")
                        st.rerun()
