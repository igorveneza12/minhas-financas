from datetime import date
import sqlite3
import streamlit as st

from src.accounts import cents_to_brl, money_to_cents
from src.database import DEFAULT_DATABASE_PATH
from src.goals import (archive_goal, create_goal, delete_goal, goal_progress,
                       goals_summary, list_goals, reactivate_goal)

st.header("Metas financeiras")
st.caption("O valor reservado é acompanhamento manual e não altera o saldo bancário.")
with st.form("goal_form", clear_on_submit=True):
    name = st.text_input("Nome da meta")
    target = st.text_input("Valor desejado")
    reserved = st.text_input("Valor já reservado", value="0,00")
    start = st.date_input("Data de início", date.today())
    deadline = st.date_input("Prazo desejado", value=None)
    monthly = st.text_input("Valor mensal planejado (opcional)")
    notes = st.text_area("Observações")
    submitted = st.form_submit_button("Cadastrar meta", type="primary")
if submitted:
    try:
        create_goal(name, money_to_cents(target), money_to_cents(reserved), start, deadline, money_to_cents(monthly) if monthly.strip() else None, notes, DEFAULT_DATABASE_PATH)
    except (ValueError, sqlite3.IntegrityError) as error: st.error(str(error))
    else: st.success("Meta cadastrada."); st.rerun()
summary = goals_summary(DEFAULT_DATABASE_PATH)
st.metric("Total desejado", cents_to_brl(summary["target_cents"])); st.metric("Total reservado", cents_to_brl(summary["reserved_cents"]))
st.subheader("Metas ativas")
for goal in list_goals(DEFAULT_DATABASE_PATH):
    progress = goal_progress(goal)
    with st.container(border=True):
        st.write(f"**{goal['name']}** | {cents_to_brl(goal['reserved_cents'])} de {cents_to_brl(goal['target_cents'])} | {progress['percent']:.1f}% | Falta {cents_to_brl(progress['remaining_cents'])}")
        if progress["monthly_needed_cents"] is not None:
            st.caption(f"Necessário por mês até o prazo: {cents_to_brl(progress['monthly_needed_cents'])}")
        # As reservas são manuais e não alteram saldos bancários.
        if goal["reserved_cents"]:
            if st.button("Arquivar", key=f"archive_goal_{goal['id']}"):
                archive_goal(goal["id"], DEFAULT_DATABASE_PATH)
                st.rerun()
            st.caption("Esta meta possui valor reservado; arquive-a para preservar seu histórico.")
        else:
            if st.button("Excluir", key=f"delete_goal_{goal['id']}"):
                st.session_state["confirm_delete_goal"] = goal["id"]
            if st.session_state.get("confirm_delete_goal") == goal["id"]:
                st.warning(f"Excluir definitivamente a meta '{goal['name']}'?")
                col_yes, col_no = st.columns(2)
                if col_yes.button("Sim, excluir", key=f"confirm_goal_{goal['id']}"):
                    try:
                        delete_goal(goal["id"], DEFAULT_DATABASE_PATH)
                    except (ValueError, sqlite3.IntegrityError) as error:
                        st.error(str(error))
                    else:
                        st.session_state.pop("confirm_delete_goal", None)
                        st.rerun()
                if col_no.button("Cancelar", key=f"cancel_goal_{goal['id']}"):
                    st.session_state.pop("confirm_delete_goal", None)
                    st.rerun()

archived = [goal for goal in list_goals(DEFAULT_DATABASE_PATH, include_archived=True) if not goal["active"]]
if archived:
    with st.expander(f"Metas arquivadas ({len(archived)})"):
        for goal in archived:
            col_name, col_action = st.columns([4, 1])
            col_name.write(f"{goal['name']} — {cents_to_brl(goal['reserved_cents'])} reservados")
            if col_action.button("Reativar", key=f"reactivate_goal_{goal['id']}"):
                reactivate_goal(goal["id"], DEFAULT_DATABASE_PATH)
                st.rerun()
