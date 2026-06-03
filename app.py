import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import pdfplumber
import re
import hmac
import base64
from io import BytesIO
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation
from math import floor
from pathlib import Path
from datetime import datetime, timedelta
import zipfile

st.set_page_config(page_title="Aplikasi SHK", layout="wide")

# =====================================================
# LOGIN SEDERHANA UNTUK ONLINE
# =====================================================

def cek_password():
    """
    Login sederhana untuk Streamlit Cloud.

    Saat online di Streamlit Cloud, password disimpan di:
    App > Settings > Secrets

    Contoh secrets:
    [auth]
    username = "admin"
    password = "ganti_password_ini"

    Kalau secrets belum diisi, default lokal:
    username: admin
    password: shk123
    """

    default_username = "admin"
    default_password = "shk123"

    try:
        username_benar = st.secrets.get("auth", {}).get("username", default_username)
        password_benar = st.secrets.get("auth", {}).get("password", default_password)
    except Exception:
        username_benar = default_username
        password_benar = default_password

    if "login_berhasil" not in st.session_state:
        st.session_state["login_berhasil"] = False

    if st.session_state["login_berhasil"]:
        return True

    st.title("Login Aplikasi SHK")
    st.caption("Masukkan username dan password untuk membuka aplikasi.")

    # Pakai form agar setelah isi password cukup tekan Enter.
    with st.form("form_login_shk", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        tombol_masuk = st.form_submit_button("Masuk", use_container_width=True)

    if tombol_masuk:
        username_ok = hmac.compare_digest(str(username), str(username_benar))
        password_ok = hmac.compare_digest(str(password), str(password_benar))

        if username_ok and password_ok:
            st.session_state["login_berhasil"] = True
            st.rerun()
        else:
            st.error("Username atau password salah.")

    st.info("Default lokal sementara: username admin, password shk123. Nanti ganti lewat Streamlit Secrets.")
    return False


if not cek_password():
    st.stop()

with st.sidebar:
    st.success("Login aktif")
    if st.button("Logout"):
        st.session_state["login_berhasil"] = False
        st.rerun()

st.title("Aplikasi SHK")

KOLOM_BANK = ["Tanggal", "Jam", "Jenis", "Nominal", "Uraian", "Uraian_Asli", "Debit", "Kredit", "Debet_Bank", "Kredit_Bank", "Saldo_Bank"]
KOLOM_ACCURATE = ["Tanggal", "Jenis", "Nominal", "Uraian", "No_Bukti", "No_Trans", "Debit", "Kredit"]

st.markdown('''
<style>
div[role="radiogroup"] { gap: 18px; }
div[role="radiogroup"] label {
    background-color: #262730; border: 1px solid #555; border-radius: 14px;
    padding: 16px 28px; min-width: 150px; justify-content: center;
    font-size: 22px; font-weight: 700;
}
div[role="radiogroup"] label:hover { border-color: #ffffff; background-color: #333540; }
div[role="radiogroup"] label p { font-size: 22px; font-weight: 700; }
</style>
''', unsafe_allow_html=True)

# =====================================================
# UTILITAS
# =====================================================

def df_bank_kosong():
    return pd.DataFrame(columns=KOLOM_BANK)

def df_accurate_kosong():
    return pd.DataFrame(columns=KOLOM_ACCURATE)

def bersih_nominal(nilai):
    if pd.isna(nilai):
        return 0
    teks = str(nilai).strip().replace("Rp", "").replace("IDR", "").replace(" ", "").replace("\n", "")
    if teks in ["", "None", "nan", "-", "0.00", "0,00"]:
        return 0
    if isinstance(nilai, (int, float)):
        try:
            return int(Decimal(str(nilai)) * 100)
        except Exception:
            return 0
    tanda = 1
    if teks.startswith("-"):
        tanda = -1
        teks = teks[1:]
    elif teks.startswith("+"):
        teks = teks[1:]
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{2}", teks):
        teks = teks.replace(".", "").replace(",", ".")
        try:
            return tanda * int(Decimal(teks) * 100)
        except Exception:
            return 0
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", teks):
        teks = teks.replace(".", "")
        try:
            return tanda * int(Decimal(teks) * 100)
        except Exception:
            return 0
    if re.fullmatch(r"\d{1,3}(,\d{3})+\.\d{2}", teks):
        teks = teks.replace(",", "")
        try:
            return tanda * int(Decimal(teks) * 100)
        except Exception:
            return 0
    teks = teks.replace(",", "")
    try:
        return tanda * int(Decimal(teks) * 100)
    except (InvalidOperation, ValueError):
        return 0

def nominal_ke_rupiah(nilai_sen):
    try:
        return int(abs(int(nilai_sen))) // 100
    except Exception:
        return 0

def format_uang(nilai_sen):
    try:
        nilai_sen = int(nilai_sen)
        tanda = "-" if nilai_sen < 0 else ""
        nilai_sen = abs(nilai_sen)
        rupiah = nilai_sen // 100
        sen = nilai_sen % 100
        text = f"{rupiah:,}".replace(",", ".")
        return f"{tanda}{text},{sen:02d}" if sen else f"{tanda}{text}"
    except Exception:
        return ""

def parse_rupiah_float(nilai):
    return bersih_nominal(nilai) / 100

def format_rupiah_float(nilai):
    try:
        nilai = float(nilai)
        tanda = "-" if nilai < 0 else ""
        nilai = abs(nilai)
        hasil = f"{nilai:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{tanda}Rp{hasil}"
    except Exception:
        return ""

def format_tanggal_indonesia(tanggal):
    hari = {0:"Senin",1:"Selasa",2:"Rabu",3:"Kamis",4:"Jumat",5:"Sabtu",6:"Minggu"}
    bulan = {1:"Januari",2:"Februari",3:"Maret",4:"April",5:"Mei",6:"Juni",7:"Juli",8:"Agustus",9:"September",10:"Oktober",11:"November",12:"Desember"}
    try:
        return f"{hari[tanggal.weekday()]}, {tanggal.day:02d} {bulan[tanggal.month]} {tanggal.year}"
    except Exception:
        return tanggal

def auto_width_excel(writer):
    for sheet_name in writer.sheets:
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = 0
            letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                except Exception:
                    pass
            ws.column_dimensions[letter].width = max_len + 3

# =====================================================
# RINGKAS URAIAN
# =====================================================

def ringkas_uraian_bri(teks):
    teks = str(teks)
    atas = teks.upper()
    if "QRIS" in atas: return "QRIS"
    if "OVO" in atas: return "Top Up OVO"
    if "DANA" in atas: return "Top Up DANA"
    if "TLKM" in atas or "TELKOM" in atas: return "Telkom"
    if "SMS" in atas: return "Biaya SMS Notifikasi"
    if "PAJAK" in atas or "TAX" in atas: return "Pajak Bunga"
    if "BUNGA" in atas or "INTEREST" in atas: return "Bunga Rekening"
    if "PLN" in atas: return "PLN"
    if "BRIVA" in atas: return "Pembayaran BRIVA"
    if "TRANSFER KE" in atas:
        return "Transfer ke " + teks.replace("Transfer Ke ", "").replace("via BRImo", "").strip()
    if "TRANSFER DARI" in atas:
        return "Transfer dari " + teks.replace("Transfer Dari ", "").replace("via BRImo", "").strip()
    return teks

def ringkas_uraian_bca(entry):
    lines = [x.strip() for x in str(entry).splitlines() if x.strip()]
    atas = "\n".join(lines).upper()
    if not lines: return ""
    if "SALDO AWAL" in atas: return "Saldo Awal"
    if "TARIKAN ATM" in atas: return "Tarikan ATM"
    if "BIAYA ADM" in atas: return "Biaya Admin"
    if "PAJAK BUNGA" in atas: return "Pajak Bunga"
    if re.search(r"\bBUNGA\b", atas): return "Bunga"
    kandidat = []
    for line in lines[1:]:
        s = line.strip(); u = s.upper()
        buang = ["TANGGAL","KETERANGAN","CBG","MUTASI","SALDO","BERSAMBUNG","HALAMAN","PERIODE","MATA UANG","REKENING TAHAPAN","NO. REKENING","CATATAN","APABILA","BCA BERHAK","SETIAP SAAT","LAPORAN MUTASI","KCU","INDONESIA"]
        if any(x in u for x in buang): continue
        if u == "MULYADI": continue
        if re.fullmatch(r"\d+\.00", s): continue
        if re.fullmatch(r"[\d,]+\.\d{2}", s): continue
        if re.fullmatch(r"[\d,]+\.\d{2}\s+DB", s): continue
        if re.fullmatch(r"[\d,]+\.\d{2}\s+DB\s+[\d,]+\.\d{2}", s): continue
        if re.fullmatch(r"[\d,]+\.\d{2}\s+[\d,]+\.\d{2}", s): continue
        if s in ["-", "DB"]: continue
        if re.fullmatch(r"\d{1,2}/\d{2}/\d{2}", s): continue
        if "FTSCY" in u or "FTFVA" in u or "WS95031" in u or "WS95271" in u or "ZN341" in u: continue
        if re.match(r"^\d{2}/\d{2}\s+", s): continue
        kandidat.append(s)
    if kandidat:
        nama = kandidat[-1]
        if "TRSF E-BANKING CR" in atas: return f"Transfer dari {nama}"
        if "TRSF E-BANKING DB" in atas: return f"Transfer ke {nama}"
        return nama
    if "TRSF E-BANKING CR" in atas: return "Transfer Masuk BCA"
    if "TRSF E-BANKING DB" in atas: return "Transfer Keluar BCA"
    return lines[0]

def ringkas_uraian_mandiri(teks):
    teks = str(teks).strip(); atas = teks.upper()
    if "ANDRE SULISTYO" in atas: return "Arsitek Sakaran"
    if "FLASDIS" in atas: return "Pembayaran No. Faktur SHK.FKT.2026.00833"
    if "ANDI ASRIJAL" in atas: return "Pembayaran No. Faktur SHK.FKT.2026.00839"
    if "ADMIN" in atas or "BIAYA" in atas: return "Biaya Admin"
    if "BUNGA" in atas or "INTEREST" in atas: return "Bunga Rekening"
    if "PAJAK" in atas or "TAX" in atas: return "Pajak Bunga"
    if "QRIS" in atas: return "QRIS"
    if "OVO" in atas: return "Top Up OVO"
    if "DANA" in atas: return "Top Up DANA"
    if "PLN" in atas: return "PLN"
    return teks

def ringkas_uraian_bni(teks):
    teks = str(teks).strip(); atas = teks.upper()
    if "PPH" in atas or "PAJAK" in atas: return "Pajak Bunga"
    if "BY ADMINISTRASI" in atas or "ADMINISTRASI" in atas: return "Biaya Administrasi"
    if "JASA GIRO" in atas or "BUNGA" in atas: return "Bunga Rekening"
    return teks.replace("\n", " ").strip()

# =====================================================
# PARSER BANK
# =====================================================

def baca_bri_pdf(file):
    transaksi = []
    pola_normal = re.compile(r"^(\d{2}/\d{2}/\d{2}) (\d{2}:\d{2}:\d{2}) (.+?) (\S+) ([\d,]+\.\d{2}) ([\d,]+\.\d{2}) ([\d,]+\.\d{2})$")
    pola_tanpa_teller = re.compile(r"^(\d{2}/\d{2}/\d{2}) (\d{2}:\d{2}:\d{2}) (.+?) ([\d,]+\.\d{2}) ([\d,]+\.\d{2}) ([\d,]+\.\d{2})$")
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                teks = page.extract_text() or ""
                for baris in teks.splitlines():
                    baris = baris.strip()
                    cocok = pola_normal.match(baris)
                    if cocok:
                        tanggal, jam, uraian, teller, debet_bri, kredit_bri, saldo = cocok.groups()
                    else:
                        cocok = pola_tanpa_teller.match(baris)
                        if cocok:
                            tanggal, jam, uraian, debet_bri, kredit_bri, saldo = cocok.groups()
                        else:
                            continue
                    debet_bri = abs(bersih_nominal(debet_bri)); kredit_bri = abs(bersih_nominal(kredit_bri)); saldo_bri = abs(bersih_nominal(saldo))
                    if kredit_bri > 0:
                        jenis = "Masuk"; nominal = kredit_bri; debit_format = format_uang(nominal); kredit_format = ""
                    elif debet_bri > 0:
                        jenis = "Keluar"; nominal = debet_bri; debit_format = ""; kredit_format = format_uang(nominal)
                    else:
                        continue
                    transaksi.append({"Tanggal": pd.to_datetime(tanggal, format="%d/%m/%y", errors="coerce").date(), "Jam": jam, "Jenis": jenis, "Nominal": nominal, "Uraian": ringkas_uraian_bri(uraian), "Uraian_Asli": uraian, "Debit": debit_format, "Kredit": kredit_format, "Debet_Bank": debet_bri, "Kredit_Bank": kredit_bri, "Saldo_Bank": saldo_bri})
    except Exception as e:
        st.error("PDF BRI tidak bisa dibaca."); st.write("Detail error:", e)
        return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    df = pd.DataFrame(transaksi)
    if len(df) == 0: return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    df = df.reindex(columns=KOLOM_BANK)
    first = df.iloc[0]; last = df.iloc[-1]
    return df, {"Saldo Awal": first["Saldo_Bank"] + first["Debet_Bank"] - first["Kredit_Bank"], "Saldo Akhir": last["Saldo_Bank"]}

def deteksi_tahun_bca(teks):
    cocok = re.search(r"PERIODE\s*:\s*[A-Z]+\s+(\d{4})", teks.upper())
    return int(cocok.group(1)) if cocok else 2026

def baca_bca_pdf(file):
    semua_teks = ""
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                semua_teks += "\n" + (page.extract_text() or "")
    except Exception as e:
        st.error("PDF BCA tidak bisa dibaca."); st.write("Detail error:", e)
        return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    tahun = deteksi_tahun_bca(semua_teks)
    saldo_awal_match = re.search(r"SALDO AWAL\s*:\s*([\d,]+\.\d{2})", semua_teks)
    saldo_akhir_match = re.search(r"SALDO AKHIR\s*:\s*([\d,]+\.\d{2})", semua_teks)
    saldo_awal = abs(bersih_nominal(saldo_awal_match.group(1))) if saldo_awal_match else 0
    saldo_akhir = abs(bersih_nominal(saldo_akhir_match.group(1))) if saldo_akhir_match else 0
    lines = [x.strip() for x in semua_teks.splitlines() if x.strip()]
    entries, current = [], []
    for line in lines:
        if re.match(r"^\d{2}/\d{2}\s+", line):
            if current: entries.append("\n".join(current))
            current = [line]
        else:
            if current: current.append(line)
    if current: entries.append("\n".join(current))
    transaksi = []
    for entry in entries:
        atas = entry.upper()
        if "SALDO AWAL" in atas: continue
        tanggal_match = re.match(r"^(\d{2})/(\d{2})", entry)
        if not tanggal_match: continue
        hari, bulan = tanggal_match.groups()
        tanggal = pd.to_datetime(f"{tahun}-{bulan}-{hari}", format="%Y-%m-%d", errors="coerce")
        if pd.isna(tanggal): continue
        tanggal = tanggal.date()
        if re.search(r"\bDB\b", atas): jenis = "Keluar"
        elif re.search(r"\bCR\b", atas): jenis = "Masuk"
        elif "PAJAK BUNGA" in atas: jenis = "Keluar"
        elif re.search(r"\bBUNGA\b", atas): jenis = "Masuk"
        else: jenis = "Masuk"
        nominal, saldo = 0, 0
        if jenis == "Keluar":
            cocok_db_semua = re.findall(r"([\d,]+\.\d{2})\s+DB(?:\s+([\d,]+\.\d{2}))?", entry)
            if cocok_db_semua:
                nominal = abs(bersih_nominal(cocok_db_semua[-1][0]))
                if cocok_db_semua[-1][1]: saldo = abs(bersih_nominal(cocok_db_semua[-1][1]))
        if nominal == 0 and jenis == "Keluar":
            angka_db = re.findall(r"([\d,]+\.\d{2})\s+DB", entry)
            if angka_db: nominal = abs(bersih_nominal(angka_db[-1]))
        if nominal == 0 and jenis == "Masuk":
            for line in entry.splitlines():
                line = line.strip()
                c1 = re.search(r"\bCR\b.*?([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?$", line)
                if c1:
                    nominal = abs(bersih_nominal(c1.group(1)))
                    if c1.group(2): saldo = abs(bersih_nominal(c1.group(2)))
                    break
                c2 = re.search(r"^([\d,]+\.\d{2})\s+([\d,]+\.\d{2})$", line)
                if c2:
                    nominal = abs(bersih_nominal(c2.group(1))); saldo = abs(bersih_nominal(c2.group(2))); break
                c3 = re.search(r"^([\d,]+\.\d{2})$", line)
                if c3:
                    nominal = abs(bersih_nominal(c3.group(1))); break
        if nominal == 0: continue
        if jenis == "Masuk":
            debit_format = format_uang(nominal); kredit_format = ""; debet_bank = 0; kredit_bank = nominal
        else:
            debit_format = ""; kredit_format = format_uang(nominal); debet_bank = nominal; kredit_bank = 0
        transaksi.append({"Tanggal": tanggal, "Jam": "", "Jenis": jenis, "Nominal": nominal, "Uraian": ringkas_uraian_bca(entry), "Uraian_Asli": entry.replace("\n", " | "), "Debit": debit_format, "Kredit": kredit_format, "Debet_Bank": debet_bank, "Kredit_Bank": kredit_bank, "Saldo_Bank": saldo})
    df = pd.DataFrame(transaksi)
    if len(df) == 0: return df_bank_kosong(), {"Saldo Awal": saldo_awal, "Saldo Akhir": saldo_akhir}
    return df.reindex(columns=KOLOM_BANK), {"Saldo Awal": saldo_awal, "Saldo Akhir": saldo_akhir}

def baca_mandiri_pdf(file, password=""):
    transaksi, semua_blok = [], []
    bulan_map = {"jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,"may":5,"jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,"sept":9,"september":9,"oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12}
    try:
        file.seek(0); data_pdf = file.read()
        with pdfplumber.open(BytesIO(data_pdf), password=password or "") as pdf:
            for page in pdf.pages:
                teks = page.extract_text(x_tolerance=2, y_tolerance=4) or ""
                lines = [x.strip() for x in teks.splitlines() if x.strip()]
                current = []
                for line in lines:
                    if re.match(r"^\d+\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}", line):
                        if current: semua_blok.append(" ".join(current))
                        current = [line]
                    else:
                        if current: current.append(line)
                if current: semua_blok.append(" ".join(current))
    except Exception as e:
        st.error("PDF Mandiri tidak bisa dibaca. Kemungkinan PDF terenkripsi/password atau format scan."); st.write("Detail error:", e)
        return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    for blok in semua_blok:
        atas = blok.upper()
        if "SALDO AWAL" in atas or ("TANGGAL" in atas and "KETERANGAN" in atas): continue
        t = re.search(r"^\d+\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", blok)
        if not t: continue
        hari, bulan_text, tahun = t.groups(); bulan = bulan_map.get(bulan_text.lower())
        if not bulan: continue
        tanggal = pd.to_datetime(f"{tahun}-{bulan}-{hari}", format="%Y-%m-%d", errors="coerce")
        if pd.isna(tanggal): continue
        tanggal = tanggal.date()
        semua_uang = re.findall(r"[+-]?\d{1,3}(?:\.\d{3})*,\d{2}", blok)
        nominal_text = None
        for uang in semua_uang:
            if uang.startswith("+") or uang.startswith("-"):
                nominal_text = uang; break
        if not nominal_text: continue
        nominal_asli = bersih_nominal(nominal_text)
        if nominal_asli == 0: continue
        saldo_bank = abs(bersih_nominal(semua_uang[-1])) if len(semua_uang) >= 2 else 0
        uraian = re.sub(r"^\d+\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}", "", blok)
        uraian = re.sub(r"\d{1,2}:\d{2}:\d{2}\s+WIB", "", uraian).replace(nominal_text, "")
        if semua_uang: uraian = uraian.replace(semua_uang[-1], "")
        uraian = re.sub(r"\s+", " ", uraian).strip()
        if nominal_asli > 0:
            jenis = "Masuk"; nominal = abs(nominal_asli); debit_format = format_uang(nominal); kredit_format = ""; debet_bank = 0; kredit_bank = nominal
        else:
            jenis = "Keluar"; nominal = abs(nominal_asli); debit_format = ""; kredit_format = format_uang(nominal); debet_bank = nominal; kredit_bank = 0
        transaksi.append({"Tanggal": tanggal, "Jam": "", "Jenis": jenis, "Nominal": nominal, "Uraian": ringkas_uraian_mandiri(uraian), "Uraian_Asli": blok, "Debit": debit_format, "Kredit": kredit_format, "Debet_Bank": debet_bank, "Kredit_Bank": kredit_bank, "Saldo_Bank": saldo_bank})
    df = pd.DataFrame(transaksi)
    if len(df) == 0: return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    df = df.reindex(columns=KOLOM_BANK).drop_duplicates(subset=["Tanggal","Jenis","Nominal","Saldo_Bank","Uraian_Asli"], keep="first").reset_index(drop=True)
    first = df.iloc[0]; last = df.iloc[-1]
    return df, {"Saldo Awal": first["Saldo_Bank"] - first["Kredit_Bank"] + first["Debet_Bank"], "Saldo Akhir": last["Saldo_Bank"]}

def baca_bni_pdf(file):
    transaksi = []
    try:
        file.seek(0); data_pdf = file.read(); semua_teks = ""
        with pdfplumber.open(BytesIO(data_pdf)) as pdf:
            for page in pdf.pages:
                semua_teks += "\n" + (page.extract_text(x_tolerance=2, y_tolerance=4) or "")
    except Exception as e:
        st.error("PDF BNI tidak bisa dibaca."); st.write("Detail error:", e)
        return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    lines = [x.strip() for x in semua_teks.splitlines() if x.strip()]
    blok_transaksi, current = [], []
    for line in lines:
        if re.match(r"^\d{4}-\d{2}-\d{2}\s+", line):
            if current: blok_transaksi.append(" ".join(current))
            current = [line]
        else:
            if current: current.append(line)
    if current: blok_transaksi.append(" ".join(current))
    for blok in blok_transaksi:
        atas = blok.upper()
        if "TANGGAL" in atas and "URAIAN" in atas: continue
        tm = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.+)", blok)
        if not tm: continue
        tanggal_text, sisa = tm.group(1), tm.group(2)
        tanggal = pd.to_datetime(tanggal_text, errors="coerce")
        if pd.isna(tanggal): continue
        tanggal = tanggal.date()
        cocok = re.search(r"(.+?)\s+(Db\.?|Cr\.?|Debit|Credit|D|C)\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})", sisa, flags=re.IGNORECASE)
        if cocok:
            uraian = cocok.group(1).strip(); tipe = cocok.group(2).strip().lower(); nominal_text = cocok.group(3).strip(); saldo_text = cocok.group(4).strip()
            nominal = abs(bersih_nominal(nominal_text)); saldo_bank = abs(bersih_nominal(saldo_text))
            if nominal == 0: continue
            if tipe.startswith("cr") or tipe == "c" or tipe == "credit":
                jenis = "Masuk"; debit_format = format_uang(nominal); kredit_format = ""; debet_bank = 0; kredit_bank = nominal
            else:
                jenis = "Keluar"; debit_format = ""; kredit_format = format_uang(nominal); debet_bank = nominal; kredit_bank = 0
        else:
            semua_uang = re.findall(r"[\d\.]+,\d{2}", sisa)
            if len(semua_uang) < 2: continue
            nominal_text = semua_uang[-2]; saldo_text = semua_uang[-1]
            nominal = abs(bersih_nominal(nominal_text)); saldo_bank = abs(bersih_nominal(saldo_text))
            if nominal == 0: continue
            uraian = sisa.replace(nominal_text, "").replace(saldo_text, "")
            uraian = re.sub(r"\s+", " ", uraian).strip(); atas_uraian = uraian.upper()
            if "PPH" in atas_uraian or "PAJAK" in atas_uraian:
                jenis = "Keluar"
            elif "JASA GIRO" in atas_uraian or "BUNGA" in atas_uraian:
                jenis = "Masuk"
            else:
                continue
            if jenis == "Masuk":
                debit_format = format_uang(nominal); kredit_format = ""; debet_bank = 0; kredit_bank = nominal
            else:
                debit_format = ""; kredit_format = format_uang(nominal); debet_bank = nominal; kredit_bank = 0
        transaksi.append({"Tanggal": tanggal, "Jam": "", "Jenis": jenis, "Nominal": nominal, "Uraian": ringkas_uraian_bni(uraian), "Uraian_Asli": blok, "Debit": debit_format, "Kredit": kredit_format, "Debet_Bank": debet_bank, "Kredit_Bank": kredit_bank, "Saldo_Bank": saldo_bank})
    df = pd.DataFrame(transaksi)
    if len(df) == 0:
        st.warning("PDF BNI berhasil dibuka, tapi transaksi belum terbaca.")
        return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    df = df.reindex(columns=KOLOM_BANK)
    df_hitung = df.copy(); df_hitung["Urutan_Asli"] = range(len(df_hitung))
    df_hitung = df_hitung.sort_values(by=["Tanggal", "Urutan_Asli"], ascending=[True, False]).reset_index(drop=True)
    first = df_hitung.iloc[0]; last = df_hitung.iloc[-1]
    return df, {"Saldo Awal": first["Saldo_Bank"] - first["Kredit_Bank"] + first["Debet_Bank"], "Saldo Akhir": last["Saldo_Bank"]}

def gabung_bni_multi(file_list):
    semua_bank_bni = []; saldo_awal_bni = 0; saldo_akhir_bni = 0
    if not file_list: return df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    for i, satu_file_bni in enumerate(file_list):
        data_bni, ringkasan_bni = baca_bni_pdf(satu_file_bni)
        if len(data_bni) > 0:
            data_bni["Sumber_File"] = satu_file_bni.name; semua_bank_bni.append(data_bni)
        if i == 0: saldo_awal_bni = ringkasan_bni.get("Saldo Awal", 0)
        saldo_akhir_bni = ringkasan_bni.get("Saldo Akhir", saldo_akhir_bni)
    if semua_bank_bni:
        bank = pd.concat(semua_bank_bni, ignore_index=True)
        bank = bank.drop_duplicates(subset=["Tanggal", "Jenis", "Nominal", "Uraian", "Saldo_Bank"], keep="first")
        bank = bank.sort_values(by=["Tanggal"]).reset_index(drop=True)
        bank = bank.reindex(columns=KOLOM_BANK + ["Sumber_File"])
    else:
        bank = df_bank_kosong()
    return bank, {"Saldo Awal": saldo_awal_bni, "Saldo Akhir": saldo_akhir_bni}

# =====================================================
# ACCURATE DAN REKONSILIASI
# =====================================================

def baca_accurate(file):
    try:
        raw = pd.read_excel(file, header=None)
    except Exception as e:
        st.error("File Accurate tidak bisa dibaca."); st.write("Detail error:", e)
        return df_accurate_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    try:
        data = pd.DataFrame({
            "Tanggal": pd.to_datetime(raw.iloc[:, 1], errors="coerce").dt.date,
            "No_Bukti": raw.iloc[:, 4], "No_Trans": raw.iloc[:, 8], "Tipe": raw.iloc[:, 10], "Keterangan": raw.iloc[:, 12],
            "Debit_Accurate": raw.iloc[:, 19].apply(lambda x: abs(bersih_nominal(x))),
            "Kredit_Accurate": raw.iloc[:, 22].apply(lambda x: abs(bersih_nominal(x))),
            "Saldo_Accurate": raw.iloc[:, 24].apply(lambda x: abs(bersih_nominal(x))),
        })
    except Exception as e:
        st.error("Format kolom Accurate tidak sesuai."); st.write("Detail error:", e)
        return df_accurate_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
    data = data.dropna(subset=["Tanggal"]).copy()
    transaksi = []
    for _, row in data.iterrows():
        if row["Debit_Accurate"] > 0:
            transaksi.append({"Tanggal": row["Tanggal"], "Jenis": "Masuk", "Nominal": row["Debit_Accurate"], "Uraian": row["Keterangan"], "No_Bukti": row["No_Bukti"], "No_Trans": row["No_Trans"], "Debit": format_uang(row["Debit_Accurate"]), "Kredit": ""})
        if row["Kredit_Accurate"] > 0:
            transaksi.append({"Tanggal": row["Tanggal"], "Jenis": "Keluar", "Nominal": row["Kredit_Accurate"], "Uraian": row["Keterangan"], "No_Bukti": row["No_Bukti"], "No_Trans": row["No_Trans"], "Debit": "", "Kredit": format_uang(row["Kredit_Accurate"])})
    transaksi_df = pd.DataFrame(transaksi)
    transaksi_df = df_accurate_kosong() if len(transaksi_df) == 0 else transaksi_df.reindex(columns=KOLOM_ACCURATE)
    data_saldo = data[(data["Debit_Accurate"] > 0) | (data["Kredit_Accurate"] > 0) | (data["Saldo_Accurate"] > 0)].copy()
    if len(data_saldo) == 0: return transaksi_df, {"Saldo Awal": 0, "Saldo Akhir": 0}
    first = data_saldo.iloc[0]; last = data_saldo.iloc[-1]
    return transaksi_df, {"Saldo Awal": first["Saldo_Accurate"] - first["Debit_Accurate"] + first["Kredit_Accurate"], "Saldo Akhir": last["Saldo_Accurate"]}

def cocokkan_pakai_sekali(bank, accurate):
    bank = bank.copy(); accurate = accurate.copy(); bank["Terpakai"] = False; accurate["Terpakai"] = False
    if len(bank) == 0 or len(accurate) == 0: return bank, accurate
    if "Nominal" not in bank.columns or "Nominal" not in accurate.columns: return bank, accurate
    tahap = [["Tanggal", "Jenis", "Nominal"], ["Jenis", "Nominal"], ["Nominal"]]
    for kolom_key in tahap:
        bank_sisa = bank[bank["Terpakai"] == False].copy(); acc_sisa = accurate[accurate["Terpakai"] == False].copy()
        acc_index = defaultdict(list)
        for idx, row in acc_sisa.iterrows():
            try: acc_index[tuple(row[k] for k in kolom_key)].append(idx)
            except Exception: pass
        for idx_bank, row_bank in bank_sisa.iterrows():
            try: key = tuple(row_bank[k] for k in kolom_key)
            except Exception: continue
            while acc_index.get(key):
                idx_acc = acc_index[key].pop(0)
                if not accurate.loc[idx_acc, "Terpakai"]:
                    bank.loc[idx_bank, "Terpakai"] = True; accurate.loc[idx_acc, "Terpakai"] = True; break
    return bank, accurate

def unmatched_berdasarkan_jenis_nominal(sumber_df, pembanding_df):
    if sumber_df is None or len(sumber_df) == 0: return pd.DataFrame()
    if pembanding_df is None or len(pembanding_df) == 0: return sumber_df.copy()
    if "Nominal" not in sumber_df.columns or "Jenis" not in sumber_df.columns: return sumber_df.copy()
    if "Nominal" not in pembanding_df.columns or "Jenis" not in pembanding_df.columns: return sumber_df.copy()
    counter = Counter()
    for _, row in pembanding_df.iterrows():
        counter[(str(row.get("Jenis", "")).strip().upper(), nominal_ke_rupiah(row.get("Nominal", 0)))] += 1
    unmatched_idx = []
    for idx, row in sumber_df.iterrows():
        key = (str(row.get("Jenis", "")).strip().upper(), nominal_ke_rupiah(row.get("Nominal", 0)))
        if counter[key] > 0: counter[key] -= 1
        else: unmatched_idx.append(idx)
    return sumber_df.loc[unmatched_idx].copy()

def buat_tabel_bank_belum_ada(unmatched_bank, nama_bank):
    if unmatched_bank is None or len(unmatched_bank) == 0:
        return pd.DataFrame(columns=["Tanggal", "Uraian", "Debit", "Kredit", "Keterangan"])
    return pd.DataFrame([{"Tanggal": format_tanggal_indonesia(r.get("Tanggal", "")), "Uraian": r.get("Uraian", ""), "Debit": r.get("Debit", ""), "Kredit": r.get("Kredit", ""), "Keterangan": "Tidak ada pasangan nominal di Accurate"} for _, r in unmatched_bank.iterrows()])

def buat_tabel_accurate_tidak_ada(unmatched_acc, nama_bank):
    if unmatched_acc is None or len(unmatched_acc) == 0:
        return pd.DataFrame(columns=["Tanggal", "Uraian Accurate", "Debit", "Kredit", "No Bukti", "No Trans", "Keterangan"])
    return pd.DataFrame([{"Tanggal": format_tanggal_indonesia(r.get("Tanggal", "")), "Uraian Accurate": r.get("Uraian", ""), "Debit": r.get("Debit", ""), "Kredit": r.get("Kredit", ""), "No Bukti": r.get("No_Bukti", ""), "No Trans": r.get("No_Trans", ""), "Keterangan": f"Tidak ada pasangan nominal di {nama_bank}"} for _, r in unmatched_acc.iterrows()])

def tabel_transaksi_sen(df, sumber):
    if df is None or len(df) == 0 or "Nominal" not in df.columns:
        return pd.DataFrame(columns=["Sumber", "Tanggal", "Jenis", "Uraian", "Nominal"])
    sen = df[df["Nominal"] % 100 != 0].copy()
    if len(sen) == 0: return pd.DataFrame(columns=["Sumber", "Tanggal", "Jenis", "Uraian", "Nominal"])
    hasil = pd.DataFrame({"Sumber": sumber, "Tanggal": sen["Tanggal"].apply(format_tanggal_indonesia), "Jenis": sen["Jenis"], "Uraian": sen["Uraian"], "Nominal": sen["Nominal"].apply(format_uang)})
    if "No_Bukti" in sen.columns:
        hasil["No Bukti"] = sen.get("No_Bukti", ""); hasil["No Trans"] = sen.get("No_Trans", "")
    return hasil

def buat_excel_rekon(tabel_saldo, tabel_analisa, tabel_bank, tabel_acc, tabel_sen_bank, tabel_sen_acc, nama_bank):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        tabel_saldo.to_excel(writer, index=False, sheet_name="Perbandingan Saldo")
        tabel_analisa.to_excel(writer, index=False, sheet_name="Analisa Mutasi")
        tabel_bank.to_excel(writer, index=False, sheet_name=f"{nama_bank} Belum Ada"[:31])
        tabel_acc.to_excel(writer, index=False, sheet_name="Accurate Tidak Ada")
        tabel_sen_bank.to_excel(writer, index=False, sheet_name=f"Sen {nama_bank}"[:31])
        tabel_sen_acc.to_excel(writer, index=False, sheet_name="Sen Accurate")
        auto_width_excel(writer)
    return output.getvalue()

# =====================================================
# MODUL GAJI KARYAWAN SHK
# =====================================================

def ekstrak_laba_bersih_dari_pdf(file):
    hasil = []
    try:
        file.seek(0)
        with pdfplumber.open(file) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                teks = page.extract_text(x_tolerance=2, y_tolerance=4) or ""
                for line in teks.splitlines():
                    line_clean = re.sub(r"\s+", " ", line).strip(); upper = line_clean.upper()
                    if "LABA BERSIH" not in upper: continue
                    if "LABA KOTOR" in upper or "LABA OPERASIONAL" in upper or "LABA SEBELUM" in upper: continue
                    angka = re.findall(r"-?\d{1,3}(?:\.\d{3})*(?:,\d{2})|-?\d{1,3}(?:,\d{3})*(?:\.\d{2})", line_clean)
                    if angka:
                        nilai = parse_rupiah_float(angka[-1])
                        if nilai != 0:
                            hasil.append({"Halaman": page_no, "Jenis": "LABA BERSIH", "Baris": line_clean, "Nilai Laba Bersih": nilai, "Nilai Format": format_rupiah_float(nilai)})
    except Exception as e:
        st.error("PDF Laba/Rugi tidak bisa dibaca."); st.write("Detail error:", e)
        return pd.DataFrame()
    df = pd.DataFrame(hasil)
    if len(df) == 0: return df
    return df.drop_duplicates(subset=["Baris", "Nilai Laba Bersih"]).reset_index(drop=True)

def pilih_laba_bersih_dari_upload(file_laba, nama_cabang, key_prefix):
    """
    Ambil LABA BERSIH dari PDF.
    Tampilan ringkas:
    - Tidak tampilkan tabel
    - Tidak tampilkan pilihan laba
    - Tidak tampilkan input koreksi manual
    - Cukup tampilkan tulisan biru nilai laba bersih
    """
    laba_bersih = 0
    df_laba_bersih = pd.DataFrame()

    if file_laba:
        df_laba_bersih = ekstrak_laba_bersih_dari_pdf(file_laba)

        if len(df_laba_bersih) > 0:
            laba_bersih = float(df_laba_bersih.loc[0, "Nilai Laba Bersih"])
            st.info(f"Laba Bersih {nama_cabang}: {format_rupiah_float(laba_bersih)}")
        else:
            st.warning(f"LABA BERSIH {nama_cabang} belum ditemukan di PDF.")
    else:
        st.info(f"Laba Bersih {nama_cabang}: {format_rupiah_float(0)}")

    return laba_bersih, df_laba_bersih



def daftar_libur_nasional_cuti_2026():
    """
    Untuk kalender kerja gaji:
    - Ahad tetap libur dari fungsi hitung_kalender_kerja.
    - Tanggal merah yang dihitung hanya Idul Adha H-1, H, H+1.
    - Libur nasional lain tidak dihitung, sesuai permintaan.
    """
    libur = {
        "2026-05-26": "H-1 Idul Adha",
        "2026-05-27": "Idul Adha",
        "2026-05-28": "H+1 Idul Adha",
    }
    return {pd.to_datetime(tgl).date(): ket for tgl, ket in libur.items()}


def hitung_kalender_kerja(tanggal_mulai, tanggal_selesai, libur_tambahan_text=""):
    tanggal_merah = daftar_libur_nasional_cuti_2026().copy()

    for baris in str(libur_tambahan_text).splitlines():
        baris = baris.strip()
        if not baris:
            continue
        tanggal_text = baris.split()[0].strip()
        try:
            tgl = pd.to_datetime(tanggal_text).date()
            tanggal_merah[tgl] = "Libur Tambahan Manual"
        except Exception:
            pass

    daftar_hari_kerja = []
    daftar_libur = []

    tanggal = tanggal_mulai
    while tanggal <= tanggal_selesai:
        if tanggal.weekday() == 6:
            daftar_libur.append({"Tanggal": tanggal, "Keterangan": "Ahad / Minggu"})
        elif tanggal in tanggal_merah:
            daftar_libur.append({"Tanggal": tanggal, "Keterangan": tanggal_merah[tanggal]})
        else:
            daftar_hari_kerja.append({"Tanggal": tanggal, "Keterangan": "Hari Kerja"})
        tanggal = tanggal + pd.Timedelta(days=1)

    df_hari_kerja = pd.DataFrame(daftar_hari_kerja)
    df_libur = pd.DataFrame(daftar_libur)

    if len(df_hari_kerja) > 0:
        df_hari_kerja["Tanggal"] = df_hari_kerja["Tanggal"].apply(format_tanggal_indonesia)

    if len(df_libur) > 0:
        df_libur["Tanggal"] = df_libur["Tanggal"].apply(format_tanggal_indonesia)

    return len(daftar_hari_kerja), df_hari_kerja, df_libur



def render_kalender_bulanan_lengkap(tanggal_mulai, tanggal_selesai, libur_tambahan_text=""):
    """
    Kalender kecil:
    - Isi kotak hanya angka tanggal
    - Warna hijau = hari kerja
    - Warna merah = libur
    - Warna abu-abu = luar bulan/periode
    - Libur: Ahad + Idul Adha H-1, H, H+1 + libur tambahan manual
    """
    nama_bulan = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember",
    }

    nama_hari = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Ahad"]

    mulai_bulan = tanggal_mulai.replace(day=1)
    akhir_bulan = (mulai_bulan + pd.offsets.MonthEnd(0)).date()

    tanggal_merah = daftar_libur_nasional_cuti_2026().copy()

    for baris in str(libur_tambahan_text).splitlines():
        baris = baris.strip()
        if not baris:
            continue
        tanggal_text = baris.split()[0].strip()
        try:
            tgl = pd.to_datetime(tanggal_text).date()
            tanggal_merah[tgl] = "Libur Tambahan Manual"
        except Exception:
            pass

    tanggal_awal_grid = mulai_bulan - pd.Timedelta(days=mulai_bulan.weekday())
    tanggal_akhir_grid = akhir_bulan + pd.Timedelta(days=(6 - akhir_bulan.weekday()))

    html = f"""
    <style>
    .kalender-card {{
        background: #111827;
        border: 1px solid #374151;
        border-radius: 14px;
        padding: 12px;
        margin-top: 6px;
        margin-bottom: 16px;
        max-width: 720px;
    }}
    .kalender-title {{
        text-align: center;
        color: #ffffff;
        font-size: 22px;
        font-weight: 800;
        margin: 2px 0 10px 0;
    }}
    .kalender-grid {{
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 5px;
    }}
    .kalender-head {{
        background: #1f2937;
        color: #f9fafb;
        border-radius: 8px;
        padding: 7px 4px;
        text-align: center;
        font-weight: 800;
        font-size: 13px;
    }}
    .kalender-cell {{
        height: 42px;
        border-radius: 9px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #374151;
        color: #ffffff;
        font-weight: 800;
        font-size: 15px;
    }}
    .kalender-cell-kerja {{
        background: #166534;
    }}
    .kalender-cell-libur {{
        background: #7f1d1d;
    }}
    .kalender-cell-luar {{
        background: #27272a;
        color: #9ca3af;
        opacity: 0.65;
    }}
    .kalender-legend {{
        display: flex;
        gap: 14px;
        justify-content: center;
        margin-top: 10px;
        color: #d1d5db;
        font-size: 12px;
    }}
    .legend-item {{
        display: flex;
        align-items: center;
        gap: 5px;
    }}
    .legend-dot {{
        width: 12px;
        height: 12px;
        border-radius: 4px;
        display: inline-block;
    }}
    .dot-kerja {{ background:#166534; }}
    .dot-libur {{ background:#7f1d1d; }}
    .dot-luar {{ background:#27272a; border:1px solid #4b5563; }}
    </style>

    <div class="kalender-card">
        <div class="kalender-title">{nama_bulan[mulai_bulan.month]} {mulai_bulan.year}</div>
        <div class="kalender-grid">
    """

    for hari in nama_hari:
        html += f'<div class="kalender-head">{hari}</div>'

    tanggal = tanggal_awal_grid

    while tanggal <= tanggal_akhir_grid:
        if tanggal.month != mulai_bulan.month:
            kelas = "kalender-cell-luar"
        elif tanggal < tanggal_mulai or tanggal > tanggal_selesai:
            kelas = "kalender-cell-luar"
        elif tanggal.weekday() == 6:
            kelas = "kalender-cell-libur"
        elif tanggal in tanggal_merah:
            kelas = "kalender-cell-libur"
        else:
            kelas = "kalender-cell-kerja"

        html += f'<div class="kalender-cell {kelas}">{tanggal.day}</div>'
        tanggal = tanggal + pd.Timedelta(days=1)

    html += """
        </div>
        <div class="kalender-legend">
            <div class="legend-item"><span class="legend-dot dot-kerja"></span>Kerja</div>
            <div class="legend-item"><span class="legend-dot dot-libur"></span>Libur</div>
            <div class="legend-item"><span class="legend-dot dot-luar"></span>Luar bulan/periode</div>
        </div>
    </div>
    """

    components.html(html, height=360, scrolling=False)


def normalisasi_nama_karyawan(teks):
    teks_asli = str(teks)
    teks = teks_asli.upper()
    teks = re.sub(r"[^A-Z0-9 ]+", " ", teks)
    teks = re.sub(r"\s+", " ", teks).strip()

    # Nama lengkap / alias karyawan SHK Makassar
    if "MUSTAKIM" in teks:
        return "M. Nur Mustakim Hamzah"
    if "TONY" in teks or "TONI" in teks or "ANWAR" in teks:
        return "Anwar Tony"
    if "IDRIS" in teks or "MAPPAKAYAH" in teks or "SIJALLING" in teks:
        return "Idris Mappakayah Dg.Sijalling"
    if "JUSRIANDI" in teks:
        return "Jusriandi"

    # Nama lengkap / alias karyawan Walet Veteran
    if "AHMAD" in teks and "LATA" in teks:
        return "Ahmad Lata"
    if "RAHMAT" in teks:
        return "Rahmat"
    if "YUSRAN" in teks:
        return "Yusran"
    if "ABRAR" in teks:
        return "Muh. Abrar"

    return str(teks_asli).strip().title()


def daftar_karyawan_shk_dan_veteran():
    return [
        {"Cabang": "SHK Makassar", "Nama": "M. Nur Mustakim Hamzah"},
        {"Cabang": "SHK Makassar", "Nama": "Anwar Tony"},
        {"Cabang": "SHK Makassar", "Nama": "Idris Mappakayah Dg.Sijalling"},
        {"Cabang": "SHK Makassar", "Nama": "Jusriandi"},
        {"Cabang": "Walet Veteran", "Nama": "Ahmad Lata"},
        {"Cabang": "Walet Veteran", "Nama": "Rahmat"},
        {"Cabang": "Walet Veteran", "Nama": "Yusran"},
        {"Cabang": "Walet Veteran", "Nama": "Muh. Abrar"},
    ]


def daftar_karyawan_bagi_hasil():
    return [
        "M. Nur Mustakim Hamzah",
        "Anwar Tony",
        "Ahmad Lata",
        "Rahmat",
    ]


def ekstrak_kehadiran_dari_excel(file):
    """
    Membaca file mentah Excel dari aplikasi hadir.
    Format yang didukung:
    Sheet: Rekap Kehadiran
    Kolom:
    - Nama
    - Jumlah Kehadiran -> Hari
    - Jumlah Terlambat -> Hari
    - Tidak Hadir
    """
    hasil = []
    semua_nama = [x["Nama"] for x in daftar_karyawan_shk_dan_veteran()]

    def angka_cell(nilai):
        try:
            if pd.isna(nilai):
                return 0
        except Exception:
            pass

        teks = str(nilai).strip()
        if teks in ["", "-", "nan", "None"]:
            return 0

        cocok = re.search(r"-?\d+(?:[.,]\d+)?", teks)
        if not cocok:
            return 0

        try:
            return float(cocok.group(0).replace(",", "."))
        except Exception:
            return 0

    try:
        file.seek(0)
        sheets = pd.read_excel(file, sheet_name=None, header=None)
    except Exception as e:
        st.error("Excel Rekap Kehadiran tidak bisa dibaca.")
        st.write("Detail error:", e)
        return pd.DataFrame()

    # Prioritaskan sheet Rekap Kehadiran karena itu ringkasan yang dibutuhkan.
    urutan_sheet = []
    for nama_sheet in sheets.keys():
        if str(nama_sheet).strip().upper() == "REKAP KEHADIRAN":
            urutan_sheet.insert(0, nama_sheet)
        else:
            urutan_sheet.append(nama_sheet)

    for nama_sheet in urutan_sheet:
        df_sheet = sheets[nama_sheet]

        # Cari baris header yang berisi Nama dan Tidak Hadir
        header_idx = None
        for idx, row in df_sheet.iterrows():
            teks_row = " ".join([str(x).strip() for x in row.tolist() if str(x).strip() not in ["", "nan", "None"]]).upper()

            if "NAMA" in teks_row and "TIDAK HADIR" in teks_row:
                header_idx = idx
                break

        if header_idx is None:
            continue

        header = [str(x).strip() for x in df_sheet.iloc[header_idx].tolist()]
        group_header = [str(x).strip() for x in df_sheet.iloc[header_idx - 1].tolist()] if header_idx > 0 else [""] * len(header)

        # Kolom nama
        nama_col = None
        for i, h in enumerate(header):
            if h.upper() == "NAMA":
                nama_col = i
                break

        if nama_col is None:
            continue

        # Kolom jumlah kehadiran: kolom "Hari" pertama setelah Nama
        hadir_col = None
        for i in range(nama_col + 1, len(header)):
            if str(header[i]).strip().upper() == "HARI":
                hadir_col = i
                break

        # Kolom terlambat: "Hari" di bawah group "Jumlah Terlambat"
        terlambat_col = None
        for i in range(len(header)):
            g = str(group_header[i]).strip().upper()
            h = str(header[i]).strip().upper()
            if "JUMLAH TERLAMBAT" in g and h == "HARI":
                terlambat_col = i
                break

        # Kolom tidak hadir
        tidak_hadir_col = None
        for i, h in enumerate(header):
            if str(h).strip().upper() == "TIDAK HADIR":
                tidak_hadir_col = i
                break

        if hadir_col is None:
            continue

        for _, row in df_sheet.iloc[header_idx + 1:].iterrows():
            nama_asli = str(row.iloc[nama_col]).strip() if nama_col < len(row) else ""

            if not nama_asli or nama_asli.lower() in ["nan", "none"]:
                continue

            nama_key = normalisasi_nama_karyawan(nama_asli)

            if nama_key not in semua_nama:
                continue

            hadir = angka_cell(row.iloc[hadir_col]) if hadir_col is not None and hadir_col < len(row) else 0
            terlambat = angka_cell(row.iloc[terlambat_col]) if terlambat_col is not None and terlambat_col < len(row) else 0
            tidak_hadir = angka_cell(row.iloc[tidak_hadir_col]) if tidak_hadir_col is not None and tidak_hadir_col < len(row) else 0

            hasil.append({
                "Nama": nama_key,
                "Jumlah Kehadiran": hadir,
                "Tidak Hadir": tidak_hadir,
                "Terlambat": terlambat,
                "Baris Asli": f"{nama_asli} | hadir={hadir} | tidak hadir={tidak_hadir} | terlambat={terlambat}",
            })

        if len(hasil) > 0:
            break

    df = pd.DataFrame(hasil)

    if len(df) == 0:
        return df

    return df.drop_duplicates(subset=["Nama"], keep="last").reset_index(drop=True)


def ekstrak_kehadiran_dari_pdf(file):
    """
    Nama fungsi lama dipertahankan agar bagian lain tidak error.
    Sekarang fungsi ini otomatis membaca:
    - Excel mentah aplikasi hadir (.xlsx/.xls)
    - PDF lama, jika sewaktu-waktu masih dipakai
    """
    nama_file = str(getattr(file, "name", "")).lower()

    if nama_file.endswith(".xlsx") or nama_file.endswith(".xls"):
        return ekstrak_kehadiran_dari_excel(file)

    hasil = []
    semua_nama = [x["Nama"] for x in daftar_karyawan_shk_dan_veteran()]

    try:
        file.seek(0)

        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                teks = page.extract_text(x_tolerance=2, y_tolerance=4) or ""

                for line in teks.splitlines():
                    line_clean = re.sub(r"\s+", " ", line).strip()
                    upper = line_clean.upper()

                    nama_key = normalisasi_nama_karyawan(line_clean)

                    if nama_key not in semua_nama:
                        continue

                    angka_hari = [int(x) for x in re.findall(r"(\d+)\s*HARI", upper)]

                    if len(angka_hari) == 0:
                        angka_hari = [int(x) for x in re.findall(r"\b\d+\b", upper)]

                    if len(angka_hari) == 0:
                        continue

                    hadir = angka_hari[0] if len(angka_hari) > 0 else 0
                    tidak_hadir = angka_hari[1] if len(angka_hari) > 1 else 0
                    terlambat = angka_hari[2] if len(angka_hari) > 2 else 0

                    hasil.append({
                        "Nama": nama_key,
                        "Jumlah Kehadiran": hadir,
                        "Tidak Hadir": tidak_hadir,
                        "Terlambat": terlambat,
                        "Baris Asli": line_clean,
                    })

    except Exception as e:
        st.error("File Rekap Kehadiran tidak bisa dibaca.")
        st.write("Detail error:", e)
        return pd.DataFrame()

    df = pd.DataFrame(hasil)
    if len(df) == 0:
        return df

    return df.drop_duplicates(subset=["Nama"], keep="last").reset_index(drop=True)


def ambil_kehadiran(df_kehadiran, nama, kolom="Jumlah Kehadiran"):
    # Default sementara kalau PDF rekap belum diupload/belum terbaca.
    # Bisa diedit manual di tabel Streamlit.
    default_hadir = {
        "M. Nur Mustakim Hamzah": 22,
        "Anwar Tony": 22,
        "Idris Mappakayah Dg.Sijalling": 0,
        "Jusriandi": 0,
        "Ahmad Lata": 20,
        "Rahmat": 18,
        "Yusran": 0,
        "Muh. Abrar": 0,
    }

    default_tidak_hadir = {
        "M. Nur Mustakim Hamzah": 0,
        "Anwar Tony": 0,
        "Idris Mappakayah Dg.Sijalling": 0,
        "Jusriandi": 0,
        "Ahmad Lata": 2,
        "Rahmat": 4,
        "Yusran": 0,
        "Muh. Abrar": 0,
    }

    default_terlambat = {
        "M. Nur Mustakim Hamzah": 0,
        "Anwar Tony": 0,
        "Idris Mappakayah Dg.Sijalling": 0,
        "Jusriandi": 0,
        "Ahmad Lata": 0,
        "Rahmat": 0,
        "Yusran": 0,
        "Muh. Abrar": 0,
    }

    nama_norm = normalisasi_nama_karyawan(nama)

    def nilai_default():
        if kolom == "Tidak Hadir":
            return default_tidak_hadir.get(nama_norm, 0)
        if kolom == "Terlambat":
            return default_terlambat.get(nama_norm, 0)
        return default_hadir.get(nama_norm, 0)

    if df_kehadiran is None or len(df_kehadiran) == 0:
        return nilai_default()

    cocok = df_kehadiran[df_kehadiran["Nama"] == nama_norm]

    if len(cocok) == 0:
        return nilai_default()

    try:
        return float(cocok.iloc[0][kolom])
    except Exception:
        return nilai_default()


def ekstrak_uang_makan_accurate(file_accurate_uang_makan):
    """
    Membaca file Excel Accurate untuk mencari nominal uang makan per karyawan.
    Cara baca dibuat fleksibel:
    - Semua sheet dibaca tanpa header
    - Setiap baris digabung jadi teks
    - Jika nama/alias karyawan ketemu, nominal terbesar pada baris itu diambil
    """
    hasil = {x["Nama"]: 0 for x in daftar_karyawan_shk_dan_veteran()}

    if not file_accurate_uang_makan:
        return hasil

    try:
        file_accurate_uang_makan.seek(0)
        sheets = pd.read_excel(file_accurate_uang_makan, sheet_name=None, header=None)
    except Exception as e:
        st.error("File Accurate Uang Makan tidak bisa dibaca.")
        st.write("Detail error:", e)
        return hasil

    semua_nama = list(hasil.keys())

    for _, df_sheet in sheets.items():
        for _, row in df_sheet.iterrows():
            cells = [str(x) for x in row.tolist() if str(x).strip() not in ["", "nan", "None"]]
            teks_baris = " ".join(cells)

            if not teks_baris.strip():
                continue

            nama_norm = normalisasi_nama_karyawan(teks_baris)
            if nama_norm not in semua_nama:
                continue

            nominal_kandidat = []

            for cell in cells:
                nilai = abs(bersih_nominal(cell))
                # Abaikan angka kecil yang biasanya tanggal/nomor bukti
                if nilai >= 1000000:  # minimal Rp10.000 dalam satuan sen
                    nominal_kandidat.append(nilai)

            if nominal_kandidat:
                # Ambil nominal terbesar dalam baris
                hasil[nama_norm] += max(nominal_kandidat)

    return hasil


def buat_tabel_uang_makan(df_kehadiran, uang_makan_per_hari, data_accurate_uang_makan=None):
    rows = []

    if data_accurate_uang_makan is None:
        data_accurate_uang_makan = {}

    for item in daftar_karyawan_shk_dan_veteran():
        cabang = item["Cabang"]
        nama = item["Nama"]
        hadir = ambil_kehadiran(df_kehadiran, nama, "Jumlah Kehadiran")
        tidak_hadir = ambil_kehadiran(df_kehadiran, nama, "Tidak Hadir")
        terlambat = ambil_kehadiran(df_kehadiran, nama, "Terlambat")

        seharusnya = float(hadir) * float(uang_makan_per_hari)
        accurate = float(nominal_ke_rupiah(data_accurate_uang_makan.get(nama, 0)))
        selisih = accurate - seharusnya

        rows.append({
            "Cabang": cabang,
            "Nama": nama,
            "Jumlah Kehadiran": hadir,
            "Tidak Hadir": tidak_hadir,
            "Terlambat": terlambat,
            "Uang Makan / Hari": uang_makan_per_hari,
            "Seharusnya Uang Makan": seharusnya,
            "Uang Makan di Accurate": accurate,
            "Selisih": selisih,
            "Status": "Cocok" if round(selisih, 2) == 0 else "Selisih",
        })

    return pd.DataFrame(rows)


def format_tabel_uang_makan(df):
    hasil = df.copy()
    for kolom in ["Uang Makan / Hari", "Seharusnya Uang Makan", "Uang Makan di Accurate", "Selisih"]:
        if kolom in hasil.columns:
            hasil[kolom] = hasil[kolom].apply(format_rupiah_float)
    return hasil



def ekstrak_total_kehilangan_barang(file_kehilangan):
    """
    Ambil nilai total kehilangan/penyesuaian barang dari file Accurate.

    Format PDF yang didukung:
    Penyesuaian Persediaan dengan kolom:
    Kode Barang | Nama Barang | Kts. | Satuan | Tipe | Total Biaya

    Aturan:
    - Jika ada baris Tipe = Pengurangan, sistem jumlahkan semua nilai Total Biaya di baris itu.
    - Contoh:
      183.801,62 + 169.000,06 + 126.415,75 = 479.217,43
    - Kalau format tidak terbaca, sistem tetap coba ambil nominal terbesar dekat Total/Jumlah.
    - Jika tetap tidak terbaca, hasil 0 dan bisa diisi manual.
    """
    if not file_kehilangan:
        return 0

    nama_file = str(getattr(file_kehilangan, "name", "")).lower()

    def rupiah_float_dari_text(teks):
        """
        Ubah angka Indonesia menjadi float rupiah.
        Contoh:
        183.801,62 -> 183801.62
        -479.217,431626 -> -479217.431626
        """
        try:
            s = str(teks).strip()
            s = s.replace("Rp", "").replace("IDR", "").replace(" ", "")
            s = s.replace("\n", "")
            if s in ["", "-", "nan", "None"]:
                return 0.0

            tanda = -1 if s.startswith("-") else 1
            s = s.lstrip("+-")

            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            else:
                # Kalau ada titik ribuan dan tidak ada koma
                if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
                    s = s.replace(".", "")

            return tanda * float(s)
        except Exception:
            return 0.0

    def ambil_nominal_dari_teks(teks):
        hasil = []
        if not teks:
            return hasil

        pola = r"[-+]?\s*(?:Rp\s*)?\d{1,3}(?:\.\d{3})+(?:,\d{1,6})?|[-+]?\s*(?:Rp\s*)?\d+(?:,\d{1,6})?"
        for m in re.findall(pola, str(teks), flags=re.IGNORECASE):
            nilai = abs(rupiah_float_dari_text(m))
            if nilai >= 1000:
                hasil.append(nilai)

        return hasil

    def ambil_total_biaya_pengurangan_dari_teks(teks):
        """
        Khusus PDF Penyesuaian Persediaan Accurate.
        Ambil nominal terakhir pada baris yang mengandung Pengurangan.
        """
        total = 0.0
        ketemu = False

        for line in str(teks).splitlines():
            line_clean = re.sub(r"\s+", " ", line).strip()
            upper = line_clean.upper()

            if "PENGURANGAN" not in upper:
                continue

            nominal = ambil_nominal_dari_teks(line_clean)

            if not nominal:
                continue

            # Di baris item, nominal Total Biaya biasanya angka terakhir.
            total += nominal[-1]
            ketemu = True

        return total if ketemu else 0.0

    kandidat = []

    try:
        file_kehilangan.seek(0)

        if nama_file.endswith(".pdf"):
            teks_semua = ""

            with pdfplumber.open(file_kehilangan) as pdf:
                for page in pdf.pages:
                    teks = page.extract_text(x_tolerance=2, y_tolerance=4) or ""
                    teks_semua += "\n" + teks

            total_pengurangan = ambil_total_biaya_pengurangan_dari_teks(teks_semua)

            if total_pengurangan > 0:
                return total_pengurangan

            # Cadangan: cari baris total/jumlah
            for line in teks_semua.splitlines():
                upper = line.upper()
                if "TOTAL" in upper or "JUMLAH" in upper:
                    kandidat.extend(ambil_nominal_dari_teks(line))

            kandidat.extend(ambil_nominal_dari_teks(teks_semua))

        elif nama_file.endswith(".xlsx") or nama_file.endswith(".xls"):
            sheets = pd.read_excel(file_kehilangan, sheet_name=None, header=None)
            total_pengurangan = 0.0
            ketemu_pengurangan = False

            for _, df_sheet in sheets.items():
                for _, row in df_sheet.iterrows():
                    cells = [str(x) for x in row.tolist() if str(x).strip() not in ["", "nan", "None"]]
                    teks_baris = " ".join(cells)
                    upper = teks_baris.upper()

                    if "PENGURANGAN" in upper:
                        nominal = ambil_nominal_dari_teks(teks_baris)
                        if nominal:
                            total_pengurangan += nominal[-1]
                            ketemu_pengurangan = True

                    if "TOTAL" in upper or "JUMLAH" in upper:
                        kandidat.extend(ambil_nominal_dari_teks(teks_baris))

            if ketemu_pengurangan and total_pengurangan > 0:
                return total_pengurangan

    except Exception as e:
        st.warning("File kehilangan barang tidak bisa dibaca otomatis. Silakan isi manual.")
        st.write("Detail:", e)
        return 0

    if not kandidat:
        return 0

    return max(kandidat)


def buat_tabel_potongan_kehilangan(nilai_shk, nilai_veteran):
    rows = []

    nilai_shk = float(nilai_shk or 0)
    nilai_veteran = float(nilai_veteran or 0)

    if nilai_shk > 0:
        rows.append({
            "Cabang": "SHK Makassar",
            "Karyawan Dipotong": "Anwar Tony",
            "Nilai Kehilangan": nilai_shk,
            "Potongan Gaji": nilai_shk,
            "Keterangan": "Kehilangan barang SHK ditanggung Pak Toni",
        })

    if nilai_veteran > 0:
        potongan_per_orang = nilai_veteran / 2
        rows.append({
            "Cabang": "Walet Veteran",
            "Karyawan Dipotong": "Ahmad Lata",
            "Nilai Kehilangan": nilai_veteran,
            "Potongan Gaji": potongan_per_orang,
            "Keterangan": "Kehilangan barang Veteran dibagi 2",
        })
        rows.append({
            "Cabang": "Walet Veteran",
            "Karyawan Dipotong": "Rahmat",
            "Nilai Kehilangan": nilai_veteran,
            "Potongan Gaji": potongan_per_orang,
            "Keterangan": "Kehilangan barang Veteran dibagi 2",
        })

    return pd.DataFrame(rows)


def format_tabel_potongan_kehilangan(df):
    hasil = df.copy()
    for kolom in ["Nilai Kehilangan", "Potongan Gaji"]:
        if kolom in hasil.columns:
            hasil[kolom] = hasil[kolom].apply(format_rupiah_float)
    return hasil


def buat_tabel_gaji_shk(df_input, laba_bersih_shk, laba_bersih_walet, hari_kerja=27, pembulatan=1000):
    data = df_input.copy()
    kolom_wajib = ["Cabang", "Nama", "Jumlah Kehadiran", "Gaji Pokok", "Persentase Laba / Gaji", "Absen / Terlambat", "Daftar Piutang Karyawan", "Potongan Tambahan Manual", "Tagihan / Kewajiban"]
    for kolom in kolom_wajib:
        if kolom not in data.columns:
            data[kolom] = 0

    data["Cabang"] = data["Cabang"].astype(str).str.strip()
    data["Nama"] = data["Nama"].astype(str).str.strip()
    data = data[data["Nama"] != ""].copy()

    for k in ["Jumlah Kehadiran", "Gaji Pokok", "Persentase Laba / Gaji", "Absen / Terlambat", "Daftar Piutang Karyawan", "Potongan Tambahan Manual", "Tagihan / Kewajiban"]:
        data[k] = pd.to_numeric(data[k], errors="coerce").fillna(0)

    data["Persentase Laba / Gaji"] = data["Persentase Laba / Gaji"].replace(0, 7.5)

    def ambil_laba_cabang(cabang):
        cabang_upper = str(cabang).upper()
        if "WALET" in cabang_upper or "VETERAN" in cabang_upper:
            return float(laba_bersih_walet)
        return float(laba_bersih_shk)

    data["Laba Bersih Cabang"] = data["Cabang"].apply(ambil_laba_cabang)
    data["Laba karyawan"] = data["Laba Bersih Cabang"] * (data["Persentase Laba / Gaji"] / 100)

    if hari_kerja <= 0:
        hari_kerja = 27

    data["Laba Harian"] = data["Laba karyawan"] / hari_kerja
    data["Pot Absen"] = data["Laba Harian"] * data["Absen / Terlambat"]
    data["Gaji Real Potong Absen"] = data["Gaji Pokok"] + data["Laba karyawan"] - data["Pot Absen"]
    data["Gaji Setelah - Pot Piutang"] = data["Gaji Real Potong Absen"] - data["Daftar Piutang Karyawan"]

    if pembulatan <= 0:
        pembulatan = 1000

    def hitung_potongan_tambahan(row):
        if row["Potongan Tambahan Manual"] > 0:
            return row["Potongan Tambahan Manual"]
        nilai = row["Gaji Setelah - Pot Piutang"]
        if nilai <= 0:
            return 0
        bawah = floor(nilai / pembulatan) * pembulatan
        return nilai - bawah

    data["Potongan tambahan"] = data.apply(hitung_potongan_tambahan, axis=1)
    data["Total Potongan Bayar Piutang"] = data["Daftar Piutang Karyawan"] + data["Potongan tambahan"]
    data["Gaji Yang Diterima"] = data["Gaji Setelah - Pot Piutang"] - data["Potongan tambahan"]
    data["Pembayaran Gaji & Bonus"] = data["Gaji Yang Diterima"]
    data["Gaji Bersih"] = data["Pembayaran Gaji & Bonus"] - data["Tagihan / Kewajiban"]

    return pd.DataFrame({
        "Cabang": data["Cabang"],
        "Nama": data["Nama"],
        "Jumlah Kehadiran": data["Jumlah Kehadiran"],
        "Gaji Pokok": data["Gaji Pokok"],
        "Persentase Laba / Gaji": data["Persentase Laba / Gaji"].apply(lambda x: f"{x:.2f}%".replace(".", ",")),
        "Laba Bersih Cabang": data["Laba Bersih Cabang"],
        "Laba karyawan": data["Laba karyawan"],
        "Laba Harian": data["Laba Harian"],
        "Absen/tidak masuk/Terlambat": data["Absen / Terlambat"],
        "Pot Absen": data["Pot Absen"],
        "Gaji Real Potong Absen": data["Gaji Real Potong Absen"],
        "Daftar Piutang Karyawan": data["Daftar Piutang Karyawan"],
        "Gaji Setelah - Pot Piutang": data["Gaji Setelah - Pot Piutang"],
        "Potongan tambahan": data["Potongan tambahan"],
        "Total Potongan Bayar Piutang": data["Total Potongan Bayar Piutang"],
        "Gaji Yang Diterima": data["Gaji Yang Diterima"],
        "Tagihan/Kewajiban": data["Tagihan / Kewajiban"],
        "Pembayaran Gaji & Bonus": data["Pembayaran Gaji & Bonus"],
        "Gaji Bersih": data["Gaji Bersih"],
    })

def format_tabel_gaji(df):
    hasil = df.copy()
    kolom_uang = ["Gaji Pokok", "Laba Bersih Cabang", "Laba karyawan", "Laba Harian", "Pot Absen", "Gaji Real Potong Absen", "Daftar Piutang Karyawan", "Gaji Setelah - Pot Piutang", "Potongan tambahan", "Total Potongan Bayar Piutang", "Gaji Yang Diterima", "Tagihan/Kewajiban", "Pembayaran Gaji & Bonus", "Gaji Bersih"]
    for kolom in kolom_uang:
        if kolom in hasil.columns: hasil[kolom] = hasil[kolom].apply(format_rupiah_float)
    return hasil

def buat_excel_gaji_shk(df_gaji_format, df_laba_gabungan, ringkasan_laba, df_hari_kerja=None, df_libur=None, df_uang_makan=None, df_potongan_kehilangan=None):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        ringkasan_laba.to_excel(writer, index=False, sheet_name="Ringkasan Laba")
        df_gaji_format.to_excel(writer, index=False, sheet_name="Gaji SHK")
        if df_laba_gabungan is not None and len(df_laba_gabungan) > 0:
            df_laba_gabungan.to_excel(writer, index=False, sheet_name="Laba Bersih Terbaca")
        if df_hari_kerja is not None and len(df_hari_kerja) > 0:
            df_hari_kerja.to_excel(writer, index=False, sheet_name="Hari Kerja")
        if df_libur is not None and len(df_libur) > 0:
            df_libur.to_excel(writer, index=False, sheet_name="Libur")

        if df_uang_makan is not None and len(df_uang_makan) > 0:
            format_tabel_uang_makan(df_uang_makan).to_excel(writer, index=False, sheet_name="Rekon Uang Makan")

        if df_potongan_kehilangan is not None and len(df_potongan_kehilangan) > 0:
            format_tabel_potongan_kehilangan(df_potongan_kehilangan).to_excel(writer, index=False, sheet_name="Potongan Hilang")

        auto_width_excel(writer)
    return output.getvalue()




def tampilkan_pdf_lokal(path_pdf, tinggi=760):
    """
    Menampilkan PDF yang ikut di-upload ke repository GitHub.
    File PDF harus berada di folder yang sama dengan app.py.
    """
    path_pdf = Path(path_pdf)

    if not path_pdf.exists():
        st.warning(f"File SOP belum ada di repository: {path_pdf.name}")
        st.info("Upload file PDF ini ke GitHub di folder yang sama dengan app.py.")
        return

    data_pdf = path_pdf.read_bytes()
    b64_pdf = base64.b64encode(data_pdf).decode("utf-8")

    st.download_button(
        "Download PDF SOP",
        data=data_pdf,
        file_name=path_pdf.name,
        mime="application/pdf"
    )

    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{b64_pdf}"
            width="100%"
            height="{tinggi}"
            style="border:1px solid #374151; border-radius:12px;">
        </iframe>
        """,
        unsafe_allow_html=True
    )


def tampilkan_flowchart_sop(judul, langkah_list):
    st.markdown("#### Flowchart SOP")

    style = """
    <style>
    .flowchart-wrap {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 10px;
        margin-top: 8px;
        margin-bottom: 22px;
    }
    .flowchart-title {
        text-align: center;
        font-size: 18px;
        font-weight: 700;
        color: #93c5fd;
        margin-bottom: 12px;
    }
    .flowchart-box {
        width: min(800px, 94%);
        color: white;
        border-radius: 16px;
        padding: 16px 20px;
        text-align: center;
        font-size: 17px;
        font-weight: 700;
        line-height: 1.45;
        border: 1px solid rgba(255,255,255,0.15);
        box-shadow: 0 6px 18px rgba(0,0,0,0.18);
    }
    .flowchart-start {
        background: linear-gradient(180deg, #15803d 0%, #166534 100%);
        border-color: #22c55e;
    }
    .flowchart-step {
        background: linear-gradient(180deg, #1f3a5f 0%, #17314f 100%);
        border-color: #3b82f6;
    }
    .flowchart-finish {
        background: linear-gradient(180deg, #b45309 0%, #92400e 100%);
        border-color: #f59e0b;
    }
    .flowchart-arrow {
        font-size: 28px;
        line-height: 1;
        color: #60a5fa;
        font-weight: bold;
    }
    .flowchart-badge {
        display: inline-block;
        font-size: 12px;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 999px;
        margin-bottom: 8px;
        background: rgba(255,255,255,0.14);
        letter-spacing: 0.3px;
    }
    </style>
    """

    items = [
        '<div class="flowchart-wrap">',
        f'<div class="flowchart-title">{judul}</div>',
        '<div class="flowchart-box flowchart-start"><div class="flowchart-badge">START</div><div>Mulai SOP</div></div>'
    ]

    total = len(langkah_list)
    if total > 0:
        items.append('<div class="flowchart-arrow">↓</div>')

    for i, langkah in enumerate(langkah_list, start=1):
        items.append(
            f'<div class="flowchart-box flowchart-step">'
            f'<div class="flowchart-badge">LANGKAH {i}</div>'
            f'<div>{langkah}</div>'
            f'</div>'
        )
        items.append('<div class="flowchart-arrow">↓</div>')

    items.append('<div class="flowchart-box flowchart-finish"><div class="flowchart-badge">FINISH</div><div>SOP Selesai</div></div>')
    items.append('</div>')

    st.markdown(style + ''.join(items), unsafe_allow_html=True)


def buat_excel_sop(df_sop):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_sop.to_excel(writer, index=False, sheet_name="SOP")
        auto_width_excel(writer)
    return output.getvalue()


# =====================================================
# UI UTAMA
# =====================================================

st.markdown("""
<div style="
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
    border: 1px solid #334155;
    border-radius: 22px;
    padding: 26px 30px;
    margin: 18px 0 22px 0;
    box-shadow: 0 10px 24px rgba(0,0,0,0.25);
">
    <div style="font-size: 34px; font-weight: 900; color: white; margin-bottom: 8px;">
        Selamat Datang, Pak Mulyadi
    </div>
    <div style="font-size: 20px; color: #dbeafe; font-weight: 600;">
        Silakan pilih mau cek apa hari ini.
    </div>
</div>
""", unsafe_allow_html=True)

# Navigasi halaman tanpa reload URL, supaya login cukup sekali.
if "menu_utama" not in st.session_state:
    st.session_state["menu_utama"] = "Beranda"

menu_utama = st.session_state["menu_utama"]

if menu_utama != "Beranda":
    if st.button("⬅️ Kembali ke Beranda", use_container_width=False):
        st.session_state["menu_utama"] = "Beranda"
        st.rerun()

if menu_utama == "Beranda":
    st.header("Mau Cek Apa, Pak?")

    st.markdown("""
    <style>
    div[data-testid="stButton"] > button {
        min-height: 145px;
        border-radius: 18px;
        border: 1px solid #374151;
        background: #111827;
        color: #ffffff;
        box-shadow: 0 6px 18px rgba(0,0,0,0.20);
        text-align: left;
        padding: 18px;
        font-size: 17px;
        font-weight: 800;
        white-space: pre-line;
        transition: transform 0.15s ease, border-color 0.15s ease, background 0.15s ease;
    }
    div[data-testid="stButton"] > button:hover {
        transform: translateY(-3px);
        border-color: #60a5fa;
        background: #172033;
        color: #ffffff;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(
            "DASHBOARD\\n\\nDashboard Harian\\n\\nRingkasan cepat saldo, absensi, gaji, uang makan, dan barang hilang.",
            use_container_width=True,
            key="card_dashboard"
        ):
            st.session_state["menu_utama"] = "Dashboard Harian"
            st.rerun()

    with col2:
        if st.button(
            "BANK\\n\\nRekonsiliasi Bank\\n\\nCek mutasi BRI, BCA, Mandiri, dan BNI dibandingkan dengan Histori Bank Accurate.",
            use_container_width=True,
            key="card_bank"
        ):
            st.session_state["menu_utama"] = "Rekonsiliasi Bank"
            st.rerun()

    with col3:
        if st.button(
            "ABSENSI\\n\\nRekap Absensi\\n\\nUpload file mentah aplikasi hadir, cek jumlah hadir, tidak hadir, terlambat, dan uang makan per cabang.",
            use_container_width=True,
            key="card_absensi"
        ):
            st.session_state["menu_utama"] = "Rekap Absensi"
            st.rerun()

    col4, col5, col6 = st.columns(3)

    with col4:
        if st.button(
            "GAJI\\n\\nGaji Karyawan\\n\\nHitung gaji bagi hasil, uang makan, potongan absen, dan potongan kehilangan barang.",
            use_container_width=True,
            key="card_gaji"
        ):
            st.session_state["menu_utama"] = "Gaji Karyawan"
            st.rerun()

    with col5:
        if st.button(
            "STOK\\n\\nStok & Barang Hilang\\n\\nUpload penyesuaian persediaan dan hitung total kehilangan per cabang.",
            use_container_width=True,
            key="card_stok_hilang"
        ):
            st.session_state["menu_utama"] = "Stok & Barang Hilang"
            st.rerun()

    with col6:
        if st.button(
            "PIUTANG\\n\\nPiutang Karyawan\\n\\nCatat pinjaman, cicilan, potongan gaji, dan sisa piutang karyawan.",
            use_container_width=True,
            key="card_piutang"
        ):
            st.session_state["menu_utama"] = "Piutang Karyawan"
            st.rerun()

    col7, col8, col9 = st.columns(3)

    with col7:
        if st.button(
            "SELFIE\\n\\nAbsensi Selfie\\n\\nKaryawan absen masuk/pulang memakai kamera HP dan foto sebagai bukti.",
            use_container_width=True,
            key="card_absensi_selfie"
        ):
            st.session_state["menu_utama"] = "Absensi Selfie"
            st.rerun()

    with col8:
        if st.button(
            "MARKETPLACE\\n\\nMarketplace / Shopee\\n\\nCatat pengecekan order, dana masuk, dan selisih biaya marketplace.",
            use_container_width=True,
            key="card_marketplace"
        ):
            st.session_state["menu_utama"] = "Marketplace / Shopee"
            st.rerun()

    with col9:
        if st.button(
            "SOP\\n\\nModul SOP\\n\\nBuka SOP kerja, tabel langkah kerja, dan flowchart operasional SHK.",
            use_container_width=True,
            key="card_sop"
        ):
            st.session_state["menu_utama"] = "Modul SOP"
            st.rerun()

    col10, col11, col12 = st.columns(3)

    with col10:
        if st.button(
            "LAPORAN\\n\\nLaporan Bulanan\\n\\nGabungkan ringkasan absensi, uang makan, gaji, barang hilang, dan catatan operasional.",
            use_container_width=True,
            key="card_laporan"
        ):
            st.session_state["menu_utama"] = "Laporan Bulanan"
            st.rerun()

    st.info("Klik kartu yang ingin dicek. Login tetap aktif saat pindah modul.")




elif menu_utama == "Absensi Selfie":
    st.header("Absensi Selfie")

    st.warning(
        "Catatan: di Streamlit Cloud, data foto tersimpan sementara di sesi aplikasi. "
        "Untuk arsip permanen, download Excel/ZIP secara berkala atau nanti kita sambungkan ke Google Sheets/Drive."
    )

    if "absensi_selfie_rows" not in st.session_state:
        st.session_state["absensi_selfie_rows"] = []

    daftar_karyawan = daftar_karyawan_shk_dan_veteran()
    nama_ke_cabang = {x["Nama"]: x["Cabang"] for x in daftar_karyawan}
    nama_karyawan = [x["Nama"] for x in daftar_karyawan]

    col_form1, col_form2, col_form3 = st.columns(3)

    with col_form1:
        nama_absen = st.selectbox("Nama Karyawan", nama_karyawan, key="selfie_nama_karyawan")

    with col_form2:
        cabang_absen = nama_ke_cabang.get(nama_absen, "")
        st.text_input("Cabang", value=cabang_absen, disabled=True)

    with col_form3:
        jenis_absen = st.selectbox("Jenis Absen", ["Masuk", "Pulang"], key="selfie_jenis_absen")

    col_jam1, col_jam2 = st.columns(2)

    with col_jam1:
        batas_jam_masuk = st.time_input(
            "Batas Jam Masuk",
            value=pd.to_datetime("09:00").time(),
            help="Dipakai untuk menandai terlambat pada absen Masuk."
        )

    with col_jam2:
        catatan_absen = st.text_input("Catatan, opsional", placeholder="Contoh: dinas luar / lupa absen / izin")

    foto_selfie = st.camera_input("Ambil Foto Selfie")

    if st.button("Simpan Absensi Selfie", use_container_width=True):
        if foto_selfie is None:
            st.error("Foto selfie wajib diambil dulu.")
        else:
            waktu_wib = datetime.utcnow() + timedelta(hours=7)
            tanggal_absen = waktu_wib.date()
            jam_absen = waktu_wib.time().replace(microsecond=0)

            terlambat = "Tidak"
            if jenis_absen == "Masuk" and jam_absen > batas_jam_masuk:
                terlambat = "Ya"

            foto_bytes = foto_selfie.getvalue()
            nama_file_foto = f"{tanggal_absen}_{nama_absen.replace(' ', '_').replace('.', '')}_{jenis_absen}_{waktu_wib.strftime('%H%M%S')}.jpg"

            st.session_state["absensi_selfie_rows"].append({
                "Tanggal": str(tanggal_absen),
                "Jam": jam_absen.strftime("%H:%M:%S"),
                "Cabang": cabang_absen,
                "Nama": nama_absen,
                "Jenis Absen": jenis_absen,
                "Terlambat": terlambat,
                "Catatan": catatan_absen,
                "Nama File Foto": nama_file_foto,
                "_foto_bytes": foto_bytes,
            })

            st.success("Absensi selfie berhasil disimpan.")
            st.rerun()

    rows_absen = st.session_state.get("absensi_selfie_rows", [])

    if len(rows_absen) > 0:
        st.subheader("Riwayat Absensi Selfie")

        df_absen_selfie = pd.DataFrame(rows_absen)
        df_absen_tampil = df_absen_selfie.drop(columns=["_foto_bytes"], errors="ignore")
        st.dataframe(df_absen_tampil, use_container_width=True)

        st.subheader("Ringkasan Absensi Selfie")

        df_masuk = df_absen_tampil[df_absen_tampil["Jenis Absen"] == "Masuk"].copy()
        if len(df_masuk) > 0:
            df_rekap_selfie = (
                df_masuk
                .groupby(["Cabang", "Nama"], as_index=False)
                .agg(
                    **{
                        "Jumlah Kehadiran": ("Tanggal", "nunique"),
                        "Terlambat": ("Terlambat", lambda x: (x == "Ya").sum()),
                    }
                )
            )
            df_rekap_selfie["Tidak Hadir"] = 0
            df_rekap_selfie = df_rekap_selfie[["Cabang", "Nama", "Jumlah Kehadiran", "Tidak Hadir", "Terlambat"]]
            st.dataframe(df_rekap_selfie, use_container_width=True)

            if st.button("Gunakan Data Selfie untuk Rekap Absensi/Gaji", use_container_width=True):
                df_sinkron = df_rekap_selfie[["Nama", "Jumlah Kehadiran", "Tidak Hadir", "Terlambat"]].copy()
                st.session_state["df_kehadiran"] = df_sinkron

                uang_makan_selfie = int(st.session_state.get("uang_makan_per_hari_rekap", 25000))
                df_um_selfie = buat_tabel_uang_makan(df_sinkron, uang_makan_selfie, {})
                kolom_rekap_um = [
                    "Cabang",
                    "Nama",
                    "Jumlah Kehadiran",
                    "Tidak Hadir",
                    "Terlambat",
                    "Uang Makan / Hari",
                    "Seharusnya Uang Makan",
                ]
                st.session_state["df_rekap_uang_makan_edit"] = df_um_selfie[kolom_rekap_um].copy()

                st.success("Data selfie sudah disinkronkan ke Rekap Absensi dan Gaji Karyawan.")

        output_absen = BytesIO()
        with pd.ExcelWriter(output_absen, engine="openpyxl") as writer:
            df_absen_tampil.to_excel(writer, index=False, sheet_name="Absensi Selfie")
            if "df_rekap_selfie" in locals() and len(df_rekap_selfie) > 0:
                df_rekap_selfie.to_excel(writer, index=False, sheet_name="Rekap")
            auto_width_excel(writer)

        st.download_button(
            "Download Rekap Absensi Selfie (.xlsx)",
            data=output_absen.getvalue(),
            file_name="rekap_absensi_selfie.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for row in rows_absen:
                if row.get("_foto_bytes"):
                    zip_file.writestr(row.get("Nama File Foto", "foto_absensi.jpg"), row["_foto_bytes"])

        st.download_button(
            "Download Semua Foto Selfie (.zip)",
            data=zip_buffer.getvalue(),
            file_name="foto_absensi_selfie.zip",
            mime="application/zip"
        )

        with st.expander("Lihat Foto Terakhir"):
            last = rows_absen[-1]
            st.write(f"{last['Nama']} - {last['Tanggal']} {last['Jam']} - {last['Jenis Absen']}")
            st.image(last["_foto_bytes"], width=260)

        if st.button("Hapus Semua Data Absensi Selfie", type="secondary"):
            st.session_state["absensi_selfie_rows"] = []
            st.rerun()
    else:
        st.info("Belum ada data absensi selfie. Pilih nama, ambil foto, lalu klik Simpan Absensi Selfie.")

elif menu_utama == "Dashboard Harian":
    st.header("Dashboard Harian")

    df_kehadiran = st.session_state.get("df_kehadiran", pd.DataFrame())
    df_uang_makan = st.session_state.get("df_rekap_uang_makan_edit", pd.DataFrame())

    total_karyawan_hadir = len(df_kehadiran) if isinstance(df_kehadiran, pd.DataFrame) else 0
    total_uang_makan = 0
    if isinstance(df_uang_makan, pd.DataFrame) and len(df_uang_makan) > 0 and "Seharusnya Uang Makan" in df_uang_makan.columns:
        total_uang_makan = pd.to_numeric(df_uang_makan["Seharusnya Uang Makan"], errors="coerce").fillna(0).sum()

    total_hilang_shk = float(st.session_state.get("dashboard_hilang_shk", 0) or 0)
    total_hilang_veteran = float(st.session_state.get("dashboard_hilang_veteran", 0) or 0)

    total_absensi_selfie = len(st.session_state.get("absensi_selfie_rows", []))

    col_a, col_b, col_c, col_d, col_e = st.columns(5)
    col_a.metric("Data Absensi Terbaca", f"{total_karyawan_hadir} karyawan")
    col_b.metric("Absensi Selfie", f"{total_absensi_selfie} data")
    col_c.metric("Total Uang Makan", format_rupiah_float(total_uang_makan))
    col_d.metric("Barang Hilang SHK", format_rupiah_float(total_hilang_shk))
    col_e.metric("Barang Hilang Veteran", format_rupiah_float(total_hilang_veteran))

    st.subheader("Catatan Harian")
    catatan_dashboard = st.text_area(
        "Catatan operasional hari ini",
        value=st.session_state.get("catatan_dashboard", ""),
        height=180,
        placeholder="Contoh: rekonsiliasi BRI sudah cocok, absensi Mei sudah diupload, barang hilang Veteran perlu dicek ulang..."
    )
    st.session_state["catatan_dashboard"] = catatan_dashboard

    st.info("Dashboard ini mengambil data dari menu Rekap Absensi, Stok & Barang Hilang, dan catatan yang Bapak isi di sini.")

elif menu_utama == "Stok & Barang Hilang":
    st.header("Stok & Barang Hilang")

    st.markdown(
        """
        Upload dokumen **Penyesuaian Persediaan** dari Accurate.
        Sistem akan menjumlahkan semua baris **Pengurangan** sebagai nilai barang hilang.
        """
    )

    col_stok1, col_stok2 = st.columns(2)

    with col_stok1:
        file_hilang_shk_dashboard = st.file_uploader(
            "Upload Penyesuaian Persediaan - SHK Makassar",
            type=["pdf", "xlsx", "xls"],
            key="stok_hilang_shk_file"
        )
        nilai_hilang_shk_dashboard = ekstrak_total_kehilangan_barang(file_hilang_shk_dashboard)
        nilai_hilang_shk_dashboard = st.number_input(
            "Total Barang Hilang SHK Makassar",
            min_value=0.0,
            value=float(nilai_hilang_shk_dashboard),
            step=1000.0,
            key=f"stok_hilang_shk_{getattr(file_hilang_shk_dashboard, 'name', 'manual')}_{round(float(nilai_hilang_shk_dashboard), 2)}"
        )
        st.session_state["dashboard_hilang_shk"] = nilai_hilang_shk_dashboard

    with col_stok2:
        file_hilang_veteran_dashboard = st.file_uploader(
            "Upload Penyesuaian Persediaan - Walet Veteran",
            type=["pdf", "xlsx", "xls"],
            key="stok_hilang_veteran_file"
        )
        nilai_hilang_veteran_dashboard = ekstrak_total_kehilangan_barang(file_hilang_veteran_dashboard)
        nilai_hilang_veteran_dashboard = st.number_input(
            "Total Barang Hilang Walet Veteran",
            min_value=0.0,
            value=float(nilai_hilang_veteran_dashboard),
            step=1000.0,
            key=f"stok_hilang_veteran_{getattr(file_hilang_veteran_dashboard, 'name', 'manual')}_{round(float(nilai_hilang_veteran_dashboard), 2)}"
        )
        st.session_state["dashboard_hilang_veteran"] = nilai_hilang_veteran_dashboard

    df_pot_hilang_dashboard = buat_tabel_potongan_kehilangan(
        nilai_hilang_shk_dashboard,
        nilai_hilang_veteran_dashboard
    )

    if len(df_pot_hilang_dashboard) > 0:
        st.subheader("Pembagian Potongan Otomatis")
        st.dataframe(format_tabel_potongan_kehilangan(df_pot_hilang_dashboard), use_container_width=True)

    st.caption("Data ini bisa menjadi acuan saat mengisi potongan di halaman Gaji Karyawan.")

elif menu_utama == "Piutang Karyawan":
    st.header("Piutang Karyawan")

    st.markdown("Catat pinjaman/piutang karyawan dan cicilan yang akan dipotong dari gaji.")

    if "df_piutang_karyawan" not in st.session_state:
        st.session_state["df_piutang_karyawan"] = pd.DataFrame([
            {"Cabang": "SHK Makassar", "Nama": "Anwar Tony", "Piutang Awal": 0, "Cicilan / Potongan Bulan Ini": 0},
            {"Cabang": "Walet Veteran", "Nama": "Ahmad Lata", "Piutang Awal": 0, "Cicilan / Potongan Bulan Ini": 0},
            {"Cabang": "Walet Veteran", "Nama": "Rahmat", "Piutang Awal": 0, "Cicilan / Potongan Bulan Ini": 0},
        ])

    df_piutang_edit = st.data_editor(
        st.session_state["df_piutang_karyawan"],
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Piutang Awal": st.column_config.NumberColumn("Piutang Awal", step=1000),
            "Cicilan / Potongan Bulan Ini": st.column_config.NumberColumn("Cicilan / Potongan Bulan Ini", step=1000),
        }
    )

    df_piutang_edit["Sisa Piutang"] = (
        pd.to_numeric(df_piutang_edit["Piutang Awal"], errors="coerce").fillna(0)
        - pd.to_numeric(df_piutang_edit["Cicilan / Potongan Bulan Ini"], errors="coerce").fillna(0)
    )

    st.session_state["df_piutang_karyawan"] = df_piutang_edit

    st.subheader("Ringkasan Piutang")
    st.dataframe(df_piutang_edit, use_container_width=True)

    total_piutang = pd.to_numeric(df_piutang_edit["Sisa Piutang"], errors="coerce").fillna(0).sum()
    st.metric("Total Sisa Piutang", format_rupiah_float(total_piutang))

elif menu_utama == "Marketplace / Shopee":
    st.header("Marketplace / Shopee")

    st.markdown(
        """
        Modul ini untuk catatan pengecekan marketplace.
        Saat ini masih berupa tabel kontrol manual agar proses order, input Accurate, dan dana masuk bisa dipantau.
        """
    )

    if "df_marketplace" not in st.session_state:
        st.session_state["df_marketplace"] = pd.DataFrame([
            {"Tanggal": "", "Marketplace": "Shopee", "No Pesanan": "", "Status": "Belum dicek", "Catatan": ""},
        ])

    df_marketplace_edit = st.data_editor(
        st.session_state["df_marketplace"],
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Marketplace": st.column_config.SelectboxColumn("Marketplace", options=["Shopee", "Tokopedia", "TikTok Shop", "Lainnya"]),
            "Status": st.column_config.SelectboxColumn("Status", options=["Belum dicek", "Sudah input Accurate", "Dana masuk", "Selisih", "Selesai"]),
        }
    )

    st.session_state["df_marketplace"] = df_marketplace_edit

    st.subheader("Ringkasan Status")
    if len(df_marketplace_edit) > 0 and "Status" in df_marketplace_edit.columns:
        st.dataframe(df_marketplace_edit["Status"].value_counts().reset_index().rename(columns={"index": "Status", "Status": "Jumlah"}), use_container_width=True)

elif menu_utama == "Laporan Bulanan":
    st.header("Laporan Bulanan")

    periode_laporan = st.text_input("Periode Laporan", value="Mei 2026")

    df_kehadiran = st.session_state.get("df_kehadiran", pd.DataFrame())
    df_uang_makan = st.session_state.get("df_rekap_uang_makan_edit", pd.DataFrame())
    df_piutang = st.session_state.get("df_piutang_karyawan", pd.DataFrame())
    df_marketplace = st.session_state.get("df_marketplace", pd.DataFrame())
    df_absensi_selfie = pd.DataFrame(st.session_state.get("absensi_selfie_rows", []))
    if len(df_absensi_selfie) > 0:
        df_absensi_selfie = df_absensi_selfie.drop(columns=["_foto_bytes"], errors="ignore")

    total_uang_makan = 0
    if isinstance(df_uang_makan, pd.DataFrame) and len(df_uang_makan) > 0 and "Seharusnya Uang Makan" in df_uang_makan.columns:
        total_uang_makan = pd.to_numeric(df_uang_makan["Seharusnya Uang Makan"], errors="coerce").fillna(0).sum()

    total_hilang_shk = float(st.session_state.get("dashboard_hilang_shk", 0) or 0)
    total_hilang_veteran = float(st.session_state.get("dashboard_hilang_veteran", 0) or 0)

    ringkasan_bulanan = pd.DataFrame([
        {"Keterangan": "Periode", "Nilai": periode_laporan},
        {"Keterangan": "Jumlah Data Absensi", "Nilai": len(df_kehadiran) if isinstance(df_kehadiran, pd.DataFrame) else 0},
        {"Keterangan": "Total Uang Makan", "Nilai": format_rupiah_float(total_uang_makan)},
        {"Keterangan": "Barang Hilang SHK Makassar", "Nilai": format_rupiah_float(total_hilang_shk)},
        {"Keterangan": "Barang Hilang Walet Veteran", "Nilai": format_rupiah_float(total_hilang_veteran)},
    ])

    st.subheader("Ringkasan")
    st.dataframe(ringkasan_bulanan, use_container_width=True)

    output_laporan = BytesIO()
    with pd.ExcelWriter(output_laporan, engine="openpyxl") as writer:
        ringkasan_bulanan.to_excel(writer, index=False, sheet_name="Ringkasan")
        if isinstance(df_kehadiran, pd.DataFrame) and len(df_kehadiran) > 0:
            df_kehadiran.to_excel(writer, index=False, sheet_name="Absensi")
        if isinstance(df_uang_makan, pd.DataFrame) and len(df_uang_makan) > 0:
            df_uang_makan.to_excel(writer, index=False, sheet_name="Uang Makan")
        if isinstance(df_piutang, pd.DataFrame) and len(df_piutang) > 0:
            df_piutang.to_excel(writer, index=False, sheet_name="Piutang")
        if isinstance(df_marketplace, pd.DataFrame) and len(df_marketplace) > 0:
            df_marketplace.to_excel(writer, index=False, sheet_name="Marketplace")
        if isinstance(df_absensi_selfie, pd.DataFrame) and len(df_absensi_selfie) > 0:
            df_absensi_selfie.to_excel(writer, index=False, sheet_name="Absensi Selfie")
        auto_width_excel(writer)

    st.download_button(
        "Download Laporan Bulanan (.xlsx)",
        data=output_laporan.getvalue(),
        file_name=f"laporan_bulanan_{periode_laporan.replace(' ', '_').lower()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif menu_utama == "Rekonsiliasi Bank":
    jenis_bank = st.radio("Pilih Bank", ["BRI", "BCA", "MANDIRI", "BNI"], horizontal=True)
    if jenis_bank == "BNI":
        file_bank = st.file_uploader("Upload PDF Mutasi BNI, bisa 1 atau lebih file", type=["pdf"], accept_multiple_files=True)
    else:
        file_bank = st.file_uploader(f"Upload PDF Mutasi {jenis_bank}", type=["pdf"])
    file_accurate = st.file_uploader("Upload Histori Bank Accurate", type=["xlsx", "xls"])
    password_mandiri = ""
    if jenis_bank == "MANDIRI":
        password_mandiri = st.text_input("Password PDF Mandiri, kalau ada", type="password")
    if file_bank and file_accurate:
        if jenis_bank == "BRI": bank, ringkasan_bank = baca_bri_pdf(file_bank)
        elif jenis_bank == "BCA": bank, ringkasan_bank = baca_bca_pdf(file_bank)
        elif jenis_bank == "MANDIRI": bank, ringkasan_bank = baca_mandiri_pdf(file_bank, password_mandiri)
        elif jenis_bank == "BNI": bank, ringkasan_bank = gabung_bni_multi(file_bank)
        else: bank, ringkasan_bank = df_bank_kosong(), {"Saldo Awal": 0, "Saldo Akhir": 0}
        accurate, ringkasan_accurate = baca_accurate(file_accurate)
        st.write(f"Saya cocokkan dari rekening koran {jenis_bank} ke Histori Bank Accurate terbaru.")
        saldo_awal_bank = ringkasan_bank.get("Saldo Awal", 0); saldo_akhir_bank = ringkasan_bank.get("Saldo Akhir", 0)
        saldo_awal_accurate = ringkasan_accurate.get("Saldo Awal", 0); saldo_akhir_accurate = ringkasan_accurate.get("Saldo Akhir", 0)
        selisih_saldo_awal = saldo_awal_bank - saldo_awal_accurate; selisih_saldo_akhir = saldo_akhir_bank - saldo_akhir_accurate
        perubahan_selisih = selisih_saldo_akhir - selisih_saldo_awal
        perbandingan_saldo = pd.DataFrame([
            {"Keterangan":"Saldo Awal", jenis_bank:format_uang(saldo_awal_bank), "Accurate":format_uang(saldo_awal_accurate), "Selisih":format_uang(selisih_saldo_awal), "Status":"Cocok" if selisih_saldo_awal == 0 else "Selisih"},
            {"Keterangan":"Saldo Akhir", jenis_bank:format_uang(saldo_akhir_bank), "Accurate":format_uang(saldo_akhir_accurate), "Selisih":format_uang(selisih_saldo_akhir), "Status":"Cocok" if selisih_saldo_akhir == 0 else "Selisih"},
            {"Keterangan":"Perubahan Selisih", jenis_bank:"", "Accurate":"", "Selisih":format_uang(perubahan_selisih), "Status":"Cocok" if perubahan_selisih == 0 else "Ada transaksi beda"},
        ])
        st.subheader("Perbandingan Saldo"); st.dataframe(perbandingan_saldo, use_container_width=True)
        st.write("Jumlah transaksi bank terbaca:", len(bank)); st.write("Jumlah transaksi Accurate terbaca:", len(accurate))
        total_debit_bank = bank[bank["Jenis"] == "Masuk"]["Nominal"].sum() if len(bank) > 0 and "Nominal" in bank.columns else 0
        total_kredit_bank = bank[bank["Jenis"] == "Keluar"]["Nominal"].sum() if len(bank) > 0 and "Nominal" in bank.columns else 0
        net_bank = total_debit_bank - total_kredit_bank
        total_debit_acc = accurate[accurate["Jenis"] == "Masuk"]["Nominal"].sum() if len(accurate) > 0 and "Nominal" in accurate.columns else 0
        total_kredit_acc = accurate[accurate["Jenis"] == "Keluar"]["Nominal"].sum() if len(accurate) > 0 and "Nominal" in accurate.columns else 0
        net_acc = total_debit_acc - total_kredit_acc; selisih_mutasi = net_bank - net_acc
        tabel_analisa_mutasi = pd.DataFrame([
            {"Keterangan":"Total Debit / Masuk", jenis_bank:format_uang(total_debit_bank), "Accurate":format_uang(total_debit_acc), "Selisih":format_uang(total_debit_bank-total_debit_acc)},
            {"Keterangan":"Total Kredit / Keluar", jenis_bank:format_uang(total_kredit_bank), "Accurate":format_uang(total_kredit_acc), "Selisih":format_uang(total_kredit_bank-total_kredit_acc)},
            {"Keterangan":"Net Mutasi", jenis_bank:format_uang(net_bank), "Accurate":format_uang(net_acc), "Selisih":format_uang(selisih_mutasi)},
        ])
        st.subheader("Analisa Selisih Mutasi"); st.dataframe(tabel_analisa_mutasi, use_container_width=True)
        tabel_sen_bank = tabel_transaksi_sen(bank, jenis_bank); tabel_sen_acc = tabel_transaksi_sen(accurate, "Accurate")
        if len(tabel_sen_bank) > 0 or len(tabel_sen_acc) > 0:
            st.subheader("Transaksi yang Mengandung Sen/Desimal")
            if len(tabel_sen_bank) > 0: st.write(f"Di {jenis_bank}:"); st.dataframe(tabel_sen_bank, use_container_width=True)
            if len(tabel_sen_acc) > 0: st.write("Di Accurate:"); st.dataframe(tabel_sen_acc, use_container_width=True)
        bank_cocok, accurate_cocok = cocokkan_pakai_sekali(bank, accurate)
        if jenis_bank in ["MANDIRI", "BNI"]:
            unmatched_bank = unmatched_berdasarkan_jenis_nominal(bank, accurate); unmatched_acc = unmatched_berdasarkan_jenis_nominal(accurate, bank)
        else:
            unmatched_bank = bank_cocok[bank_cocok["Terpakai"] == False].copy(); unmatched_acc = accurate_cocok[accurate_cocok["Terpakai"] == False].copy()
        bank_belum_ada = buat_tabel_bank_belum_ada(unmatched_bank, jenis_bank); accurate_tidak_ada = buat_tabel_accurate_tidak_ada(unmatched_acc, jenis_bank)
        st.subheader(f"1. Transaksi {jenis_bank} yang Belum Ada di Accurate")
        if len(bank_belum_ada) > 0: st.dataframe(bank_belum_ada, use_container_width=True); st.write("Jumlah:", len(bank_belum_ada))
        else: st.success(f"Tidak ada. Semua transaksi {jenis_bank} sudah terlihat di Accurate.")
        st.subheader(f"2. Transaksi Accurate yang Tidak Ada di {jenis_bank}")
        if len(accurate_tidak_ada) > 0: st.dataframe(accurate_tidak_ada, use_container_width=True); st.write("Jumlah:", len(accurate_tidak_ada))
        else: st.success(f"Tidak ada transaksi Accurate tambahan yang tidak terlihat di {jenis_bank}.")
        excel_file = buat_excel_rekon(perbandingan_saldo, tabel_analisa_mutasi, bank_belum_ada, accurate_tidak_ada, tabel_sen_bank, tabel_sen_acc, jenis_bank)
        st.download_button(label="Download File Spreadsheet (.xlsx)", data=excel_file, file_name=f"rekonsiliasi_{jenis_bank.lower()}_vs_accurate.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Pilih bank, lalu upload PDF mutasi bank dan Histori Bank Accurate.")


elif menu_utama == "Rekap Absensi":
    st.header("Rekap Absensi Karyawan")

    st.markdown(
        """
        Upload file mentah dari aplikasi hadir di halaman ini.
        Data yang sudah terbaca akan otomatis dipakai di halaman **Gaji Karyawan**.
        """
    )

    file_kehadiran = st.file_uploader(
        "Masukkan File Rekap Kehadiran Karyawan",
        type=["xlsx", "xls"],
        key="upload_rekap_kehadiran_absensi_page",
        help="Upload file mentah Excel dari aplikasi hadir. Sistem membaca sheet Rekap Kehadiran."
    )

    if "df_kehadiran" not in st.session_state:
        st.session_state["df_kehadiran"] = pd.DataFrame()

    if "df_rekap_uang_makan_edit" not in st.session_state:
        st.session_state["df_rekap_uang_makan_edit"] = pd.DataFrame()

    if file_kehadiran:
        df_kehadiran_baru = ekstrak_kehadiran_dari_pdf(file_kehadiran)

        if len(df_kehadiran_baru) > 0:
            st.session_state["df_kehadiran"] = df_kehadiran_baru
            st.success("Rekap kehadiran berhasil dimasukkan dan tersinkron ke halaman Gaji Karyawan.")
        else:
            st.warning("File kehadiran terbaca, tapi data hadir karyawan belum ditemukan. Pastikan memakai sheet Rekap Kehadiran.")

    df_kehadiran = st.session_state.get("df_kehadiran", pd.DataFrame())

    if len(df_kehadiran) > 0:
        st.subheader("Rekap Kehadiran + Uang Makan")

        uang_makan_per_hari_rekap = st.number_input(
            "Uang Makan per Hari",
            min_value=0,
            value=int(st.session_state.get("uang_makan_per_hari_rekap", 25000)),
            step=1000,
            key="uang_makan_per_hari_rekap_absensi_page"
        )
        st.session_state["uang_makan_per_hari_rekap"] = uang_makan_per_hari_rekap

        df_rekap_uang_makan = buat_tabel_uang_makan(
            df_kehadiran,
            uang_makan_per_hari_rekap,
            {}
        )

        kolom_rekap_um = [
            "Cabang",
            "Nama",
            "Jumlah Kehadiran",
            "Tidak Hadir",
            "Terlambat",
            "Uang Makan / Hari",
            "Seharusnya Uang Makan",
        ]

        df_rekap_uang_makan_edit = df_rekap_uang_makan[kolom_rekap_um].copy()
        df_rekap_uang_makan_edit["Seharusnya Uang Makan"] = (
            pd.to_numeric(df_rekap_uang_makan_edit["Jumlah Kehadiran"], errors="coerce").fillna(0)
            * pd.to_numeric(df_rekap_uang_makan_edit["Uang Makan / Hari"], errors="coerce").fillna(0)
        )

        st.session_state["df_rekap_uang_makan_edit"] = df_rekap_uang_makan_edit

        st.dataframe(
            format_tabel_uang_makan(df_rekap_uang_makan_edit),
            use_container_width=True
        )

        total_um_cabang = (
            df_rekap_uang_makan_edit
            .groupby("Cabang", as_index=False)["Seharusnya Uang Makan"]
            .sum()
        )

        total_shk_um = total_um_cabang.loc[
            total_um_cabang["Cabang"].str.contains("SHK", case=False, na=False),
            "Seharusnya Uang Makan"
        ].sum()

        total_veteran_um = total_um_cabang.loc[
            total_um_cabang["Cabang"].str.contains("Walet|Veteran", case=False, na=False),
            "Seharusnya Uang Makan"
        ].sum()

        col_um_shk, col_um_vet, col_um_all = st.columns(3)
        col_um_shk.metric("Total Uang Makan SHK Makassar", format_rupiah_float(total_shk_um))
        col_um_vet.metric("Total Uang Makan Walet Veteran", format_rupiah_float(total_veteran_um))
        col_um_all.metric("Total Uang Makan Semua Cabang", format_rupiah_float(total_shk_um + total_veteran_um))

        st.caption("Data ini otomatis dipakai di halaman Gaji Karyawan.")
    else:
        st.info("Belum ada data absensi. Upload file Excel rekap kehadiran untuk mulai.")

elif menu_utama == "Gaji Karyawan":
    st.subheader("Modul Gaji Karyawan")

    st.subheader("Periode Gaji Karyawan")
    col_periode1, col_periode2 = st.columns(2)

    with col_periode1:
        tanggal_mulai_gaji = st.date_input(
            "Dari Tanggal",
            value=pd.to_datetime("2026-05-01").date(),
            key="periode_gaji_mulai_gaji_page"
        )

    with col_periode2:
        tanggal_selesai_gaji = st.date_input(
            "Sampai Tanggal",
            value=pd.to_datetime("2026-05-31").date(),
            key="periode_gaji_selesai_gaji_page"
        )

    if tanggal_selesai_gaji < tanggal_mulai_gaji:
        st.warning("Tanggal selesai tidak boleh lebih kecil dari tanggal mulai. Sistem memakai tanggal mulai sebagai tanggal selesai.")
        tanggal_selesai_gaji = tanggal_mulai_gaji

    st.caption(
        f"Periode terpilih: {format_tanggal_indonesia(tanggal_mulai_gaji)} "
        f"s/d {format_tanggal_indonesia(tanggal_selesai_gaji)}"
    )

    st.subheader("Kalender Kerja untuk Pembagi Laba Harian")
    st.info(
        f"Periode gaji: {format_tanggal_indonesia(tanggal_mulai_gaji)} "
        f"s/d {format_tanggal_indonesia(tanggal_selesai_gaji)}"
    )

    libur_tambahan_text = st.text_area(
        "Libur Tambahan Manual, opsional",
        value="",
        placeholder="Contoh:\n2026-05-29\n2026-06-02",
        help="Isi kalau ada libur toko/libur khusus. Satu tanggal per baris. Format YYYY-MM-DD."
    )

    hari_kerja_otomatis, df_hari_kerja, df_libur = hitung_kalender_kerja(
        tanggal_mulai_gaji,
        tanggal_selesai_gaji,
        libur_tambahan_text
    )

    render_kalender_bulanan_lengkap(
        tanggal_mulai_gaji,
        tanggal_selesai_gaji,
        libur_tambahan_text
    )

    col_kal1, col_kal2 = st.columns(2)
    with col_kal1:
        st.metric("Pembagi Laba Harian Otomatis", hari_kerja_otomatis)

    with col_kal2:
        pakai_manual_hari_kerja = st.checkbox(
            "Koreksi manual pembagi laba harian",
            value=False
        )

    if pakai_manual_hari_kerja:
        hari_kerja = st.number_input(
            "Pembagi Laba Harian Manual",
            min_value=1,
            value=int(hari_kerja_otomatis) if hari_kerja_otomatis > 0 else 1,
            step=1
        )
    else:
        hari_kerja = int(hari_kerja_otomatis) if hari_kerja_otomatis > 0 else 1

    with st.expander("Lihat daftar hari kerja dan libur yang dihitung"):
        st.write("Hari Kerja:")
        st.dataframe(df_hari_kerja, use_container_width=True)

        st.write("Libur:")
        st.dataframe(df_libur, use_container_width=True)


    st.write("Upload PDF Laba/Rugi cabang SHK Makassar dan Walet Veteran. Sistem akan mengambil LABA BERSIH masing-masing cabang. Mustakim dan Toni dihitung dari SHK Makassar; Ahmad Lata dan Rahmat dihitung dari Walet Veteran.")
    col_upload1, col_upload2 = st.columns(2)
    with col_upload1:
        file_laba_shk = st.file_uploader("Upload PDF Laba / Rugi - Cabang SHK Makassar", type=["pdf"], key="upload_laba_shk")
    with col_upload2:
        file_laba_walet = st.file_uploader("Upload PDF Laba / Rugi - Cabang Walet Veteran", type=["pdf"], key="upload_laba_walet")

    st.subheader("Data Absensi Tersinkron")

    df_kehadiran = st.session_state.get("df_kehadiran", pd.DataFrame())
    df_rekap_uang_makan_edit = st.session_state.get("df_rekap_uang_makan_edit", pd.DataFrame())

    if len(df_kehadiran) > 0:
        st.success("Data absensi sudah tersedia dari halaman Rekap Absensi.")
        kolom_absensi_ringkas = ["Nama", "Jumlah Kehadiran", "Tidak Hadir", "Terlambat"]
        st.dataframe(
            df_kehadiran[[c for c in kolom_absensi_ringkas if c in df_kehadiran.columns]],
            use_container_width=True
        )
    else:
        st.warning("Belum ada data absensi. Silakan buka menu Rekap Absensi dan upload file kehadiran terlebih dahulu.")
        st.info("Gaji tetap bisa dihitung memakai nilai default, tetapi paling aman upload Rekap Absensi dulu.")

    laba_bersih_shk = 0; laba_bersih_walet = 0; df_laba_shk = pd.DataFrame(); df_laba_walet = pd.DataFrame()
    if file_laba_shk:
        laba_bersih_shk, df_laba_shk = pilih_laba_bersih_dari_upload(file_laba_shk, "SHK Makassar", "shk")
    if file_laba_walet:
        laba_bersih_walet, df_laba_walet = pilih_laba_bersih_dari_upload(file_laba_walet, "Walet Veteran", "walet")
    total_laba_bersih = laba_bersih_shk + laba_bersih_walet
    st.subheader("Ringkasan Laba Bersih")
    ringkasan_laba = pd.DataFrame([
        {"Cabang":"SHK Makassar", "Laba Bersih":format_rupiah_float(laba_bersih_shk)},
        {"Cabang":"Walet Veteran", "Laba Bersih":format_rupiah_float(laba_bersih_walet)},
        {"Cabang":"TOTAL LABA BERSIH 2 CABANG", "Laba Bersih":format_rupiah_float(total_laba_bersih)},
    ])
    st.dataframe(ringkasan_laba, use_container_width=True)
    st.success(f"Total Laba Bersih yang dipakai untuk hitung gaji: {format_rupiah_float(total_laba_bersih)}")
    col1, col3 = st.columns(2)
    with col1:
        persen_default = st.number_input("Persentase Default per Karyawan", min_value=0.0, max_value=100.0, value=7.5, step=0.5)
    with col3:
        pembulatan = st.number_input("Pembulatan Gaji", min_value=1, value=1000, step=500)
    st.subheader("Potongan Kehilangan Barang")

    st.caption(
        "Aturan: SHK Makassar dipotong ke Anwar Tony. "
        "Walet Veteran dipotong ke Ahmad Lata dan Rahmat, dibagi 2 sama rata."
    )

    col_hilang1, col_hilang2 = st.columns(2)

    with col_hilang1:
        file_kehilangan_shk = st.file_uploader(
            "Upload Penyesuaian Barang Hilang - SHK Makassar, opsional",
            type=["pdf", "xlsx", "xls"],
            key="upload_kehilangan_shk"
        )
        nilai_hilang_shk_otomatis = ekstrak_total_kehilangan_barang(file_kehilangan_shk)

        if file_kehilangan_shk and nilai_hilang_shk_otomatis > 0:
            st.success(f"Total kehilangan terbaca: {format_rupiah_float(nilai_hilang_shk_otomatis)}")
        elif file_kehilangan_shk:
            st.warning("Total kehilangan belum terbaca otomatis. Silakan isi manual.")

        nilai_hilang_shk = st.number_input(
            "Nilai Kehilangan Barang SHK Makassar",
            min_value=0.0,
            value=float(nilai_hilang_shk_otomatis),
            step=1000.0,
            key=f"nilai_hilang_shk_{getattr(file_kehilangan_shk, 'name', 'manual')}_{round(float(nilai_hilang_shk_otomatis), 2)}"
        )

    with col_hilang2:
        file_kehilangan_veteran = st.file_uploader(
            "Upload Penyesuaian Barang Hilang - Walet Veteran, opsional",
            type=["pdf", "xlsx", "xls"],
            key="upload_kehilangan_veteran"
        )
        nilai_hilang_veteran_otomatis = ekstrak_total_kehilangan_barang(file_kehilangan_veteran)

        if file_kehilangan_veteran and nilai_hilang_veteran_otomatis > 0:
            st.success(f"Total kehilangan terbaca: {format_rupiah_float(nilai_hilang_veteran_otomatis)}")
        elif file_kehilangan_veteran:
            st.warning("Total kehilangan belum terbaca otomatis. Silakan isi manual.")

        nilai_hilang_veteran = st.number_input(
            "Nilai Kehilangan Barang Walet Veteran",
            min_value=0.0,
            value=float(nilai_hilang_veteran_otomatis),
            step=1000.0,
            key=f"nilai_hilang_veteran_{getattr(file_kehilangan_veteran, 'name', 'manual')}_{round(float(nilai_hilang_veteran_otomatis), 2)}"
        )

    df_potongan_kehilangan = buat_tabel_potongan_kehilangan(
        nilai_hilang_shk,
        nilai_hilang_veteran
    )

    if len(df_potongan_kehilangan) > 0:
        st.write("Pembagian Potongan Kehilangan Barang:")
        st.dataframe(format_tabel_potongan_kehilangan(df_potongan_kehilangan), use_container_width=True)

    df_input_awal = pd.DataFrame([
        {"Cabang":"SHK Makassar", "Nama":"M. Nur Mustakim Hamzah", "Jumlah Kehadiran":ambil_kehadiran(df_kehadiran, "M. Nur Mustakim Hamzah"), "Gaji Pokok":0, "Persentase Laba / Gaji":persen_default, "Absen / Terlambat":ambil_kehadiran(df_kehadiran, "M. Nur Mustakim Hamzah", "Tidak Hadir"), "Daftar Piutang Karyawan":0, "Potongan Tambahan Manual":0, "Tagihan / Kewajiban":0},
        {"Cabang":"SHK Makassar", "Nama":"Anwar Tony", "Jumlah Kehadiran":ambil_kehadiran(df_kehadiran, "Anwar Tony"), "Gaji Pokok":0, "Persentase Laba / Gaji":persen_default, "Absen / Terlambat":ambil_kehadiran(df_kehadiran, "Anwar Tony", "Tidak Hadir"), "Daftar Piutang Karyawan":0, "Potongan Tambahan Manual":0, "Tagihan / Kewajiban":nilai_hilang_shk},
        {"Cabang":"Walet Veteran", "Nama":"Ahmad Lata", "Jumlah Kehadiran":ambil_kehadiran(df_kehadiran, "Ahmad Lata"), "Gaji Pokok":0, "Persentase Laba / Gaji":persen_default, "Absen / Terlambat":ambil_kehadiran(df_kehadiran, "Ahmad Lata", "Tidak Hadir"), "Daftar Piutang Karyawan":0, "Potongan Tambahan Manual":0, "Tagihan / Kewajiban":nilai_hilang_veteran / 2},
        {"Cabang":"Walet Veteran", "Nama":"Rahmat", "Jumlah Kehadiran":ambil_kehadiran(df_kehadiran, "Rahmat"), "Gaji Pokok":0, "Persentase Laba / Gaji":persen_default, "Absen / Terlambat":ambil_kehadiran(df_kehadiran, "Rahmat", "Tidak Hadir"), "Daftar Piutang Karyawan":0, "Potongan Tambahan Manual":0, "Tagihan / Kewajiban":nilai_hilang_veteran / 2},
    ])
    # Tabel Input Karyawan disembunyikan.
    # Data tetap dipakai otomatis dari rekap kehadiran, potongan kehilangan, dan pengaturan default.
    df_input = df_input_awal.copy()

    if total_laba_bersih > 0:
        df_gaji = buat_tabel_gaji_shk(df_input, laba_bersih_shk=laba_bersih_shk, laba_bersih_walet=laba_bersih_walet, hari_kerja=hari_kerja, pembulatan=pembulatan)
        df_gaji_format = format_tabel_gaji(df_gaji)

        # Tampilan hasil gaji disederhanakan.
        # Kolom teknis seperti Persentase 7,5%, Laba Bersih Cabang,
        # Gaji Pokok, dan beberapa kolom perantara tidak ditampilkan.
        kolom_hasil_sederhana = [
            "Cabang",
            "Nama",
            "Jumlah Kehadiran",
            "Laba karyawan",
            "Laba Harian",
            "Absen/tidak masuk/Terlambat",
            "Pot Absen",
            "Daftar Piutang Karyawan",
            "Potongan tambahan",
            "Tagihan/Kewajiban",
            "Gaji Bersih",
        ]

        df_gaji_format = df_gaji_format[
            [c for c in kolom_hasil_sederhana if c in df_gaji_format.columns]
        ]

        st.subheader("Hasil Gaji Karyawan")
        st.dataframe(df_gaji_format, use_container_width=True)
        total_laba_karyawan = df_gaji["Laba karyawan"].sum(); total_potongan = df_gaji["Total Potongan Bayar Piutang"].sum(); total_gaji_bersih = df_gaji["Gaji Bersih"].sum()
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total Laba Karyawan", format_rupiah_float(total_laba_karyawan))
        col_b.metric("Total Potongan", format_rupiah_float(total_potongan))
        col_c.metric("Total Gaji Bersih", format_rupiah_float(total_gaji_bersih))

        if len(df_potongan_kehilangan) > 0:
            total_pot_hilang = df_potongan_kehilangan["Potongan Gaji"].sum()
            st.metric("Total Potongan Kehilangan Barang", format_rupiah_float(total_pot_hilang))

        # Rekap uang makan sudah dimasukkan langsung di tabel Rekap Kehadiran.
        df_uang_makan_edit = df_rekap_uang_makan_edit.copy() if "df_rekap_uang_makan_edit" in locals() else pd.DataFrame()

        df_laba_gabungan = pd.concat([
            df_laba_shk.assign(Cabang="SHK Makassar") if len(df_laba_shk) > 0 else pd.DataFrame(),
            df_laba_walet.assign(Cabang="Walet Veteran") if len(df_laba_walet) > 0 else pd.DataFrame(),
        ], ignore_index=True)
        excel_gaji = buat_excel_gaji_shk(df_gaji_format, df_laba_gabungan, ringkasan_laba, df_hari_kerja, df_libur, df_uang_makan_edit, df_potongan_kehilangan)
        st.download_button(label="Download Gaji SHK ke Spreadsheet (.xlsx)", data=excel_gaji, file_name="gaji_karyawan_shk.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Upload PDF Laba/Rugi SHK Makassar dan/atau Walet Veteran, atau isi Laba Bersih manual.")

elif menu_utama == "Modul SOP":
    st.header("Modul SOP SHK")

    st.markdown(
        """
        Modul ini untuk menyimpan SOP kerja agar bisa dibuka langsung dari aplikasi.
        Bisa dipakai untuk SOP marketplace, Accurate, gudang, kasir, admin, dan operasional harian.
        """
    )

    pilihan_sop = st.radio(
        "Pilih SOP",
        [
            "SOP Shopee ke Accurate",
            "SOP Rekonsiliasi Bank",
            "SOP Gaji Karyawan",
            "SOP Kehilangan Barang",
            "SOP Pembuatan Dokumen SOP",
            "SOP Custom / Manual",
        ],
        horizontal=False
    )

    if pilihan_sop == "SOP Shopee ke Accurate":
        st.subheader("SOP Shopee ke Accurate")

        data_sop = [
            {
                "No": 1,
                "Tahapan": "Cek Order Shopee",
                "Penanggung Jawab": "Admin Shopee",
                "Langkah Kerja": "Buka Seller Center Shopee, masuk ke menu Perlu Dikirim, lalu pilih pesanan yang akan diproses.",
                "Output": "Order Shopee siap dicek",
            },
            {
                "No": 2,
                "Tahapan": "Validasi Data Pesanan",
                "Penanggung Jawab": "Admin Shopee",
                "Langkah Kerja": "Cek nama pelanggan, alamat, produk, jumlah, metode pengiriman, ongkir, diskon, dan total pembayaran.",
                "Output": "Data order valid",
            },
            {
                "No": 3,
                "Tahapan": "Cek Stok",
                "Penanggung Jawab": "Admin / Gudang",
                "Langkah Kerja": "Pastikan barang tersedia sesuai jumlah yang dibeli pelanggan.",
                "Output": "Barang tersedia atau perlu konfirmasi",
            },
            {
                "No": 4,
                "Tahapan": "Input Pesanan Penjualan di Accurate",
                "Penanggung Jawab": "Admin Accurate",
                "Langkah Kerja": "Buat Pesanan Penjualan. Input nama pelanggan, alamat lengkap, barang, jumlah, harga, diskon/biaya lain, dan nomor pesanan Shopee.",
                "Output": "Pesanan Penjualan Accurate dibuat",
            },
            {
                "No": 5,
                "Tahapan": "Cocokkan Total",
                "Penanggung Jawab": "Admin Accurate",
                "Langkah Kerja": "Pastikan total di Accurate sama dengan total pesanan Shopee setelah memperhitungkan diskon dan biaya.",
                "Output": "Total Accurate cocok dengan Shopee",
            },
            {
                "No": 6,
                "Tahapan": "Proses Pengiriman",
                "Penanggung Jawab": "Admin / Gudang",
                "Langkah Kerja": "Proses Pesanan Penjualan menjadi Pengiriman. Masukkan ekspedisi dan nomor resi sesuai Shopee.",
                "Output": "Pengiriman Accurate tercatat",
            },
            {
                "No": 7,
                "Tahapan": "Packing dan Serah ke Ekspedisi",
                "Penanggung Jawab": "Gudang",
                "Langkah Kerja": "Packing barang sesuai standar, tempel label, lalu serahkan ke kurir/ekspedisi.",
                "Output": "Barang dikirim",
            },
            {
                "No": 8,
                "Tahapan": "Dana Shopee Masuk",
                "Penanggung Jawab": "Admin Shopee / Keuangan",
                "Langkah Kerja": "Setelah dana masuk, konfirmasi ke admin Accurate untuk proses faktur dan pembayaran.",
                "Output": "Dana terkonfirmasi",
            },
            {
                "No": 9,
                "Tahapan": "Buat Faktur Penjualan",
                "Penanggung Jawab": "Admin Accurate",
                "Langkah Kerja": "Ubah Pengiriman menjadi Faktur Penjualan. Ganti label/keterangan faktur dengan nomor pesanan Shopee.",
                "Output": "Faktur Penjualan selesai",
            },
            {
                "No": 10,
                "Tahapan": "Input Pembayaran",
                "Penanggung Jawab": "Admin Accurate / Keuangan",
                "Langkah Kerja": "Input pembayaran sesuai dana yang diterima dari Shopee.",
                "Output": "Transaksi selesai dan siap direkonsiliasi",
            },
        ]

        df_sop = pd.DataFrame(data_sop)
        st.dataframe(df_sop, use_container_width=True)

        tampilkan_flowchart_sop(
            "SOP Shopee ke Accurate",
            [
                "Cek Order Shopee",
                "Validasi Data Pesanan",
                "Cek Stok",
                "Input Pesanan Penjualan di Accurate",
                "Cocokkan Total",
                "Proses Pengiriman",
                "Packing dan Serah ke Ekspedisi",
                "Dana Shopee Masuk",
                "Buat Faktur Penjualan",
                "Input Pembayaran",
            ]
        )

        st.download_button(
            "Download SOP Shopee ke Accurate (.xlsx)",
            data=buat_excel_sop(df_sop),
            file_name="sop_shopee_ke_accurate.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        with st.expander("Lihat versi ringkas untuk ditempel ke WhatsApp"):
            st.text_area(
                "Script SOP WA",
                value="""SOP Shopee ke Accurate

1. Buka Seller Center Shopee > Perlu Dikirim.
2. Cek detail pesanan: nama, alamat, produk, jumlah, ekspedisi, diskon, dan total.
3. Pastikan stok tersedia.
4. Input Pesanan Penjualan di Accurate.
5. Cocokkan total Accurate dengan Shopee.
6. Proses Pesanan Penjualan menjadi Pengiriman.
7. Masukkan ekspedisi dan nomor resi.
8. Packing barang dan serahkan ke ekspedisi.
9. Setelah dana Shopee masuk, ubah Pengiriman menjadi Faktur Penjualan.
10. Input pembayaran sesuai dana masuk.

Catatan:
Nomor pesanan Shopee wajib dicatat di keterangan/label agar mudah direkonsiliasi.""",
                height=320
            )

    elif pilihan_sop == "SOP Rekonsiliasi Bank":
        st.subheader("SOP Rekonsiliasi Bank")

        data_sop = [
            {"No": 1, "Tahapan": "Siapkan File", "Langkah Kerja": "Siapkan PDF mutasi bank dan Excel Histori Bank Accurate.", "Output": "File siap upload"},
            {"No": 2, "Tahapan": "Pilih Bank", "Langkah Kerja": "Pilih BRI, BCA, Mandiri, atau BNI sesuai file mutasi.", "Output": "Bank terpilih"},
            {"No": 3, "Tahapan": "Upload File", "Langkah Kerja": "Upload PDF bank dan Excel Accurate ke aplikasi.", "Output": "Data terbaca"},
            {"No": 4, "Tahapan": "Cek Selisih Saldo", "Langkah Kerja": "Periksa saldo awal, saldo akhir, dan net mutasi.", "Output": "Selisih diketahui"},
            {"No": 5, "Tahapan": "Cek Transaksi Belum Input", "Langkah Kerja": "Lihat tabel transaksi bank yang belum ada di Accurate dan transaksi Accurate yang belum ada di bank.", "Output": "Daftar koreksi"},
            {"No": 6, "Tahapan": "Input Koreksi di Accurate", "Langkah Kerja": "Input transaksi yang belum tercatat, seperti biaya admin, bunga, transfer, QRIS, top up, atau pembayaran lain.", "Output": "Accurate diperbaiki"},
            {"No": 7, "Tahapan": "Rekonsiliasi Ulang", "Langkah Kerja": "Upload ulang laporan terbaru sampai selisih menjadi 0 atau sesuai.", "Output": "Rekonsiliasi selesai"},
        ]

        df_sop = pd.DataFrame(data_sop)
        st.dataframe(df_sop, use_container_width=True)

        tampilkan_flowchart_sop(
            "SOP Rekonsiliasi Bank",
            [
                "Siapkan File",
                "Pilih Bank",
                "Upload File",
                "Cek Selisih Saldo",
                "Cek Transaksi Belum Input",
                "Input Koreksi di Accurate",
                "Rekonsiliasi Ulang",
            ]
        )

        st.download_button(
            "Download SOP Rekonsiliasi Bank (.xlsx)",
            data=buat_excel_sop(df_sop),
            file_name="sop_rekonsiliasi_bank.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    elif pilihan_sop == "SOP Gaji Karyawan":
        st.subheader("SOP Gaji Karyawan")

        data_sop = [
            {"No": 1, "Tahapan": "Tentukan Periode", "Langkah Kerja": "Isi tanggal mulai dan tanggal selesai periode gaji.", "Output": "Periode gaji terpilih"},
            {"No": 2, "Tahapan": "Upload Rekap Kehadiran", "Langkah Kerja": "Upload PDF rekap kehadiran karyawan.", "Output": "Jumlah hadir, tidak hadir, dan terlambat terbaca"},
            {"No": 3, "Tahapan": "Upload Laba/Rugi", "Langkah Kerja": "Upload PDF Laba/Rugi cabang SHK Makassar dan Walet Veteran.", "Output": "Laba bersih cabang terbaca"},
            {"No": 4, "Tahapan": "Cek Kalender Kerja", "Langkah Kerja": "Pastikan pembagi laba harian sesuai hari kerja periode tersebut.", "Output": "Pembagi laba harian benar"},
            {"No": 5, "Tahapan": "Cek Uang Makan", "Langkah Kerja": "Pastikan uang makan dihitung dari jumlah kehadiran per cabang.", "Output": "Total uang makan per cabang benar"},
            {"No": 6, "Tahapan": "Cek Potongan", "Langkah Kerja": "Masukkan potongan barang hilang/piutang/tagihan jika ada.", "Output": "Potongan masuk ke gaji"},
            {"No": 7, "Tahapan": "Finalisasi Gaji", "Langkah Kerja": "Cek hasil gaji bersih dan download Excel.", "Output": "Gaji siap dibayarkan"},
        ]

        df_sop = pd.DataFrame(data_sop)
        st.dataframe(df_sop, use_container_width=True)

        tampilkan_flowchart_sop(
            "SOP Gaji Karyawan",
            [
                "Tentukan Periode",
                "Upload Rekap Kehadiran",
                "Upload Laba/Rugi",
                "Cek Kalender Kerja",
                "Cek Uang Makan",
                "Cek Potongan",
                "Finalisasi Gaji",
            ]
        )

        st.download_button(
            "Download SOP Gaji Karyawan (.xlsx)",
            data=buat_excel_sop(df_sop),
            file_name="sop_gaji_karyawan_shk.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    elif pilihan_sop == "SOP Kehilangan Barang":
        st.subheader("SOP Kehilangan Barang")

        data_sop = [
            {"No": 1, "Tahapan": "Buat Penyesuaian Persediaan", "Langkah Kerja": "Input barang hilang di Accurate melalui Penyesuaian Persediaan dengan tipe Pengurangan.", "Output": "Dokumen IA dibuat"},
            {"No": 2, "Tahapan": "Export Dokumen", "Langkah Kerja": "Export dokumen Penyesuaian Persediaan ke PDF.", "Output": "PDF barang hilang siap"},
            {"No": 3, "Tahapan": "Upload ke Modul Gaji", "Langkah Kerja": "Upload PDF pada bagian Potongan Kehilangan Barang sesuai cabang.", "Output": "Nilai kehilangan terbaca"},
            {"No": 4, "Tahapan": "Pembagian Potongan", "Langkah Kerja": "SHK Makassar dipotong ke Anwar Tony. Walet Veteran dipotong ke Ahmad Lata dan Rahmat masing-masing 50%.", "Output": "Potongan otomatis masuk"},
            {"No": 5, "Tahapan": "Cek Hasil Gaji", "Langkah Kerja": "Pastikan potongan tampil di kolom Tagihan/Kewajiban dan mengurangi Gaji Bersih.", "Output": "Gaji bersih sudah dipotong"},
        ]

        df_sop = pd.DataFrame(data_sop)
        st.dataframe(df_sop, use_container_width=True)

        tampilkan_flowchart_sop(
            "SOP Kehilangan Barang",
            [
                "Buat Penyesuaian Persediaan",
                "Export Dokumen",
                "Upload ke Modul Gaji",
                "Pembagian Potongan",
                "Cek Hasil Gaji",
            ]
        )

        st.download_button(
            "Download SOP Kehilangan Barang (.xlsx)",
            data=buat_excel_sop(df_sop),
            file_name="sop_kehilangan_barang.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    elif pilihan_sop == "SOP Pembuatan Dokumen SOP":
        st.subheader("SOP Pembuatan Dokumen SOP")

        st.markdown(
            """
            SOP ini adalah panduan standar untuk membuat dokumen SOP di Toko Walet Veteran.
            Isinya mencakup tujuan, ruang lingkup, istilah dan definisi, urutan prosedur,
            referensi, bagan alir, lampiran, dan lembar pengesahan.
            """
        )

        data_sop = [
            {"No": 1, "Bagian": "Tujuan", "Ringkasan": "Memastikan dokumen SOP dibuat dengan kualitas yang konsisten, dapat diandalkan, dan memenuhi kebutuhan operasional."},
            {"No": 2, "Bagian": "Ruang Lingkup", "Ringkasan": "Digunakan di semua cabang atau unit usaha Toko Walet SHK dan Toko Walet Veteran."},
            {"No": 3, "Bagian": "Istilah dan Definisi", "Ringkasan": "Menjelaskan cabang/unit usaha, KOP dokumen, tujuan, ruang lingkup, istilah, prosedur, referensi, bagan alir, lampiran, dan pengesahan."},
            {"No": 4, "Bagian": "Urutan Prosedur", "Ringkasan": "Mulai dari menyiapkan dokumen SOP, menulis tujuan, ruang lingkup, istilah, prosedur, bagan alir, lampiran, pengesahan, lalu selesai."},
            {"No": 5, "Bagian": "Referensi", "Ringkasan": "Mengacu ke dokumen IK.HR.2408.001 dan IK.HR.2408.002."},
            {"No": 6, "Bagian": "Bagan Alir", "Ringkasan": "Alur mulai dari KOP SOP, tujuan, ruang lingkup, istilah, urutan prosedur, instruksi kerja, bagan alir, lampiran, lembar pengesahan, hingga selesai."},
            {"No": 7, "Bagian": "Lampiran", "Ringkasan": "Berisi contoh KOP Dokumen SOP dan Lembar Pengesahan."},
            {"No": 8, "Bagian": "Lembar Pengesahan", "Ringkasan": "Memuat perumusan oleh Mulyadi, pemeriksa oleh Achyar, dan persetujuan oleh Ahmad."},
        ]

        df_sop = pd.DataFrame(data_sop)
        st.dataframe(df_sop, use_container_width=True)

        tampilkan_flowchart_sop(
            "SOP Pembuatan Dokumen SOP",
            [
                "KOP SOP",
                "Tujuan",
                "Ruang Lingkup",
                "Istilah dan Definisi",
                "Urutan Prosedur",
                "Instruksi Kerja",
                "Bagan Alir",
                "Lampiran",
                "Lembar Pengesahan",
            ]
        )

        st.markdown("#### File PDF SOP")
        tampilkan_pdf_lokal("SOP_Pembuatan_Dokumen_SOP.pdf", tinggi=760)

        st.download_button(
            "Download Ringkasan SOP Pembuatan Dokumen SOP (.xlsx)",
            data=buat_excel_sop(df_sop),
            file_name="sop_pembuatan_dokumen_sop.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.subheader("SOP Custom / Manual")

        st.markdown("Tulis SOP manual di bawah ini. Bisa dicopy atau dijadikan catatan sementara.")

        judul_sop = st.text_input("Judul SOP", value="SOP Baru")
        isi_sop = st.text_area(
            "Isi SOP",
            value="""1. 
2. 
3. 
4. 
5. """,
            height=300
        )

        df_sop = pd.DataFrame([
            {"Judul": judul_sop, "Isi SOP": isi_sop}
        ])

        st.download_button(
            "Download SOP Custom (.xlsx)",
            data=buat_excel_sop(df_sop),
            file_name="sop_custom.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

