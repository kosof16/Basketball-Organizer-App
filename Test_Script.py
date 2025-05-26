import streamlit as st
import sys

def test_imports():
    """Test all required imports"""
    results = {}
    
    # Test basic imports
    try:
        import pandas as pd
        results['pandas'] = "✅ OK"
    except ImportError as e:
        results['pandas'] = f"❌ Failed: {e}"
    
    try:
        import altair as alt
        results['altair'] = "✅ OK"
    except ImportError as e:
        results['altair'] = f"❌ Failed: {e}"
    
    # Test PostgreSQL
    try:
        import psycopg2
        results['psycopg2'] = "✅ OK"
    except ImportError as e:
        results['psycopg2'] = f"❌ Failed: {e}"
    
    # Test bcrypt
    try:
        import bcrypt
        results['bcrypt'] = "✅ OK"
    except ImportError as e:
        results['bcrypt'] = f"❌ Failed: {e}"
    
    # Test Google APIs
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        results['google_apis'] = "✅ OK"
    except ImportError as e:
        results['google_apis'] = f"❌ Failed: {e}"
    
    return results

def test_database_connection():
    """Test database connection"""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=st.secrets["database"]["host"],
            database=st.secrets["database"]["dbname"],
            user=st.secrets["database"]["user"],
            password=st.secrets["database"]["password"],
            port=st.secrets["database"]["port"]
        )
        conn.close()
        return "✅ Database connection successful"
    except Exception as e:
        return f"❌ Database connection failed: {e}"

def test_google_drive():
    """Test Google Drive connection"""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["google_drive"]["service_account"],
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=credentials)
        return "✅ Google Drive connection successful"
    except Exception as e:
        return f"❌ Google Drive connection failed: {e}"

# Main test interface
st.title("🔧 Basketball App - System Test")

st.header("📦 Import Tests")
import_results = test_imports()
for package, result in import_results.items():
    st.write(f"**{package}:** {result}")

st.header("🗄️ Database Connection Test")
if st.button("Test Database"):
    result = test_database_connection()
    st.write(result)

st.header("☁️ Google Drive Test")
if st.button("Test Google Drive"):
    result = test_google_drive()
    st.write(result)

st.header("🐍 Python Information")
st.write(f"**Python Version:** {sys.version}")
st.write(f"**Streamlit Version:** {st.__version__}")