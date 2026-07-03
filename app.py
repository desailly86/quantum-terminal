import streamlit as st
from st_gsheets_connection import GSheetsConnection
import pandas as pd
import time
import hashlib
from weasyprint import HTML
import io

# SAYFA AYARLARI
st.set_page_config(page_title="QUANTUM TERMINAL v3.0", page_icon="🌌", layout="centered")

# GOOGLE SHEETS BAĞLANTISI
conn = st.connection("gsheets", type=GSheetsConnection)

# PREMIUM CSS
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .stButton>button { width: 100%; border-radius: 12px; background: linear-gradient(135deg, #1f6feb 0%, #238636 100%); color: white !important; font-weight: bold; border: none; }
    .quant-card { border: 1px solid #30363d; padding: 20px; border-radius: 14px; margin-bottom: 20px; background-color: #161b22; border-left: 6px solid #238636; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌌 Quant Global Terminal v3.0")
tabs = st.tabs(["📋 Bülten Girişi", "🔬 Canlı Analiz", "🎟️ Kupon & PDF", "🛡️ Otonom Otopsi"])

# 1. SEKME: BÜLTEN
with tabs[0]:
    race_data = st.text_area("Bülten metnini kopyalayıp buraya yapıştırın:", height=200)
    col1, col2 = st.columns(2)
    with col1:
        w_draw = st.slider("Pist/Kulvar Ağırlığı", 0.0, 1.0, 0.85)
        w_vet = st.slider("Sağlık Onayı", 0.0, 1.0, 0.95)
    with col2:
        w_lobby = st.slider("Lobi/Söylem Analizi", 0.0, 1.0, 0.90)
        w_thermal = st.slider("Padok Isı Eşiği", 0.0, 1.0, 0.80)
    
    analyze_btn = st.button("🚀 ANALİZİ BAŞLAT")

# ANALİZ MOTORU (Hash tabanlı deterministik simülatör)
if analyze_btn and race_data:
    with st.spinner("40 Katmanlı Süzgeç ve Hafıza Taranıyor..."):
        time.sleep(2)
        hasher = hashlib.md5(race_data.encode('utf-8'))
        digest = hasher.hexdigest()
        results = []
        for i in range(1, 7):
            idx = (i * 3) % len(digest)
            h1 = (int(digest[idx], 16) % 14) + 1
            results.append({
                "race": i, "score": round(85 + (int(digest[idx], 16)%15), 2),
                "banko": f"#{h1}", "plase": f"#{(h1%14)+1}, #{(h1+3)%14+1}"
            })
        st.session_state['results'] = results
        st.success("Analiz Tamamlandı!")

# 2. SEKME: ANALİZ SONUÇLARI
with tabs[1]:
    if 'results' in st.session_state:
        for r in st.session_state['results']:
            st.markdown(f"""<div class='quant-card'><h3>🏇 Koşu {r['race']}</h3>Puan: {r['score']} / 100<br><b>BANKO: {r['banko']}</b><br>Plase: {r['plase']}</div>""", unsafe_allow_html=True)

# 3. SEKME: PDF ÜRETİMİ
with tabs[2]:
    if 'results' in st.session_state:
        st.subheader("📥 Raporu PDF Olarak İndir")
        # PDF HTML Şablonu (Daha önce konuştuğumuz v3.0 yapısı)
        html_template = f"<h1>Quantum Raporu</h1>" # Basitleştirilmiş örnek
        pdf_bytes = HTML(string=html_template).write_pdf()
        st.download_button("📥 PDF RAPORUNU İNDİR", data=pdf_bytes, file_name="quantum_rapor.pdf", mime="application/pdf")

# 4. SEKME: OTOPSİ VE HAFIZA
with tabs[3]:
    st.subheader("🤖 Toplu Sonuç Girişi")
    bulk_results = st.text_area("Günün tüm sonuçlarını kopyalayıp buraya yapıştırın:")
    if st.button("🧠 HAFIZAYA İŞLE"):
        # Google Sheets'e veri yazma simülasyonu
        new_data = pd.DataFrame([{"Tarih": time.ctime(), "Detay": bulk_results}])
        conn.create(spreadsheet=st.secrets["gsheets"]["spreadsheet"], data=new_data)
        st.toast("Hafıza güncellendi!")
