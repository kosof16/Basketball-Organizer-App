import psycopg2
import streamlit as st

def test_db_connection():
    try:
        conn = psycopg2.connect(
            host=st.secrets["database"]["host"],
            database=st.secrets["database"]["dbname"],
            user=st.secrets["database"]["user"],
            password=st.secrets["database"]["password"],
            port=st.secrets["database"]["port"]
        )
        st.success("Database connection successful!")
        conn.close()
    except Exception as e:
        st.error(f"Database connection failed: {e}")

test_db_connection()