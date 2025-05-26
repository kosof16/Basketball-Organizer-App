from google.oauth2 import service_account
from googleapiclient.discovery import build
import streamlit as st

def test_google_drive():
    try:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["google_drive"]["service_account"],
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=credentials)
        
        # Test by listing files in backup folder
        folder_id = st.secrets["google_drive"]["backup_folder_id"]
        results = service.files().list(
            q=f"parents in '{folder_id}'",
            fields="files(id, name)"
        ).execute()
        
        st.success(f"Google Drive connection successful! Found {len(results.get('files', []))} files in backup folder.")
    except Exception as e:
        st.error(f"Google Drive connection failed: {e}")

test_google_drive()