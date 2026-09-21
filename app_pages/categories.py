import sqlite3

import streamlit as st

from src.categories import CATEGORY_TYPES, create_category, list_categories
from src.database import DEFAULT_DATABASE_PATH


st.header("Categorias")
st.caption("Organize receitas e despesas com categorias compatíveis com cada tipo.")

with st.form("category_form", clear_on_submit=True):
    name = st.text_input("Nome da categoria")
    category_label = st.selectbox("Tipo", list(CATEGORY_TYPES))
    submitted = st.form_submit_button("Cadastrar categoria", type="primary")

if submitted:
    try:
        create_category(name, CATEGORY_TYPES[category_label], DEFAULT_DATABASE_PATH)
    except (ValueError, sqlite3.IntegrityError) as error:
        st.error(str(error))
    else:
        st.success("Categoria cadastrada com sucesso.")

for label, category_type in CATEGORY_TYPES.items():
    st.subheader(label)
    categories = list_categories(category_type, DEFAULT_DATABASE_PATH)
    st.dataframe(
        [{"Categoria": row["name"]} for row in categories],
        hide_index=True,
        width="stretch",
    )
