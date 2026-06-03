# Panduan Menyimpan Data Aplikasi SHK ke Google Sheets

## 1. Buat Google Sheet
Buat Google Sheet baru, misalnya:
Database Aplikasi SHK

Copy Spreadsheet ID dari URL:
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit

## 2. Buat Service Account Google Cloud
Buat service account, lalu download JSON key.

## 3. Share Google Sheet
Share Google Sheet ke email service account, contohnya:
xxxxx@xxxxx.iam.gserviceaccount.com

Hak akses: Editor.

## 4. Isi Streamlit Secrets
Buka Streamlit Cloud > Manage app > Settings > Secrets.

Isi format seperti ini:

[google_sheets]
spreadsheet_id = "ISI_SPREADSHEET_ID"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "xxxxx@xxxxx.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

## 5. Update requirements.txt
Pastikan requirements.txt berisi:

streamlit
pandas
pdfplumber
openpyxl
gspread
google-auth

