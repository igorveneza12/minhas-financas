import streamlit as st

from src.categories import seed_default_categories
from src.database import DEFAULT_DATABASE_PATH, initialize_database


st.set_page_config(page_title="Minhas Finanças", page_icon=":material/account_balance_wallet:", layout="wide")

initialize_database(DEFAULT_DATABASE_PATH)
seed_default_categories(DEFAULT_DATABASE_PATH)

pages = {
    "": [
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
        st.Page("app_pages/accounts.py", title="Contas", icon=":material/account_balance:"),
        st.Page("app_pages/transactions.py", title="Movimentações", icon=":material/payments:"),
        st.Page("app_pages/categories.py", title="Categorias", icon=":material/category:"),
        st.Page("app_pages/cards.py", title="Cartões de crédito", icon=":material/credit_card:"),
        st.Page("app_pages/purchases.py", title="Compras no cartão", icon=":material/shopping_cart:"),
        st.Page("app_pages/invoices.py", title="Faturas", icon=":material/receipt_long:"),
        st.Page("app_pages/budget.py", title="Orçamento", icon=":material/account_balance_wallet:"),
        st.Page("app_pages/debts.py", title="Dívidas", icon=":material/request_quote:"),
        st.Page("app_pages/goals.py", title="Metas financeiras", icon=":material/flag:"),
        st.Page("app_pages/planning.py", title="Planejamento", icon=":material/event_note:"),
        st.Page("app_pages/imports.py", title="Importar documentos", icon=":material/upload_file:"),
        st.Page("app_pages/reports.py", title="Relatórios", icon=":material/assessment:"),
        st.Page("app_pages/recurring.py", title="Recorrentes", icon=":material/repeat:"),
    ],
    "Configurações": [
        st.Page("app_pages/data_management.py", title="Gerenciamento de dados", icon=":material/storage:")
    ],
}
page = st.navigation(pages, position="top")
page.run()
