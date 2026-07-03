# -*- coding: utf-8 -*-
"""
app.py ENTEGRASYONU
====================
1) app.py'nin en üstüne ekleyin:
       from veri_kaynagi import tjk_program_cek, hkjc_racecard_cek, form_skoru_hesapla

2) 'Bülten Yükle' sekmesindeki PDF yükleyicinin ÜSTÜNE aşağıdaki bloğu ekleyin.
   PDF alanı yedek olarak kalabilir; artık ana yol otomatik çekimdir.

3) Bu blok run_quantum_core'u HİÇ ÇAĞIRMAZ — sonuçlar gerçek racecard'dan
   gelir ve form_skoru_hesapla ile şeffaf biçimde puanlanır. Sahte 40 katman
   animasyonunu, sabit ROI grafiklerini ve "lobi sinyali" metinlerini
   kaldırmanız/yeniden etiketlemeniz önerilir (aşağıda etiket haritası var).
"""

# ============ BÜLTEN YÜKLE SEKMESİNE EKLENECEK BLOK ============
import streamlit as st
from veri_kaynagi import tjk_program_cek, hkjc_racecard_cek, form_skoru_hesapla

st.markdown("### 🌐 Otomatik Bülten Çekimi (PDF'e gerek kalmadan)")
kaynak = st.radio("Veri Kaynağı:", ["TJK (Türkiye)", "HKJC Sha Tin", "HKJC Happy Valley"], horizontal=True)

sehir = None
if kaynak == "TJK (Türkiye)":
    sehir = st.selectbox("Hipodrom:", ["İstanbul", "Bursa", "İzmir", "Ankara", "Adana",
                                        "Şanlıurfa", "Elazığ", "Diyarbakır", "Antalya", "Kocaeli"])

if st.button("🌐 SEÇİLİ TARİHİN BÜLTENİNİ ÇEK VE PUANLA", use_container_width=True):
    with st.spinner("Racecard indiriliyor ve form skorları hesaplanıyor..."):
        try:
            if kaynak == "TJK (Türkiye)":
                races = tjk_program_cek(date_str, sehir)          # date_str app.py'de zaten var
            else:
                pist = "ST" if "Sha Tin" in kaynak else "HV"
                races = hkjc_racecard_cek(date_str, pist)

            if not races:
                st.error("❌ Bu tarihte seçili pistte koşu bulunamadı veya sayfa yapısı değişmiş. "
                         "PDF/metin yükleme yolunu kullanabilirsiniz.")
            else:
                races = form_skoru_hesapla(races)
                st.session_state['quantum_results'] = races
                st.session_state['analyzed'] = True
                st.session_state['loaded_date'] = date_str
                toplam_at = sum(len(r['horses']) for r in races)
                st.success(f"✅ {len(races)} koşu, {toplam_at} at çekildi ve form skoru hesaplandı.")
                if API_URL:
                    try:
                        import json as _json, requests as _req
                        _req.post(API_URL, json={"Tarih": date_str, "Kosu_No": "BÜLTEN_DATA",
                                                 "Gelen_At": "SYSTEM", "Detay": _json.dumps(races)},
                                  timeout=10)
                    except Exception as e:
                        st.warning(f"⚠️ Bulut arşive yazılamadı: {e}")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Veri çekilemedi: {e}")
# ================================================================

# ETİKET HARİTASI — arayüzde dürüst isimlendirme için değiştirin:
#   "Biyo-Mekanik"  ->  "Son 6 Koşu Formu"
#   "Aerodinamik"   ->  "Rating / Handikap P."
#   "Lobi Sinyali"  ->  "Kilo Avantajı"
#   "Sinerji"       ->  "Start Pozisyonu"
# Ve kaldırılması önerilenler (uydurma veri gösteriyorlar):
#   - Dashboard'daki sabit ROI/pist başarı/isabet grafikleri
#     (gerçek sonuç girişleriyle hesaplanana kadar)
#   - "40 katman" time.sleep animasyonu
#   - Sabit hava durumu / "28°C" telemetri kartı
#     (isterseniz Open-Meteo API'den gerçek hava verisi eklenebilir)
#   - "Value Bet" rozeti (gerçek oran verisi bağlanana kadar)
