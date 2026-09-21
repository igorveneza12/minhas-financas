from datetime import date
import sqlite3
import streamlit as st

from src.accounts import cents_to_brl, list_accounts, money_to_cents
from src.categories import list_categories
from src.database import DEFAULT_DATABASE_PATH
from src.recurring import archive_recurring, create_recurring, delete_recurring, list_occurrences, list_recurring, occurrence_status, pay_occurrence, reactivate_recurring, set_recurring_status, update_recurring

st.header("Recorrentes")
year = st.number_input("Ano", 2000, 2100, date.today().year)
month = st.selectbox("Mês", range(1, 13), index=date.today().month - 1, format_func=lambda value: f"{value:02d}")
status_filter = st.selectbox("Status da recorrência", ["Todos", "Ativas", "Inativas"])
accounts = list_accounts(DEFAULT_DATABASE_PATH)
categories = list_categories("despesa", DEFAULT_DATABASE_PATH)
with st.form("recurring_form", clear_on_submit=True):
    description = st.text_input("Descrição")
    category = st.selectbox("Categoria", [row["name"] for row in categories])
    account = st.selectbox("Conta", [row["name"] for row in accounts])
    amount = st.text_input("Valor previsto")
    due_day = st.number_input("Dia de vencimento", 1, 31, 10)
    start = st.date_input("Data de início", date.today())
    end = st.date_input("Data de término (opcional)", value=None)
    submitted = st.form_submit_button("Cadastrar recorrência", type="primary")
if submitted:
    try:
        create_recurring(description, next(row["id"] for row in categories if row["name"] == category), next(row["id"] for row in accounts if row["name"] == account), money_to_cents(amount), int(due_day), start, end, DEFAULT_DATABASE_PATH)
    except (ValueError, sqlite3.IntegrityError) as error: st.error(str(error))
    else: st.success("Despesa recorrente cadastrada."); st.rerun()
recurring_rows = list_recurring(status_filter, DEFAULT_DATABASE_PATH)
st.subheader("Recorrências cadastradas")
if not recurring_rows:
    st.info("Nenhuma recorrência cadastrada para este filtro.")
for recurring in recurring_rows:
    with st.container(border=True):
        recurring_status = {"active": "Ativa", "paused": "Pausada", "canceled": "Cancelada"}[recurring["status"]]
        st.write(f"**{recurring['description']}** | {recurring['category_name']} | {recurring['account_name']} | {cents_to_brl(recurring['expected_amount_cents'])} | dia {recurring['due_day']} | **{recurring_status}**")
        month_rows = list_occurrences(int(year), int(month), database_path=DEFAULT_DATABASE_PATH)
        month_row = next((row for row in month_rows if row["recurring_id"] == recurring["id"]), None)
        if month_row:
            status = occurrence_status(month_row)
            st.caption(f"Previsão {month_row['reference_month']}: {month_row['due_date']} | {cents_to_brl(month_row['expected_amount_cents'])} | {status}")
            if status != "Paga":
                paid_amount = st.text_input("Valor pago", value=cents_to_brl(month_row["expected_amount_cents"]).replace("R$ ", ""), key=f"amount_{month_row['id']}")
                if st.button("Confirmar pagamento", key=f"pay_{month_row['id']}"):
                    try: pay_occurrence(month_row["id"], money_to_cents(paid_amount), date.today(), DEFAULT_DATABASE_PATH)
                    except ValueError as error: st.error(str(error))
                    else: st.success("Pagamento registrado."); st.rerun()
        else:
            st.caption("Sem previsão para o mês selecionado.")
        if recurring["status"] == "active" and st.button("Pausar recorrência", key=f"pause_{recurring['id']}"):
            set_recurring_status(recurring["id"], "paused", DEFAULT_DATABASE_PATH); st.rerun()
        if recurring["status"] == "paused" and st.button("Reativar recorrência", key=f"reactivate_{recurring['id']}"):
            reactivate_recurring(recurring["id"], DEFAULT_DATABASE_PATH); st.rerun()
        with st.expander("Editar recorrência", expanded=False):
            edit_description = st.text_input("Descrição", value=recurring["description"], key=f"description_{recurring['id']}")
            edit_amount = st.text_input("Valor previsto", value=cents_to_brl(recurring["expected_amount_cents"]).replace("R$ ", ""), key=f"expected_{recurring['id']}")
            if st.button("Salvar edição", key=f"edit_{recurring['id']}"):
                try: update_recurring(recurring["id"], edit_description, recurring["category_id"], recurring["account_id"], money_to_cents(edit_amount), recurring["due_day"], recurring["end_date"], DEFAULT_DATABASE_PATH)
                except ValueError as error: st.error(str(error))
                else: st.success("Recorrência atualizada."); st.rerun()
        if recurring["status"] != "canceled" and st.button("Cancelar recorrência", key=f"cancel_{recurring['id']}"):
            set_recurring_status(recurring["id"], "canceled", DEFAULT_DATABASE_PATH); st.rerun()
        if st.button("Excluir", key=f"delete_{recurring['id']}"):
            st.session_state[f"confirm_delete_{recurring['id']}"] = True
        if st.session_state.get(f"confirm_delete_{recurring['id']}"):
            st.warning(f"Confirme a exclusão de '{recurring['description']}'. Despesas pagas nunca serão apagadas.")
            confirmed = st.checkbox("Confirmo a exclusão definitiva.", key=f"confirm_delete_check_{recurring['id']}")
            if st.button("Confirmar exclusão", key=f"confirm_delete_button_{recurring['id']}", disabled=not confirmed):
                try:
                    delete_recurring(recurring["id"], DEFAULT_DATABASE_PATH)
                except ValueError as error:
                    st.error(str(error))
                    st.info("Use cancelar/arquivar para preservar o histórico desta recorrência.")
                else:
                    st.success("Recorrência excluída; previsões futuras não pagas foram removidas.")
                    st.session_state.pop(f"confirm_delete_{recurring['id']}", None)
                    st.rerun()
