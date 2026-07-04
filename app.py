# -*- coding: utf-8 -*-
"""
AVELOR — Yarış Analiz Masası
Tasarım: beyaz zemin, siyah metin, Candara; gri kabartmalı butonlar.
Motor: sha_tin_motoru (38 gerçek kriter + öğrenen ağırlıklar), veri_kaynagi (TJK/HKJC çekiciler).
"""
import json
import re
import datetime
import requests
import pandas as pd
import streamlit as st
from pypdf import PdfReader

# ---------------------------------------------------------------- MOTORLAR
try:
    from sha_tin_motoru import (pdf_ayristir, analiz_et, agirliklari_guncelle,
                                VARSAYILAN_AGIRLIKLAR, KATEGORI_ADLARI)
    SHA_TIN_HAZIR = True
except ImportError:
    SHA_TIN_HAZIR = False

try:
    from veri_kaynagi import tjk_program_cek, hkjc_racecard_cek, form_skoru_hesapla
    VERI_KAYNAGI_HAZIR = True
except ImportError:
    VERI_KAYNAGI_HAZIR = False

try:
    from weasyprint import HTML
    PDF_HAZIR = True
except Exception:
    PDF_HAZIR = False

st.set_page_config(page_title="AVELOR — Yarış Analiz Masası", page_icon="🏇",
                   layout="wide", initial_sidebar_state="expanded")
API_URL = st.secrets.get("API_URL", "")

# ---------------------------------------------------------------- TEMA
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Questrial&display=swap');
:root{
  --kagit:#FFFFFF; --murekkep:#111111; --kursun:#6A6A6A;
  --cizgi:#DCDCDC; --gumus-acik:#F5F5F5; --gumus:#E2E2E2; --gumus-koyu:#BFBFBF;
}
html, body, .stApp, [data-testid="stSidebar"]{
  font-family: Candara, "Questrial", "Gill Sans", "Segoe UI", Optima, sans-serif !important;
}
.stApp{ background: var(--kagit); color: var(--murekkep); }
[data-testid="stSidebar"]{ background:#FAFAFA; border-right:1px solid var(--cizgi); }
h1,h2,h3,h4{ color:var(--murekkep) !important; font-weight:600; letter-spacing:.2px; }
p, li, label, .stMarkdown{ color:var(--murekkep); }
small, .stCaption, [data-testid="stCaptionContainer"]{ color:var(--kursun) !important; }
hr{ border-color:var(--cizgi); }

/* ---- GRİ 3B BUTONLAR ---- */
.stButton>button, .stDownloadButton>button{
  font-family:inherit; color:var(--murekkep);
  background:linear-gradient(180deg, var(--gumus-acik) 0%, var(--gumus) 100%);
  border:1px solid var(--gumus-koyu); border-radius:6px;
  box-shadow:0 3px 0 var(--gumus-koyu), 0 4px 6px rgba(0,0,0,.08);
  transition:all .08s ease; font-weight:600;
}
.stButton>button:hover{ background:linear-gradient(180deg,#FFFFFF,#EAEAEA); color:var(--murekkep); border-color:#9E9E9E; }
.stButton>button:active{ transform:translateY(2px); box-shadow:0 1px 0 var(--gumus-koyu); }
.stButton>button[kind="primary"]{
  color:#FFFFFF; background:linear-gradient(180deg,#4B4B4B 0%,#2C2C2C 100%);
  border:1px solid #1E1E1E; box-shadow:0 3px 0 #1E1E1E, 0 4px 8px rgba(0,0,0,.18);
}
.stButton>button[kind="primary"]:hover{ background:linear-gradient(180deg,#5A5A5A,#333333); color:#fff; }

/* ---- RACECARD KARTLARI ---- */
.kart{ border:1px solid var(--cizgi); border-radius:8px; background:#FFF;
       padding:14px 18px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,.05); }
.kosu-baslik{ display:flex; align-items:center; gap:12px; border-bottom:2px solid var(--murekkep);
              padding-bottom:8px; margin-bottom:10px; }
.kosu-no{ background:var(--murekkep); color:#FFF; font-weight:700; font-size:20px;
          width:42px; height:42px; display:flex; align-items:center; justify-content:center; border-radius:6px; }
.kosu-meta{ color:var(--kursun); font-size:13px; letter-spacing:.6px; text-transform:uppercase; }
.at-satir{ display:grid; grid-template-columns:34px 30px 1fr 140px 56px; gap:10px;
           align-items:center; padding:7px 4px; border-bottom:1px solid #EFEFEF; }
.at-satir:last-child{ border-bottom:none; }
.sira{ font-weight:700; color:var(--kursun); }
.atno{ border:1px solid var(--murekkep); border-radius:4px; text-align:center;
       font-weight:700; font-size:13px; padding:1px 0; }
.atadi{ font-weight:600; } .atalt{ color:var(--kursun); font-size:12px; }
.bar-kap{ background:var(--gumus-acik); border:1px solid var(--cizgi); border-radius:4px; height:14px; overflow:hidden; }
.bar-ic{ background:var(--murekkep); height:100%; }
.skor{ font-weight:700; text-align:right; font-variant-numeric:tabular-nums; }
.rozet{ display:inline-block; border:1px solid var(--cizgi); border-radius:4px;
        padding:1px 8px; font-size:12px; color:var(--kursun); margin-right:6px; background:var(--gumus-acik);}
.banko{ border:2px solid var(--murekkep); border-radius:8px; padding:12px 16px; background:var(--gumus-acik); }
[data-testid="stMetricValue"]{ color:var(--murekkep); }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- OTURUM
def _init(anahtar, deger):
    if anahtar not in st.session_state:
        st.session_state[anahtar] = deger

_init("menu", "Masa")
_init("quantum_results", [])
_init("analyzed", False)
_init("loaded_date", "")
_init("ogrenme_agirliklari", dict(VARSAYILAN_AGIRLIKLAR) if SHA_TIN_HAZIR else None)
_init("isabet_gecmisi", [])

# ---------------------------------------------------------------- YAN MENÜ
with st.sidebar:
    st.markdown("## 🏇 AVELOR")
    st.caption("Yarış Analiz Masası — Sha Tin & TJK")
    varsayilan_kullanici = st.query_params.get("u", "")
    kullanici = st.text_input("Kullanıcı adı", value=varsayilan_kullanici,
                              placeholder="ör. ali", help="Bültenleriniz bu ada kayıtlı tutulur; "
                              "başka cihazdan aynı adı yazınca aynı verileri görürsünüz.").strip().lower()
    if kullanici and st.query_params.get("u", "") != kullanici:
        st.query_params["u"] = kullanici
        st.session_state["loaded_date"] = ""  # kullanıcı değişti → yeniden yükle
    secili_tarih = st.date_input("Yarış günü", datetime.date.today(), format="DD.MM.YYYY")
    date_str = secili_tarih.isoformat()
    st.write("---")
    for ad, ikon in [("Masa", "📊"), ("Bülten", "📥"), ("Analiz", "🔬"),
                     ("Detay", "📝"), ("Tahmin", "🎟️"), ("Sonuç & Öğrenme", "🧠")]:
        if st.button(f"{ikon} {ad}", use_container_width=True,
                     type="primary" if st.session_state["menu"] == ad else "secondary"):
            st.session_state["menu"] = ad
            st.rerun()
    st.write("---")
    if SHA_TIN_HAZIR and st.session_state["ogrenme_agirliklari"]:
        st.caption("Aktif model ağırlıkları")
        for k, v in st.session_state["ogrenme_agirliklari"].items():
            st.caption(f"{KATEGORI_ADLARI[k]}: %{v*100:.0f}")

# ---------------------------------------------------------------- BULUT YÜKLEME
# ---------------------------------------------------------------- BULUT KALICI HAFIZA
def buluta_kaydet(analiz, tarih):
    """Analizi koşu başına satır olarak kaydeder (tek hücre sınırına takılmadan)."""
    if not API_URL:
        return "API_URL tanımlı değil; veriler yalnızca bu oturumda durur."
    sahip = kullanici or "ortak"
    try:
        for r in analiz:
            requests.post(API_URL, json={"Tarih": tarih, "Kosu_No": f"BULTEN_R{r['race_no']}",
                                         "Gelen_At": sahip, "Detay": json.dumps(r)}, timeout=15)
        return None
    except requests.RequestException as e:
        return f"Buluta kaydedilemedi (analiz yerelde duruyor): {e}"


if st.session_state["loaded_date"] != date_str:
    st.session_state.update(analyzed=False, quantum_results=[], loaded_date=date_str)
    if API_URL:
        try:
            yanit = requests.get(API_URL, timeout=15); yanit.raise_for_status()
            sahip = kullanici or "ortak"
            kosu_map, eski_format = {}, None
            for satir in yanit.json():
                if str(satir.get("Tarih", ""))[:10] != date_str:
                    continue
                kno = str(satir.get("Kosu_No", ""))
                if kno.startswith("BULTEN_R") and str(satir.get("Gelen_At", "")) == sahip:
                    try:
                        r = json.loads(satir.get("Detay", "{}"))
                        kosu_map[r.get("race_no", kno)] = r  # aynı koşu tekrar kaydedildiyse sonuncusu geçerli
                    except ValueError:
                        pass
                elif kno == "BÜLTEN_DATA":  # eski format — geriye uyumluluk
                    try: eski_format = json.loads(satir.get("Detay", "[]"))
                    except ValueError: pass
                elif kno == "AGIRLIKLAR" and SHA_TIN_HAZIR and str(satir.get("Gelen_At", "")) in (sahip, "OGRENME"):
                    try:
                        st.session_state["ogrenme_agirliklari"] = json.loads(satir.get("Detay", "{}")).get(
                            "w", st.session_state["ogrenme_agirliklari"])
                    except (ValueError, AttributeError):
                        pass
            yuklenen = [kosu_map[k] for k in sorted(kosu_map, key=lambda x: int(x))] if kosu_map else (eski_format or [])
            if yuklenen:
                st.session_state.update(quantum_results=yuklenen, analyzed=True)
        except (requests.RequestException, ValueError) as e:
            st.sidebar.warning(f"Bulut arşivine ulaşılamadı: {e}")

res = st.session_state["quantum_results"]
menu = st.session_state["menu"]


# ---------------------------------------------------------------- YARDIMCILAR
def kategori_rozetleri(h):
    return (f"<span class='rozet'>Form %{h.get('bio', 0):.0f}</span>"
            f"<span class='rozet'>Rating %{h.get('aero', 0):.0f}</span>"
            f"<span class='rozet'>İnsan %{h.get('lobby', 0):.0f}</span>"
            f"<span class='rozet'>Koşul %{h.get('syn', 0):.0f}</span>")


def kosu_karti(r, ilk_n=None):
    atlar = [h for h in r["horses"] if not h.get("yedek")]
    gorunen = atlar[:ilk_n] if ilk_n else atlar
    satirlar = ""
    for i, h in enumerate(gorunen, 1):
        alt = " · ".join(x for x in [h.get("jockey") or h.get("jockey_full") or "",
                                     f"Draw {h.get('draw') or h.get('start') or '—'}",
                                     f"Rt {h.get('rt') if h.get('rt') is not None else h.get('hp', '—')}"] if x)
        satirlar += (f"<div class='at-satir'><div class='sira'>{i}.</div>"
                     f"<div class='atno'>{h['num']}</div>"
                     f"<div><div class='atadi'>{h['name']}</div><div class='atalt'>{alt}</div></div>"
                     f"<div class='bar-kap'><div class='bar-ic' style='width:{min(100, h.get('score', 0))}%'></div></div>"
                     f"<div class='skor'>{h.get('score', 0)}</div></div>")
    yedek_not = ", ".join(f"{h['num']} {h['name']}" for h in r["horses"] if h.get("yedek"))
    if yedek_not:
        satirlar += f"<div class='atalt' style='padding-top:6px'>Yedekler: {yedek_not}</div>"
    st.markdown(
        f"<div class='kart'><div class='kosu-baslik'><div class='kosu-no'>{r['race_no']}</div>"
        f"<div><b>{r.get('name', 'KOŞU')}</b><div class='kosu-meta'>{r.get('time', '')} · "
        f"{r.get('distance', '')}m · {r.get('surface', '')} · {r.get('class', '')}</div></div></div>"
        f"{satirlar}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- PDF RAPORU
def rapor_html(analiz, tarih, agirliklar):
    """Beyaz zemin, siyah metin, Candara — matbu racecard estetiğinde A4 rapor."""
    try:
        guzel_tarih = datetime.date.fromisoformat(tarih).strftime("%d.%m.%Y")
    except ValueError:
        guzel_tarih = tarih
    kosu_bloklari = ""
    for r in analiz:
        atlar = [h for h in r["horses"] if not h.get("yedek")][:5]
        satirlar = "".join(
            f"<tr><td class='n'>{i}</td><td class='n'>{h['num']}</td><td class='ad'>{h['name']}</td>"
            f"<td>{h.get('jockey') or h.get('jockey_full') or '—'}</td>"
            f"<td class='n'>{h.get('rt', h.get('hp')) if h.get('rt', h.get('hp')) is not None else '—'}</td>"
            f"<td class='n'>{h.get('draw', h.get('start')) or '—'}</td>"
            f"<td class='n'>{h.get('bio', 0):.0f}</td><td class='n'>{h.get('aero', 0):.0f}</td>"
            f"<td class='n'>{h.get('lobby', 0):.0f}</td><td class='n'>{h.get('syn', 0):.0f}</td>"
            f"<td class='n skor'>{h.get('score', 0)}</td></tr>"
            for i, h in enumerate(atlar, 1))
        kosu_bloklari += f"""
        <div class="kosu">
          <div class="kbaslik"><span class="kno">{r['race_no']}</span>
            <span class="kad">{r.get('name', 'KOŞU')}</span>
            <span class="kmeta">{r.get('time', '')} · {r.get('distance', '')}m · {r.get('surface', '')} · {r.get('class', '')}</span></div>
          <table><thead><tr><th>Sıra</th><th>No</th><th>At</th><th>Jokey</th><th>Rt</th><th>Draw</th>
            <th>Form</th><th>Rating</th><th>İnsan</th><th>Koşul</th><th>Skor</th></tr></thead>
          <tbody>{satirlar}</tbody></table>
        </div>"""
    agirlik_satiri = " · ".join(f"{KATEGORI_ADLARI[k]} %{v*100:.0f}" for k, v in (agirliklar or {}).items()) \
        if SHA_TIN_HAZIR and agirliklar else "varsayılan"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      @page {{ size:A4; margin:16mm 14mm; }}
      body {{ font-family: Candara, 'DejaVu Sans', sans-serif; color:#111; font-size:10.5px; }}
      .ust {{ border-bottom:3px solid #111; padding-bottom:6px; margin-bottom:12px;
              display:flex; justify-content:space-between; align-items:baseline; }}
      .marka {{ font-size:22px; font-weight:700; letter-spacing:1px; }}
      .tarih {{ font-size:13px; color:#555; }}
      .kosu {{ margin-bottom:12px; page-break-inside:avoid; }}
      .kbaslik {{ border-bottom:1.5px solid #111; padding-bottom:3px; margin-bottom:4px; }}
      .kno {{ background:#111; color:#fff; font-weight:700; padding:2px 8px; border-radius:3px; margin-right:8px; }}
      .kad {{ font-weight:700; }} .kmeta {{ color:#666; font-size:9.5px; margin-left:8px; text-transform:uppercase; }}
      table {{ width:100%; border-collapse:collapse; }}
      th {{ text-align:left; color:#666; font-weight:600; font-size:9px; text-transform:uppercase;
            border-bottom:1px solid #bbb; padding:2px 4px; }}
      td {{ padding:3px 4px; border-bottom:1px solid #eee; }}
      td.n {{ text-align:center; font-variant-numeric:tabular-nums; }}
      td.ad {{ font-weight:700; }} td.skor {{ font-weight:700; }}
      tbody tr:first-child td {{ background:#F2F2F2; }}
      .alt {{ margin-top:10px; border-top:1px solid #bbb; padding-top:6px; color:#666; font-size:8.5px; }}
    </style></head><body>
      <div class="ust"><div class="marka">AVELOR — GÜNLÜK TAHMİN RAPORU</div>
        <div class="tarih">{guzel_tarih}</div></div>
      {kosu_bloklari}
      <div class="alt">Skorlar, resmi racecard verilerinden (rating, form, jokey/antrenör istatistikleri,
      12 aylık draw tabloları, deneme koşuları, veteriner kayıtları) hesaplanan 40 kriterin ağırlıklı
      ortalamasıdır. Aktif ağırlıklar: {agirlik_satiri}. Bu rapor bir kazanç garantisi değildir;
      sorumlu oynayın.</div>
    </body></html>"""


# ================================================================ MASA
ONCELIKLI = ["B9", "B10", "C3", "D7", "C2", "B3", "B2", "A3", "B6"]  # kullanıcı gözlem önceliği

def oncelik_puani(h):
    kriterler = h.get("kriterler") or {}
    degerler = [v for a, v in kriterler.items() if a.split()[0] in ONCELIKLI]
    return sum(degerler) / len(degerler) if degerler else h.get("score", 0)

if menu == "Masa":
    st.markdown("# Masa")
    st.caption(f"{secili_tarih.strftime('%d.%m.%Y')} · "
               f"Öncelikli kriterler: {', '.join(ONCELIKLI)} (mesafe/pist rekoru, jokey-antrenör, "
               f"zemin, form, kilo, kariyer)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Yüklü bülten", f"{len(res)} koşu" if res else "yok")
    c2.metric("Puanlanan at", sum(len(r["horses"]) for r in res) if res else 0)
    top1 = sum(x["top1"] for x in st.session_state["isabet_gecmisi"])
    islenen = sum(x["n"] for x in st.session_state["isabet_gecmisi"])
    c3.metric("Bu oturum isabet (1. tahmin)", f"{top1}/{islenen}" if islenen else "—")

    if not res:
        st.info("Bu tarihe yüklü bülten yok. **Bülten** ekranından racecard PDF'ini yükleyin "
                "ya da TJK/HKJC'den otomatik çekin.")
    else:
        st.markdown("### Koşu koşu bahis planı")
        for r in res:
            atlar = [h for h in r["horses"] if not h.get("yedek")]
            if len(atlar) < 4:
                continue
            t4 = [h["num"] for h in atlar[:4]]
            onc = sorted(atlar, key=oncelik_puani, reverse=True)[:4]
            onc_str = " · ".join(f"#{h['num']} {h['name']}" for h in onc[:3])
            uyum = len({h["num"] for h in onc[:4]} & set(t4))
            st.markdown(
                f"<div class='kart'><div class='kosu-baslik'><div class='kosu-no'>{r['race_no']}</div>"
                f"<div><b>{r.get('name','KOŞU')}</b><div class='kosu-meta'>{r.get('time','')} · "
                f"{r.get('distance','')}m · {'Kum' if r.get('surface')=='AWT' else 'Çim'} · {r.get('class','')}</div></div></div>"
                f"<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:8px;text-align:center'>"
                f"<div><div class='kosu-meta'>İKİLİ</div><b>{t4[0]}-{t4[1]}</b></div>"
                f"<div><div class='kosu-meta'>SIRALI İKİLİ</div><b>{t4[0]}→{t4[1]}</b></div>"
                f"<div><div class='kosu-meta'>ÜÇLÜ</div><b>{t4[0]}-{t4[1]}-{t4[2]}</b></div>"
                f"<div><div class='kosu-meta'>SIRALI ÜÇLÜ</div><b>{t4[0]}→{t4[1]}→{t4[2]}</b></div>"
                f"<div><div class='kosu-meta'>TABELA</div><b>{'-'.join(map(str,t4))}</b></div></div>"
                f"<div class='atalt' style='margin-top:8px'>🎯 Öncelikli kriter sıralaması: {onc_str} "
                f"&nbsp;·&nbsp; genel skorla uyum: {uyum}/4"
                f"{' &nbsp;⚠️ öncelik listesi farklı at gösteriyor' if uyum <= 2 else ''}</div></div>",
                unsafe_allow_html=True)

    if st.session_state["isabet_gecmisi"]:
        st.markdown("### Öğrenme geçmişi (bu oturum)")
        st.table(pd.DataFrame(st.session_state["isabet_gecmisi"]).rename(columns={
            "tarih": "Tarih", "n": "Koşu", "top1": "1. isabet", "top3": "İlk-3 isabet"}))

# ================================================================ BÜLTEN
elif menu == "Bülten":
    st.markdown("# Bülten")
    st.caption("Racecard PDF'i yükleyin ya da programı doğrudan siteden çekin. "
               "Her kriter kaynağındaki gerçek veriden hesaplanır.")

    sek1, sek2 = st.tabs(["📄 Sha Tin PDF (önerilen)", "🌐 Siteden çek"])

    with sek1:
        if not SHA_TIN_HAZIR:
            st.error("sha_tin_motoru.py bulunamadı. GitHub'da app.py ile aynı klasöre yükleyin.")
        pdf = st.file_uploader("HKJC günlük racecard PDF'i (≈58 sayfa)", type=["pdf"])
        if st.button("Bülteni ayrıştır ve 40 kriterle puanla", type="primary",
                     disabled=not (SHA_TIN_HAZIR and pdf)):
            with st.spinner("Rating, form, draw istatistikleri, denemeler ve veteriner kayıtları okunuyor…"):
                try:
                    metin = "\n".join((s.extract_text() or "") for s in PdfReader(pdf).pages)
                    if "Quick Reference" not in metin:
                        st.error("Bu dosya HKJC racecard formatında görünmüyor ('Quick Reference' bölümü yok).")
                    else:
                        veri = pdf_ayristir(metin)
                        analiz = analiz_et(veri, st.session_state["ogrenme_agirliklari"])
                        if not analiz:
                            st.error("Koşu ayrıştırılamadı. PDF'in 'Final Version' racecard olduğundan emin olun.")
                        else:
                            hedef = veri.get("tarih") or date_str
                            st.session_state.update(quantum_results=analiz, analyzed=True, loaded_date=hedef)
                            hata = buluta_kaydet(analiz, hedef)
                            if hata:
                                st.warning(hata)
                            st.success(f"{len(analiz)} koşu, "
                                       f"{sum(len(r['horses']) for r in analiz)} at puanlandı. "
                                       f"Bülten tarihi: {hedef}")
                            st.rerun()
                except Exception as e:
                    st.error(f"PDF işlenemedi: {e}")

    with sek2:
        if not VERI_KAYNAGI_HAZIR:
            st.error("veri_kaynagi.py bulunamadı. GitHub'da app.py ile aynı klasöre yükleyin.")
        kaynak = st.radio("Kaynak", ["HKJC Sha Tin", "HKJC Happy Valley", "TJK (Türkiye)"], horizontal=True)
        sehir = None
        if kaynak.startswith("TJK"):
            sehir = st.selectbox("Hipodrom", ["İstanbul", "Bursa", "İzmir", "Ankara", "Adana",
                                              "Şanlıurfa", "Elazığ", "Diyarbakır", "Antalya", "Kocaeli"])
            st.caption("Kaynak: tjk.org → Günlük Yarış Programı")
        if st.button("Seçili tarihin programını çek", type="primary", disabled=not VERI_KAYNAGI_HAZIR):
            with st.spinner("Program indiriliyor…"):
                try:
                    if kaynak.startswith("TJK"):
                        cekilen = tjk_program_cek(date_str, sehir)
                    else:
                        cekilen = hkjc_racecard_cek(date_str, "ST" if "Sha Tin" in kaynak else "HV")
                    if not cekilen:
                        st.error("Bu tarihte seçili pistte koşu bulunamadı ya da site yapısı değişmiş. "
                                 "Sha Tin için PDF yolu daha güvenilirdir.")
                    else:
                        cekilen = form_skoru_hesapla(cekilen)
                        st.session_state.update(quantum_results=cekilen, analyzed=True, loaded_date=date_str)
                        st.success(f"{len(cekilen)} koşu çekildi ve basit form skoruyla puanlandı "
                                   "(web verisi PDF kadar zengin değildir; 40 kriter yalnızca PDF yolunda).")
                        st.rerun()
                except Exception as e:
                    st.error(f"Veri çekilemedi: {e}")

# ================================================================ ANALİZ
elif menu == "Analiz":
    st.markdown("# Analiz")
    if not res:
        st.info("Önce **Bülten** ekranından veri yükleyin.")
    else:
        for r in res:
            kosu_karti(r)
            atlar = [h for h in r["horses"] if h.get("kriterler")]
            if atlar and st.toggle(f"Koşu {r['race_no']} · 40 kriterlik tam matris", key=f"m{r['race_no']}"):
                st.dataframe(pd.DataFrame({f"#{h['num']} {h['name'][:14]}": h["kriterler"] for h in atlar}),
                             use_container_width=True, height=420)
                st.caption("A Rating/Sınıf · B Form · C İnsan · D Koşul (12 aylık draw istatistiği) · "
                           "E Hazırlık/Risk. 0–100; 50 = kaynakta veri yok (nötr).")

# ================================================================ DETAY
elif menu == "Detay":
    st.markdown("# Analiz Detayı")
    if not res:
        st.info("Önce **Bülten** ekranından veri yükleyin.")
    else:
        secim = st.selectbox("Koşu seçin", [f"Koşu {r['race_no']} — {r.get('name', '')}" for r in res])
        r = res[[f"Koşu {x['race_no']} — {x.get('name', '')}" for x in res].index(secim)]
        st.caption(f"{r.get('time', '')} · {r.get('distance', '')}m · {r.get('surface', '')} · {r.get('class', '')}")

        atlar = [h for h in r["horses"] if not h.get("yedek")]
        tablo = pd.DataFrame([{
            "Sıra": i + 1, "No": h["num"], "At": h["name"],
            "Jokey": h.get("jockey") or h.get("jockey_full") or "—",
            "Antrenör": h.get("trainer", "—"),
            "Rt": h.get("rt", h.get("hp")), "Draw": h.get("draw", h.get("start")),
            "Kilo": h.get("weight"), "Son koşular": h.get("form", h.get("last6", "")),
            "Form": h.get("bio", 0), "Rating": h.get("aero", 0),
            "İnsan": h.get("lobby", 0), "Koşul": h.get("syn", 0),
            "SKOR": h.get("score", 0),
        } for i, h in enumerate(atlar)])
        st.dataframe(tablo, use_container_width=True, hide_index=True)

        ilk3 = atlar[:3]
        if ilk3 and ilk3[0].get("kategoriler"):
            st.markdown("### İlk üçün kategori karşılaştırması")
            kolonlar = st.columns(len(ilk3))
            for kol, h in zip(kolonlar, ilk3):
                with kol:
                    st.markdown(f"**#{h['num']} {h['name']}** — {h['score']}")
                    for kat, deger in h["kategoriler"].items():
                        st.markdown(
                            f"<div class='atalt'>{KATEGORI_ADLARI.get(kat, kat)} · {deger}</div>"
                            f"<div class='bar-kap'><div class='bar-ic' style='width:{min(100, deger)}%'></div></div>",
                            unsafe_allow_html=True)
        if atlar and atlar[0].get("kriterler"):
            st.markdown("### Kriter matrisi")
            st.dataframe(pd.DataFrame({f"#{h['num']} {h['name'][:14]}": h["kriterler"] for h in atlar}),
                         use_container_width=True, height=460)

        if any(h.get("profil") for h in atlar):
            st.markdown("### Mesafe & yüzey profili (eski koşulardan)")
            st.caption("Her atın kendi geçmiş koşularından çıkarılmıştır: hangi zeminde ve "
                       "hangi mesafede kaç koşu / kaç galibiyet / kaç tabela.")
            profil_satirlari = []
            for h in atlar:
                p = h.get("profil") or {}
                cim = (p.get("yuzeyler") or {}).get("Çim", {"n": 0, "w": 0, "t3": 0})
                kum = (p.get("yuzeyler") or {}).get("Kum", {"n": 0, "w": 0, "t3": 0})
                bugun = (p.get("mesafeler") or {}).get(r.get("distance"), {"n": 0, "w": 0, "t3": 0})
                profil_satirlari.append({
                    "No": h["num"], "At": h["name"],
                    "Çim (k/g/t3)": f"{cim['n']}/{cim['w']}/{cim['t3']}",
                    "Kum (k/g/t3)": f"{kum['n']}/{kum['w']}/{kum['t3']}",
                    f"Bugünkü mesafe {r.get('distance','')}m": f"{bugun['n']}/{bugun['w']}/{bugun['t3']}",
                    "En başarılı mesafe": f"{p.get('en_iyi_mesafe')}m" if p.get("en_iyi_mesafe") else "—",
                })
            st.dataframe(pd.DataFrame(profil_satirlari), use_container_width=True, hide_index=True)

# ================================================================ TAHMİN
elif menu == "Tahmin":
    st.markdown("# Tahmin Kartları")
    if not res:
        st.info("Önce **Bülten** ekranından veri yükleyin.")
    else:
        st.caption("Banko = en yüksek toplam skor. Sürpriz = ilk üç dışında kalıp tek bir kategoride "
                   "alanın en iyisi olan at. Hiçbir kart kazanç garantisi değildir.")
        for r in res:
            atlar = [h for h in r["horses"] if not h.get("yedek")]
            if not atlar:
                continue
            banko, alternatif = atlar[0], atlar[1:3]
            surpriz = None
            for h in atlar[3:]:
                for kat, deger in (h.get("kategoriler") or {}).items():
                    if deger >= max((x.get("kategoriler", {}).get(kat, 0) for x in atlar), default=0):
                        surpriz = (h, KATEGORI_ADLARI.get(kat, kat)); break
                if surpriz:
                    break
            c1, c2 = st.columns([1.4, 1])
            with c1:
                st.markdown(
                    f"<div class='banko'><div class='kosu-meta'>KOŞU {r['race_no']} · {r.get('time', '')}</div>"
                    f"<h3 style='margin:4px 0'>★ #{banko['num']} {banko['name']} <span class='skor'>{banko.get('score', 0)}</span></h3>"
                    f"{kategori_rozetleri(banko)}</div>", unsafe_allow_html=True)
            with c2:
                for h in alternatif:
                    st.markdown(f"<div class='kart' style='padding:8px 12px;margin-bottom:8px'>"
                                f"<b>#{h['num']} {h['name']}</b> — {h.get('score', 0)}<br>{kategori_rozetleri(h)}</div>",
                                unsafe_allow_html=True)
                if surpriz:
                    h, kat = surpriz
                    st.markdown(f"<div class='kart' style='padding:8px 12px;border-style:dashed'>"
                                f"⚡ Sürpriz: <b>#{h['num']} {h['name']}</b> — {kat} kategorisinde alanın en iyisi</div>",
                                unsafe_allow_html=True)

        st.write("---")
        st.markdown("## Kupon planlayıcı")
        dahil = st.multiselect("Kupona girecek koşular",
                               [r["race_no"] for r in res], default=[r["race_no"] for r in res[:6]])
        secimler, kombinasyon = {}, 1
        kolonlar = st.columns(3)
        for i, r in enumerate([x for x in res if x["race_no"] in dahil]):
            atlar = [h for h in r["horses"] if not h.get("yedek")]
            with kolonlar[i % 3]:
                secim = st.multiselect(f"Koşu {r['race_no']}",
                                       [f"#{h['num']} {h['name']}" for h in atlar],
                                       default=[f"#{atlar[0]['num']} {atlar[0]['name']}"] if atlar else [],
                                       key=f"kupon{r['race_no']}")
                secimler[r["race_no"]] = secim
                kombinasyon *= max(len(secim), 1)
        birim = st.number_input("Misli / birim bahis tutarı", min_value=0.0, value=1.0, step=0.5)
        k1, k2 = st.columns(2)
        k1.metric("Kombinasyon", kombinasyon)
        k2.metric("Toplam maliyet", f"{kombinasyon * birim:,.2f}")

        st.write("---")
        st.markdown("## Rapor")
        if not PDF_HAZIR:
            st.warning("PDF üretimi için WeasyPrint gerekli (requirements.txt içinde mevcut; "
                       "Streamlit Cloud'da otomatik kurulur).")
        else:
            if st.button("📄 Günün tahmin raporunu (PDF) oluştur", type="primary"):
                with st.spinner("Rapor hazırlanıyor…"):
                    try:
                        pdf_bytes = HTML(string=rapor_html(res, date_str,
                                                           st.session_state["ogrenme_agirliklari"])).write_pdf()
                        st.download_button("Raporu indir", data=pdf_bytes,
                                           file_name=f"avelor_{date_str}.pdf", mime="application/pdf")
                    except Exception as e:
                        st.error(f"Rapor üretilemedi: {e}")

# ================================================================ SONUÇ & ÖĞRENME
elif menu == "Sonuç & Öğrenme":
    st.markdown("# Sonuç Girişi ve Öğrenme")
    if not (SHA_TIN_HAZIR and res and any(h.get("kategoriler") for r in res for h in r["horses"])):
        st.info("Öğrenme için bu tarihte 40 kriterli (PDF yolundan) bir analiz yüklü olmalı.")
    else:
        st.caption("Kazananları seçin; model, kazananı hangi kategorinin daha iyi bildiğine bakarak "
                   "ağırlıkları küçük adımlarla günceller. Anlamlı öğrenme onlarca yarış günü ister; "
                   "hiçbir ağırlık kombinasyonu kazanç garantisi vermez.")
        secimler = {}
        for r in res:
            atlar = [h for h in r["horses"] if not h.get("yedek")]
            ops = ["—"] + [f"#{h['num']} {h['name']}" for h in atlar]
            st.markdown(f"**Koşu {r['race_no']}** · {r.get('time','')}")
            k1, k2, k3, k4 = st.columns(4)
            sira4 = []
            for kol, etiket in zip([k1, k2, k3, k4], ["1.", "2.", "3.", "4."]):
                with kol:
                    s = st.selectbox(etiket, ops, key=f"s{r['race_no']}_{etiket}")
                    sira4.append(int(s.split()[0].replace("#", "")) if s != "—" else None)
            if sira4[0]:
                secimler[r["race_no"]] = [x for x in sira4 if x]
        if st.button("Sonuçlardan öğren ve ağırlıkları güncelle", type="primary"):
            if not secimler:
                st.warning("En az bir koşunun kazananını girin (1. zorunlu, 2-3-4 isteğe bağlı).")
            else:
                yeni_w, rapor = agirliklari_guncelle(st.session_state["ogrenme_agirliklari"], res, secimler)
                st.session_state["ogrenme_agirliklari"] = yeni_w
                st.session_state["isabet_gecmisi"].append({"tarih": date_str, "n": rapor["kosu_sayisi"],
                                                           "top1": rapor["top1_isabet"],
                                                           "top3": rapor["top3_isabet"]})
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("İşlenen koşu", rapor["kosu_sayisi"])
                c2.metric("1. tahmin isabeti", f"{rapor['top1_isabet']}/{rapor['kosu_sayisi']}")
                c3.metric("İlk-3 isabeti", f"{rapor['top3_isabet']}/{rapor['kosu_sayisi']}")
                c4.metric("Tabela isabeti", f"{rapor['tabela_isabet']}/{rapor['kosu_sayisi']*4}")
                st.table(pd.DataFrame([{"Kategori": KATEGORI_ADLARI[k],
                                        "Yeni ağırlık": f"%{v*100:.1f}",
                                        "Değişim": f"{rapor['degisim'][k]*100:+.2f}"} for k, v in yeni_w.items()]))
                if rapor.get("kriter_perf"):
                    # birikimli kriter performansı (oturum boyunca)
                    birikim = st.session_state.setdefault("kriter_perf_birikim", {})
                    for kr, p in rapor["kriter_perf"].items():
                        eski_p, adet = birikim.get(kr, (0.0, 0))
                        birikim[kr] = ((eski_p * adet + p) / (adet + 1), adet + 1)
                    siralama = sorted(birikim.items(), key=lambda x: -x[1][0])
                    st.markdown("### 🏆 Sonuçlara göre en işe yarayan kriterler")
                    st.caption("Gerçek ilk-4'ü kendi sıralamasında en üstte tutan kriterler "
                               "(0-100; birikimli). Bu tablo büyüdükçe hangi kriterlerin gerçekten "
                               "öngörücü olduğunu birlikte göreceğiz.")
                    st.table(pd.DataFrame([{"Kriter": kr, "Performans": f"{p:.1f}", "Ölçülen koşu": n}
                                           for kr, (p, n) in siralama[:12]]))
                    dusukler = ", ".join(kr for kr, (p, n) in siralama[-5:])
                    st.caption(f"En zayıf görünenler: {dusukler}")
                if API_URL:
                    try:
                        requests.post(API_URL, json={"Tarih": date_str, "Kosu_No": "AGIRLIKLAR",
                                                     "Gelen_At": kullanici or "OGRENME",
                                                     "Detay": json.dumps({"w": yeni_w,
                                                                          "kriter_perf": rapor.get("kriter_perf", {})})},
                                      timeout=10)
                        st.success("Öğrenilen ağırlıklar ve kriter performansı bulut arşivine kaydedildi.")
                    except requests.RequestException as e:
                        st.warning(f"Buluta yazılamadı (bu oturumda geçerli): {e}")
