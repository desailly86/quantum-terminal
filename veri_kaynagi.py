# -*- coding: utf-8 -*-
"""
veri_kaynagi.py v2 — Evrensel veri katmanı
===========================================
1) tjk_gunun_hipodromlari(tarih)  → o gün tjk.org'da OYNANABILEN TÜM
   hipodromları (yurtiçi + yabancı: Fransa, İngiltere, G.Afrika...) keşfeder.
2) tjk_program_cek(tarih, sehir_id, sehir_adi) → seçilen hipodromun programı.
3) evrensel_kriterle(races) → kaynak ne kadar veri veriyorsa o kadar kriter
   üretir (TJK yurtiçi ~12-15, yabancı ~6-10); çıktı sha_tin_motoru ile aynı
   yapıdadır (kriterler/kategoriler/score) → öğrenme sistemi ortak çalışır.
4) hkjc_sonuc_cek(tarih, pist) → yarış sonrası ilk-4'leri otomatik çeker.
5) hava_durumu(pist, tarih) → Open-Meteo (ücretsiz, anahtarsız).

DÜRÜSTLÜK: (a) tjk.org yabancı koşular için sığ veri yayınlar; o koşularda
kriter sayısı düşer ve bu arayüzde açıkça görünür. (b) Bu modül geliştirme
ortamında dış ağ kapalı olduğundan canlı test edilemedi; site yapısı
değişirse hata mesajını geri bildirin. (c) Sitelere nazik olun: çekimler
arasına bekleme kondu, gereksiz tekrar çekim yapmayın.
"""
from __future__ import annotations
import re
import time
import requests
import io
import pandas as pd
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
TIMEOUT = 20
NOTR = 50.0

TJK_PROGRAM_URL = "https://www.tjk.org/TR/Yarissever/Info/Page/GunlukYarisProgrami"
TJK_SEHIR_URL = "https://www.tjk.org/TR/Yarissever/Info/Sehir/GunlukYarisProgrami"


# ---------------------------------------------------------------------------
# 1) GÜNÜN TÜM HİPODROMLARI (yurtiçi + yabancı) — "tek takvim"in temeli
# ---------------------------------------------------------------------------
def tjk_gunun_hipodromlari(tarih: str) -> list[dict]:
    """tarih: 'YYYY-MM-DD' → [{'ad', 'sehir_id', 'yabanci': bool}]"""
    y, a, g = tarih.split("-")
    resp = requests.get(TJK_PROGRAM_URL, params={"QueryParameter_Tarih": f"{g}/{a}/{y}"},
                        headers=UA, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    hipodromlar, gorulen = [], set()
    for a_etiketi in soup.find_all("a", href=True):
        m = re.search(r"SehirId=(\d+)", a_etiketi["href"])
        if not m:
            continue
        sid = int(m.group(1))
        ad = a_etiketi.get_text(strip=True)
        if not ad:
            ma = re.search(r"SehirAdi=([^&]+)", a_etiketi["href"] + "&")
            ad = ma.group(1) if ma else f"Hipodrom {sid}"
        if sid in gorulen:
            continue
        gorulen.add(sid)
        # Yurtiçi hipodromlar küçük kimliklerdedir; büyük kimlikler yabancı programlardır
        hipodromlar.append({"ad": ad, "sehir_id": sid, "yabanci": sid > 12})
    return hipodromlar


# ---------------------------------------------------------------------------
# 2) PROGRAM ÇEKİMİ (her hipodrom — yurtiçi/yabancı aynı sayfa yapısı)
# ---------------------------------------------------------------------------
def tjk_program_cek(tarih: str, sehir_id: int = 3, sehir_adi: str = "") -> list[dict]:
    """Önce TJK'nın resmi CSV bültenini dener (en sağlam yol — sayfanın kendi
    'CSV Program' linki), olmazsa HTML tablolarına düşer."""
    y, a, g = tarih.split("-")
    resp = requests.get(TJK_SEHIR_URL, params={"SehirId": sehir_id,
                                               "QueryParameter_Tarih": f"{g}/{a}/{y}",
                                               "SehirAdi": sehir_adi},
                        headers=UA, timeout=TIMEOUT)
    resp.raise_for_status()
    metin = resp.text

    # --- YOL 1: sayfadaki resmi CSV linki ---
    mcsv = re.search(r'href="(https://[^"]+/CSV/GunlukYarisProgrami/[^"]+\.csv)"', metin)
    if mcsv:
        try:
            races = _tjk_csv_ayristir(mcsv.group(1), sehir_adi)
            if races:
                return races
        except Exception:
            pass  # CSV başarısızsa HTML yoluna düş

    # --- YOL 2: HTML tabloları ---
    return _tjk_html_ayristir(metin, sehir_adi)


def _tjk_csv_ayristir(csv_url: str, sehir_adi: str) -> list[dict]:
    resp = requests.get(csv_url, headers=UA, timeout=TIMEOUT)
    resp.raise_for_status()
    ham = resp.content
    df = None
    for enc in ("utf-8-sig", "cp1254", "iso-8859-9", "utf-8"):
        for ayrac in (";", ","):
            try:
                aday = pd.read_csv(io.BytesIO(ham), encoding=enc, sep=ayrac)
                if aday.shape[1] >= 5:
                    df = aday
                    break
            except Exception:
                continue
        if df is not None:
            break
    if df is None:
        return []
    df.columns = [str(c).strip().upper() for c in df.columns]

    def kolon(*adaylar):
        for c in df.columns:
            duz = c.replace("İ", "I").replace("Ş", "S").replace("Ö", "O").replace("Ü", "U").replace("Ğ", "G").replace("Ç", "C")
            for aday in adaylar:
                if aday in duz:
                    return c
        return None

    k_kosu, k_no = kolon("KOSU"), kolon("AT NO", "ATNO", "NO")
    k_ad = kolon("AT ISMI", "AT ADI", "ISIM")
    k_jokey, k_kilo = kolon("JOKEY"), kolon("KILO", "SIKLET")
    k_hp, k_son6 = kolon("HANDIKAP", "HP", "PUAN"), kolon("SON 6", "SON6", "SON ALTI")
    k_st, k_antrenor = kolon("START", "ST"), kolon("ANTRENOR")
    k_kosu_sayisi = kolon("KOSU SAYISI", "KOSTUGU")
    if not (k_kosu and k_ad):
        return []

    races = []
    for kosu_no, grup in df.groupby(k_kosu, sort=True):
        try:
            rn = int(re.search(r"\d+", str(kosu_no)).group())
        except (AttributeError, ValueError):
            continue
        horses = []
        for _, row in grup.iterrows():
            isim = _temiz(row.get(k_ad))
            if not isim:
                continue
            horses.append({
                "num": _sayi(row.get(k_no)) or len(horses) + 1, "name": isim, "yedek": False,
                "jockey": _temiz(row.get(k_jokey)) if k_jokey else "",
                "trainer": _temiz(row.get(k_antrenor)) if k_antrenor else "",
                "weight": _ondalik(row.get(k_kilo)) if k_kilo else None,
                "hp": _ondalik(row.get(k_hp)) if k_hp else None,
                "rt": _ondalik(row.get(k_hp)) if k_hp else None,
                "form": re.sub(r"[^0-9]", "", _temiz(row.get(k_son6))) if k_son6 else "",
                "last6": _temiz(row.get(k_son6)) if k_son6 else "",
                "start": _sayi(row.get(k_st)) if k_st else None,
                "draw": _sayi(row.get(k_st)) if k_st else None,
                "agf": None,
                "gecmis_kosu": _sayi(row.get(k_kosu_sayisi)) if k_kosu_sayisi else None,
            })
        if horses:
            races.append({"race_no": rn, "time": "", "distance": 0, "surface": "",
                          "class": "", "name": f"{sehir_adi} {rn}. Koşu".strip(),
                          "horses": horses, "kaynak": "TJK CSV"})
    races.sort(key=lambda r: r["race_no"])
    return races


def _tjk_html_ayristir(metin: str, sehir_adi: str) -> list[dict]:
    races, race_no = [], 0
    try:
        tablolar = pd.read_html(io.StringIO(metin))
    except ValueError:
        return []
    saatler = re.findall(r"(\d{1,2}[:.]\d{2})", " ".join(
        re.findall(r"\d+\s*\.\s*Koşu[^<]{0,60}", metin)))
    mesafeler = re.findall(r"(\d{3,4})\s*m", metin)
    for tbl in tablolar:
        cols = [str(c).strip().lower() for c in tbl.columns]
        if not any("at" in c for c in cols) or not any("jokey" in c or "jockey" in c for c in cols):
            continue
        race_no += 1
        horses = []
        for _, row in tbl.iterrows():
            r = {str(kk).strip().lower(): row[kk] for kk in tbl.columns}
            num = _sayi(r.get("no") or r.get("at no") or r.get("#"))
            isim = _temiz(r.get("at ismi") or r.get("at adı") or r.get("at"))
            if num is None or not isim:
                continue
            horses.append({
                "num": num, "name": isim, "yedek": False,
                "jockey": _temiz(r.get("jokey")), "trainer": _temiz(r.get("antrenör") or r.get("antrenor")),
                "weight": _ondalik(r.get("kilo")), "hp": _ondalik(r.get("hp") or r.get("handikap puanı")),
                "rt": _ondalik(r.get("hp") or r.get("handikap puanı")),
                "form": re.sub(r"[^0-9]", "", _temiz(r.get("son 6 koşu") or r.get("son 6"))),
                "last6": _temiz(r.get("son 6 koşu") or r.get("son 6")),
                "start": _sayi(r.get("st") or r.get("start")), "draw": _sayi(r.get("st") or r.get("start")),
                "agf": _ondalik(r.get("agf") or r.get("agf1") or r.get("agf %")),
                "gecmis_kosu": _sayi(r.get("koşu") or r.get("kosu")),
            })
        if horses:
            races.append({"race_no": race_no,
                          "time": (saatler[race_no - 1].replace(".", ":")
                                   if race_no - 1 < len(saatler) else ""),
                          "distance": int(mesafeler[race_no - 1]) if race_no - 1 < len(mesafeler) else 0,
                          "surface": "", "class": "",
                          "name": f"{sehir_adi} {race_no}. Koşu".strip(),
                          "horses": horses})
    return races


# ---------------------------------------------------------------------------
# 3) EVRENSEL KRİTERLEME — kaynak ne veriyorsa onu puanlar (şeffaf)
# ---------------------------------------------------------------------------
def _n(deger, dizi):
    d = [x for x in dizi if x is not None]
    if deger is None or len(d) < 2 or max(d) == min(d):
        return NOTR
    return (deger - min(d)) / (max(d) - min(d)) * 100.0


def _form_p(c):
    return {"1": 100, "2": 80, "3": 65, "4": 50, "5": 35, "6": 25, "7": 15,
            "8": 10, "9": 5, "0": 0}.get(c, 0)


def evrensel_kriterle(races: list[dict]) -> list[dict]:
    """Programı eldeki alanlarla kriterler; alan yoksa kriter üretilmez
    (nötr doldurma yok → kriter sayısı kaynağın zenginliğini dürüstçe yansıtır)."""
    for race in races:
        atlar = [h for h in race["horses"] if not h.get("yedek")]
        hps = [h.get("hp") for h in atlar]
        kilolar = [h.get("weight") for h in atlar]
        agfler = [h.get("agf") for h in atlar]
        n = len(atlar)
        for h in atlar:
            k = {}
            if any(x is not None for x in hps):
                k["A1 Handikap Puanı"] = _n(h.get("hp"), hps)
            if any(x is not None for x in kilolar):
                k["A3 Kilo Avantajı"] = 100 - _n(h.get("weight"), kilolar)
            f = h.get("form") or ""
            if f:
                k["B1 Son Koşu"] = _form_p(f[-1])
                k["B2 Son 3 Koşu Ort."] = sum(_form_p(c) for c in f[-3:]) / max(len(f[-3:]), 1)
                agirlikli = [(_form_p(c), i + 1) for i, c in enumerate(f)]
                k["B3 Son 6 Ağırlıklı"] = sum(p * g for p, g in agirlikli) / sum(g for _, g in agirlikli)
                if len(f) >= 4:
                    ilk = sum(_form_p(c) for c in f[:len(f)//2]) / (len(f)//2)
                    son = sum(_form_p(c) for c in f[len(f)//2:]) / (len(f) - len(f)//2)
                    k["B4 Form Trendi"] = max(0, min(100, 50 + (son - ilk) / 2))
            if h.get("gecmis_kosu"):
                k["B8 Deneyim"] = min(100, h["gecmis_kosu"] * 6)
            if h.get("draw"):
                k["D4 İç Kulvar"] = 100 - ((h["draw"] - 1) / max(n - 1, 1) * 100)
                if n >= 12:
                    k["D5 Geniş Alan Dış Kulvar"] = max(0, 100 - max(0, h["draw"] - 8) * 12)
            if h.get("agf") is not None and sum(1 for x in agfler if x is not None) >= 2:
                k["G1 AGF (Halk Tercihi)"] = _n(h["agf"], agfler)
            if h.get("jockey"):
                k["C6 Jokey Atanmış"] = 100
            kat = {}
            for harf, ad in [("A", "rating"), ("B", "form"), ("C", "insan"),
                             ("D", "kosul"), ("G", "piyasa")]:
                degerler = [v for a, v in k.items() if a.startswith(harf)]
                if degerler:
                    kat[ad] = round(sum(degerler) / len(degerler), 1)
            h["kriterler"] = {a: round(v, 1) for a, v in k.items()}
            h["kategoriler"] = kat
            h["score"] = round(sum(kat.values()) / len(kat), 1) if kat else NOTR
            h["bio"] = kat.get("form", 0); h["aero"] = kat.get("rating", 0)
            h["lobby"] = kat.get("insan", 0); h["syn"] = kat.get("kosul", 0)
            h["val"] = False; h["galop"] = "-"
        atlar.sort(key=lambda x: x["score"], reverse=True)
        madalya = ["🥇 1. Sıra", "🥈 2. Sıra", "🥉 3. Sıra", "🏅 4. Sıra"]
        for i, h in enumerate(atlar):
            h["medal"] = madalya[i] if i < 4 else f"#{i+1}. Sıra"
        race["horses"] = atlar
        race["kriter_sayisi"] = len(atlar[0]["kriterler"]) if atlar else 0
    return races


# ---------------------------------------------------------------------------
# 4) HKJC SONUÇ ÇEKİCİ — öğrenmeyi tek tuşla besler
# ---------------------------------------------------------------------------
def hkjc_sonuc_cek(tarih: str, pist: str = "ST", max_kosu: int = 12) -> dict:
    """{race_no: [1., 2., 3., 4. at numarası]} — LocalResults sayfasından."""
    hk = tarih.replace("-", "/")
    sonuclar = {}
    for no in range(1, max_kosu + 1):
        url = ("https://racing.hkjc.com/racing/information/English/Racing/LocalResults.aspx"
               f"?RaceDate={hk}&Racecourse={pist}&RaceNo={no}")
        try:
            resp = requests.get(url, headers=UA, timeout=TIMEOUT)
            resp.raise_for_status()
            tablolar = pd.read_html(io.StringIO(resp.text))
        except (requests.RequestException, ValueError):
            break
        ilk4 = []
        for tbl in tablolar:
            cols = " ".join(str(c).strip().lower() for c in tbl.columns)
            if "pla" in cols and "horse no" in cols:
                for _, row in tbl.iterrows():
                    r = {str(kk).strip().lower(): row[kk] for kk in tbl.columns}
                    plc = _sayi(r.get("pla.") or r.get("plc.") or r.get("pla"))
                    hno = _sayi(r.get("horse no.") or r.get("horse no"))
                    if plc and hno and plc <= 4:
                        ilk4.append((plc, hno))
                break
        if ilk4:
            sonuclar[no] = [hno for _, hno in sorted(set(ilk4))]
        time.sleep(0.8)
    return sonuclar


# ---------------------------------------------------------------------------
# 4b) TJK AGF ÇEKİCİ — halk tercihi yüzdeleri (value hesabının ham maddesi)
# ---------------------------------------------------------------------------
def tjk_agf_cek(tarih: str, sehir_id: int, bahis_no: int = 1) -> dict:
    """{(kosu_no, at_no): agf_yuzde} — /AGFv2/{sehir}/{ggaayyyy}/TR/{bahis}/1"""
    y, a, g = tarih.split("-")
    url = f"https://www.tjk.org/AGFv2/{sehir_id}/{g}{a}{y}/TR/{bahis_no}/1"
    try:
        resp = requests.get(url, headers=UA, timeout=TIMEOUT)
        resp.raise_for_status()
        tablolar = pd.read_html(io.StringIO(resp.text))
    except (requests.RequestException, ValueError):
        return {}
    agf = {}
    kosu_no = 0
    for tbl in tablolar:
        cols = [str(c).strip().upper() for c in tbl.columns]
        if not any("AGF" in c for c in cols):
            continue
        kosu_no += 1
        for _, row in tbl.iterrows():
            r = {str(kk).strip().upper(): row[kk] for kk in tbl.columns}
            no = _sayi(r.get("AT NO") or r.get("NO"))
            deger = _ondalik(next((v for kk, v in r.items() if "AGF" in kk), None))
            if no and deger is not None:
                agf[(kosu_no, no)] = deger
    return agf


# ---------------------------------------------------------------------------
# 5) HAVA DURUMU — Open-Meteo (ücretsiz, anahtarsız)
# ---------------------------------------------------------------------------
PIST_KONUM = {"ST": (22.4008, 114.2031), "HV": (22.2712, 114.1817),
              "İstanbul": (41.0658, 28.7742), "Ankara": (39.9427, 32.8112),
              "İzmir": (38.4300, 27.1600), "Bursa": (40.2280, 29.0100),
              "Adana": (37.0300, 35.3500)}

def hava_durumu(pist_veya_sehir: str, tarih: str) -> dict:
    """{'sicaklik', 'yagis_mm', 'zemin_tahmini'} — Open-Meteo günlük veri."""
    konum = PIST_KONUM.get(pist_veya_sehir)
    if not konum:
        return {}
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast",
                            params={"latitude": konum[0], "longitude": konum[1],
                                    "daily": "temperature_2m_max,precipitation_sum",
                                    "start_date": tarih, "end_date": tarih,
                                    "timezone": "auto"}, timeout=10)
        d = resp.json().get("daily", {})
        yagis = (d.get("precipitation_sum") or [0])[0] or 0
        return {"sicaklik": (d.get("temperature_2m_max") or [None])[0],
                "yagis_mm": yagis,
                "zemin_tahmini": "Ağır/Yumuşak" if yagis >= 10 else ("Nemli" if yagis >= 2 else "İyi/Kuru")}
    except (requests.RequestException, ValueError, KeyError):
        return {}


# ---------------------------------------------------------------------------
def _temiz(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()

def _sayi(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None

def _ondalik(v):
    m = re.search(r"\d+(?:[.,]\d+)?", str(v or ""))
    return float(m.group().replace(",", ".")) if m else None


# Eski API ile geriye uyumluluk:
def form_skoru_hesapla(races):
    return evrensel_kriterle(races)

def hkjc_racecard_cek(tarih, pist="ST", max_kosu=14):
    """HKJC racecard sayfası JS ile yüklendiğinden requests ile çekilemiyor;
    Sha Tin için PDF yolunu kullanın. Sonuçlar için hkjc_sonuc_cek çalışır."""
    return []
