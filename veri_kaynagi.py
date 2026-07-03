# -*- coding: utf-8 -*-
"""
veri_kaynagi.py — AVELOR için gerçek veri katmanı
==================================================
İki kaynaktan günlük yarış programını çeker ve uygulamanın beklediği
{"race_no", "time", "horses": [...]} yapısına dönüştürür:

  1. TJK  — https://www.tjk.org  (günlük yarış programı, şehir bazlı HTML)
  2. HKJC — https://racing.hkjc.com (Sha Tin / Happy Valley racecard)

NOT / DÜRÜSTLÜK: Bu modüldeki puanlama SAHTE "kuantum" motorunun yerine
geçmek üzere yazılmış, tamamen şeffaf bir FORM SKORU'dur. Yalnızca
racecard'da gerçekten bulunan alanları kullanır (rating/handikap puanı,
kilo, start pozisyonu, son koşu dereceleri). Bir olasılık modeli DEĞİLDİR;
geçmiş sonuçlarla eğitilmiş gerçek bir model (ör. LightGBM) kurulana
kadar makul bir başlangıç sıralaması verir. Hiçbir skor kazanç garantisi
taşımaz.

Bağımlılıklar: requests, beautifulsoup4, lxml, pandas
    pip install requests beautifulsoup4 lxml pandas

UYARI: Her iki site de HTML yapısını değiştirebilir; parser'lar savunmacı
yazıldı ama ilk kullanımda çıktıyı gözle doğrulayın. Sitelerin kullanım
koşullarına ve istek sıklığı nezaketine (günde birkaç istek) uyun.
"""

from __future__ import annotations

import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
TIMEOUT = 20

# TJK şehir kimlikleri (tjk.org'daki SehirId parametresi)
TJK_SEHIRLER = {
    "İstanbul": 3, "Bursa": 4, "İzmir": 1, "Ankara": 2, "Adana": 5,
    "Şanlıurfa": 6, "Elazığ": 7, "Diyarbakır": 8, "Antalya": 9, "Kocaeli": 12,
}


# ---------------------------------------------------------------------------
# 1) TJK — GÜNLÜK YARIŞ PROGRAMI
# ---------------------------------------------------------------------------
def tjk_program_cek(tarih: str, sehir: str = "İstanbul") -> list[dict]:
    """
    tarih: 'YYYY-MM-DD'  ->  TJK 'GG/AA/YYYY' bekler.
    Dönüş: [{"race_no", "time", "distance", "track", "horses": [...]}]
    """
    yil, ay, gun = tarih.split("-")
    tjk_tarih = f"{gun}/{ay}/{yil}"
    sehir_id = TJK_SEHIRLER.get(sehir, 3)
    url = (
        "https://www.tjk.org/TR/Yarissever/Info/Sehir/GunlukYarisProgrami"
        f"?SehirId={sehir_id}&QueryParameter_Tarih={tjk_tarih}&SehirAdi={sehir}"
    )
    resp = requests.get(url, headers=UA, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    races: list[dict] = []
    # TJK'da her koşu bir başlık (saat + mesafe + pist) ve bir at tablosu olarak gelir.
    # Savunmacı yaklaşım: sayfadaki tüm tabloları gez, at tablosu desenine uyanları al.
    kosu_basliklari = soup.find_all(string=re.compile(r"\d+\s*\.\s*Koşu", re.I))

    tables = pd.read_html(resp.text)  # lxml gerektirir
    race_no = 0
    for tbl in tables:
        cols = [str(c).strip().lower() for c in tbl.columns]
        # At tablosu göstergeleri: "at ismi/at adı" ve "jokey" sütunları
        if not any("at" in c for c in cols) or not any("jokey" in c or "jockey" in c for c in cols):
            continue
        race_no += 1
        horses = []
        for _, row in tbl.iterrows():
            r = {str(k).strip().lower(): row[k] for k in tbl.columns}
            num = _ilk_sayi(r.get("no") or r.get("at no") or r.get("#"))
            isim = _temiz(r.get("at ismi") or r.get("at adı") or r.get("at"))
            if num is None or not isim:
                continue
            horses.append({
                "num": num,
                "name": isim,
                "jockey": _temiz(r.get("jokey")),
                "trainer": _temiz(r.get("antrenör") or r.get("antrenor")),
                "weight": _ilk_float(r.get("kilo")),
                "hp": _ilk_float(r.get("hp") or r.get("handikap puanı")),   # handikap puanı
                "last6": _temiz(r.get("son 6 koşu") or r.get("son 6")),      # ör. "1 3 2 0 4 1"
                "start": _ilk_sayi(r.get("st") or r.get("start")),
            })
        if horses:
            # Koşu saati başlıktan; bulunamazsa boş bırak (uygulama '13:30' varsayar)
            saat = ""
            if race_no - 1 < len(kosu_basliklari):
                m = re.search(r"(\d{1,2}[:.]\d{2})", str(kosu_basliklari[race_no - 1].parent))
                if m:
                    saat = m.group(1).replace(".", ":")
            races.append({"race_no": race_no, "time": saat or f"{12 + race_no}:00", "horses": horses})
    return races


# ---------------------------------------------------------------------------
# 2) HKJC — SHA TIN / HAPPY VALLEY RACECARD
# ---------------------------------------------------------------------------
def hkjc_racecard_cek(tarih: str, pist: str = "ST", max_kosu: int = 14) -> list[dict]:
    """
    tarih: 'YYYY-MM-DD'; pist: 'ST' (Sha Tin) veya 'HV' (Happy Valley).
    Koşu koşu sayfaları gezilir; koşu bulunamayınca durur.
    """
    hk_tarih = tarih.replace("-", "/")
    races: list[dict] = []
    for no in range(1, max_kosu + 1):
        url = (
            "https://racing.hkjc.com/racing/information/English/Racing/RaceCard.aspx"
            f"?RaceDate={hk_tarih}&Racecourse={pist}&RaceNo={no}"
        )
        try:
            resp = requests.get(url, headers=UA, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            break
        if "no information" in resp.text.lower():
            break

        try:
            tables = pd.read_html(resp.text)
        except ValueError:
            break

        horses = []
        for tbl in tables:
            cols = [str(c).strip().lower() for c in tbl.columns]
            if "horse" not in " ".join(cols) or "jockey" not in " ".join(cols):
                continue
            for _, row in tbl.iterrows():
                r = {str(k).strip().lower(): row[k] for k in tbl.columns}
                num = _ilk_sayi(r.get("horse no.") or r.get("no."))
                isim = _temiz(r.get("horse"))
                if num is None or not isim:
                    continue
                horses.append({
                    "num": num,
                    "name": re.sub(r"\(.*?\)", "", isim).strip(),  # marka kodunu at
                    "jockey": _temiz(r.get("jockey")),
                    "trainer": _temiz(r.get("trainer")),
                    "weight": _ilk_float(r.get("wt.") or r.get("actual wt.")),
                    "hp": _ilk_float(r.get("rtg.") or r.get("rating")),
                    "last6": _temiz(r.get("last 6 runs")),
                    "start": _ilk_sayi(r.get("draw")),
                })
            break  # ilk uygun tablo yeterli
        if not horses:
            break

        m = re.search(r"(\d{1,2}:\d{2})", resp.text)
        races.append({"race_no": no, "time": m.group(1) if m else f"{12 + no}:00", "horses": horses})
        time.sleep(1.0)  # siteye nezaket: koşular arası 1 sn bekle
    return races


# ---------------------------------------------------------------------------
# 3) ŞEFFAF FORM SKORU — sahte "kuantum" motorunun yerine geçer
# ---------------------------------------------------------------------------
def form_skoru_hesapla(races: list[dict]) -> list[dict]:
    """
    Her at için 0-100 arası, TAMAMEN AÇIKLANABİLİR bir form skoru üretir:
      %45 Rating / Handikap puanı (koşu içinde normalize)
      %35 Son 6 koşu form ortalaması (1.lik=10p ... 6+/koşmadı=0p)
      %10 Kilo avantajı (koşunun en hafifi = tam puan)
      %10 Start pozisyonu (iç kulvar hafif avantaj)
    Bu bir olasılık modeli değildir; sadece racecard verisinin özetidir.
    """
    for race in races:
        hs = race["horses"]
        hps = [h["hp"] for h in hs if h.get("hp") is not None]
        wts = [h["weight"] for h in hs if h.get("weight") is not None]
        hp_min, hp_max = (min(hps), max(hps)) if hps else (0, 1)
        wt_min, wt_max = (min(wts), max(wts)) if wts else (0, 1)
        n = max(len(hs), 2)

        for h in hs:
            # Rating (koşu içinde min-max normalizasyon)
            if h.get("hp") is not None and hp_max > hp_min:
                s_hp = (h["hp"] - hp_min) / (hp_max - hp_min) * 100
            else:
                s_hp = 50.0
            # Son 6 form: rakamları oku, 1->10p, 2->8p, 3->6p, 4->4p, 5->2p, diğer->0
            puan_map = {1: 10, 2: 8, 3: 6, 4: 4, 5: 2}
            sonuclar = [int(x) for x in re.findall(r"\d", str(h.get("last6") or ""))]
            s_form = (sum(puan_map.get(x, 0) for x in sonuclar) / (len(sonuclar) * 10) * 100) if sonuclar else 50.0
            # Kilo: hafif olan avantajlı
            if h.get("weight") is not None and wt_max > wt_min:
                s_kilo = (wt_max - h["weight"]) / (wt_max - wt_min) * 100
            else:
                s_kilo = 50.0
            # Start: 1. kulvar en iyi
            s_start = ((n - (h.get("start") or n / 2)) / (n - 1) * 100) if n > 1 else 50.0

            h["score"] = round(0.45 * s_hp + 0.35 * s_form + 0.10 * s_kilo + 0.10 * s_start, 1)
            # Uygulamanın mevcut arayüzüyle uyum için alanlar — ama artık gerçek anlamları var:
            h["bio"] = round(s_form, 1)    # arayüzde "Form" olarak yeniden etiketleyin
            h["aero"] = round(s_hp, 1)     # arayüzde "Rating" olarak yeniden etiketleyin
            h["lobby"] = round(s_kilo, 1)  # arayüzde "Kilo Avantajı" olarak yeniden etiketleyin
            h["syn"] = round(s_start, 1)   # arayüzde "Start Pozisyonu" olarak yeniden etiketleyin
            h["val"] = False               # value bet ancak gerçek oran verisiyle hesaplanabilir
            h["agf"] = 0.0
            h["galop"] = "-"

        hs.sort(key=lambda x: x["score"], reverse=True)
        madalya = ["🥇 1. Sıra", "🥈 2. Sıra", "🥉 3. Sıra", "🏅 4. Sıra"]
        for i, h in enumerate(hs):
            h["medal"] = madalya[i] if i < 4 else f"#{i + 1}. Sıra"
    return races


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _temiz(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _ilk_sayi(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None


def _ilk_float(v):
    m = re.search(r"\d+(?:[.,]\d+)?", str(v or ""))
    return float(m.group().replace(",", ".")) if m else None


if __name__ == "__main__":
    # Hızlı el testi:  python veri_kaynagi.py
    import json, datetime
    bugun = datetime.date.today().isoformat()
    print("TJK İstanbul deneniyor...")
    try:
        r = form_skoru_hesapla(tjk_program_cek(bugun, "İstanbul"))
        print(json.dumps(r[:1], ensure_ascii=False, indent=2)[:2000])
    except Exception as e:
        print("TJK hata:", e)
    print("\nHKJC Sha Tin deneniyor...")
    try:
        r = form_skoru_hesapla(hkjc_racecard_cek(bugun, "ST"))
        print(json.dumps(r[:1], ensure_ascii=False, indent=2)[:2000])
    except Exception as e:
        print("HKJC hata:", e)
