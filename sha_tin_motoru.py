# -*- coding: utf-8 -*-
"""
sha_tin_motoru.py — HKJC Sha Tin Racecard PDF Analiz Motoru
============================================================
58 sayfalık resmi HKJC racecard PDF'ini ayrıştırır ve HER KRİTERİ
PDF'TE GERÇEKTEN VAR OLAN VERİDEN hesaplayan 40 kriterli bir analiz
matrisi üretir. Uydurma veri yoktur; bir alan PDF'te yoksa kriter
"nötr (50)" kabul edilir ve bu şeffafça işaretlenir.

5 kategori / 40 kriter:
  A. RATING & SINIF (5)  — resmi rating, sınıf bandı konumu, kilo...
  B. FORM (8)            — son koşular, kariyer yüzdeleri, trend...
  C. İNSAN FAKTÖRÜ (6)   — jokey/antrenör sezon kazanma yüzdeleri...
  D. KOŞUL UYUMU (6)     — PDF'in kendi 12 aylık draw istatistikleri...
  E. HAZIRLIK & RİSK (5) — deneme koşuları, veteriner kayıtları, ekipman

ÖĞRENME: agirliklari_guncelle() gerçek sonuçlar girildikçe kategori
ağırlıklarını küçük adımlarla günceller (sınırlı, normalize edilmiş).
DÜRÜSTLÜK NOTU: Bu bir olasılık modeli değildir ve hiçbir skor kazanç
garantisi vermez; öğrenme ancak onlarca yarış günü sonuç girildikçe
anlamlı hale gelir.
"""
from __future__ import annotations
import re
import copy

NOTR = 50.0  # veri yoksa kullanılan nötr puan

VARSAYILAN_AGIRLIKLAR = {
    "rating": 0.22, "form": 0.26, "insan": 0.14, "kosul": 0.12, "risk": 0.08, "hiz": 0.18,
}
KATEGORI_ADLARI = {
    "rating": "Rating & Sınıf", "form": "Form", "insan": "İnsan Faktörü",
    "kosul": "Koşul Uyumu", "risk": "Hazırlık & Risk", "hiz": "Hız & Zaman (AVELOR)",
}

# KRİTER AĞIRLIKLARI — 04.07.2026 Sha Tin gününün (7 koşu) ölçülmüş kriter
# performansından türetildi: agirlik = 1 + (performans - 55) x 0.08, [0.4-2.2].
# İyi bilen kriterler (Tutarlılık, Kariyer İlk-3, form ailesi) 1.6-2.2x etkili;
# zayıflar (resmi rating, draw istatistikleri, deneme galibi) 0.5x'e düşürüldü.
# Her sonuç girişinde kriter_agirliklari_turet() ile gerçek performansa göre
# kendini günceller — tek güne aşırı uyum riskine karşı harmanlanarak (%70 eski).
KRITER_AGIRLIKLARI = {
    "A1 Resmi Rating": 0.58, "A2 Sınıf Bandı Konumu": 0.58, "A3 Kilo Avantajı": 1.24,
    "A4 Rating/Kilo Dengesi": 1.38, "A5 Ortalama Üstü Rating": 1.03,
    "B1 Son Koşu": 1.4, "B2 Son 3 Koşu Ort.": 1.82, "B3 Son 6 Ağırlıklı": 1.94,
    "B4 Form Trendi": 0.77, "B5 Kariyer Kazanma %": 1.7, "B6 Kariyer İlk-3 %": 2.2,
    "B7 Tutarlılık": 2.2, "B8 Deneyim": 1.47, "B9 Mesafe Rekoru": 1.62,
    "B10 Pist+Mesafe Rekoru": 1.74, "B11 Sınıf Rekoru": 1.09, "B12 Sezon Formu": 1.89,
    "B13 Dinlenme Uyumu": 0.94, "B14 Yüzey Uyumu (Kum)": 1.94, "B14 Yüzey Uyumu (Çim)": 1.76,
    "C1 Jokey Kazanma %": 0.83, "C2 Antrenör Kazanma %": 0.75, "C3 Jokey×Antrenör": 1.01,
    "C4 Elit Jokey": 1.1, "C5 Elit Antrenör": 1.07, "C6 Jokey Atanmış": 1.38,
    "C7 Jokey-Antrenör Ortak Geçmişi": 1.22, "C8 At-Jokey Ortak Sicili": 0.95,
    "D1 Draw Kazanma % (12ay)": 0.5, "D2 Draw Tabela % (12ay)": 0.75,
    "D3 Draw İlk-4 % (12ay)": 0.78, "D4 İç Kulvar": 1.26,
    "D5 Geniş Alan Dış Draw Baskısı": 1.48, "D6 Kilo×Mesafe": 1.46,
    "D7 İyi Zemin (G) Uyumu": 1.74,
    "E1 Deneme Derecesi": 1.11, "E2 Deneme Galibi": 0.46, "E3 Veteriner Kaydı": 1.46,
    "E4 Ekipman Değişikliği": 0.57, "E5 Az Koşu Belirsizliği": 1.26, "E6 Sağlık Geçmişi": 1.38,
    "F1 En İyi Hız Figürü": 1.5, "F2 Ortalama Hız Figürü": 1.3,
    "F3 Kapanış Gücü (Son 400m)": 1.3, "F4 Tempo Senaryosu": 1.1,
}


def kriter_agirliklari_turet(kriter_perf: dict, mevcut: dict | None = None,
                             harman: float = 0.30) -> dict:
    """Ölçülen kriter performansından yeni ağırlıklar üretir (%70 eski, %30 yeni)."""
    eski = {**KRITER_AGIRLIKLARI, **(mevcut or {})}
    yeni = dict(eski)
    for kr, p in (kriter_perf or {}).items():
        hedef = max(0.4, min(2.2, 1 + (p - 55) * 0.08))
        yeni[kr] = round((1 - harman) * eski.get(kr, 1.0) + harman * hedef, 3)
    return yeni

# ---------------------------------------------------------------------------
# 1) PDF AYRIŞTIRMA
# ---------------------------------------------------------------------------
def pdf_ayristir(pdf_kaynagi) -> dict:
    """pdf_kaynagi: dosya yolu, dosya objesi veya doğrudan metin (str)."""
    if isinstance(pdf_kaynagi, str) and "\n" in pdf_kaynagi:
        tam_metin, sayfalar = pdf_kaynagi, [pdf_kaynagi]
    else:
        from pypdf import PdfReader
        reader = PdfReader(pdf_kaynagi)
        sayfalar = [(p.extract_text() or "") for p in reader.pages]
        tam_metin = "\n".join(sayfalar)

    veri = {
        "kosular": _quick_reference_ayristir(sayfalar),
        "draw_istatistik": _draw_istatistik_ayristir(tam_metin),
        "veteriner": _veteriner_ayristir(sayfalar),
        "denemeler": _deneme_ayristir(sayfalar),
        "ekipman": _ekipman_ayristir(sayfalar),
        "tarih": _tarih_bul(tam_metin),
    }
    veri["detay"] = _detay_ayristir(sayfalar, veri["tarih"])
    veri["standart"] = _standart_zamanlar_ayristir(tam_metin)
    veri["tempo"] = _tempo_ayristir(sayfalar)
    return veri


_REC = re.compile(r"(\d+)\((\d+)-(\d+)-(\d+)-(\d+)-(\d+)\)")

def _rec_oku(metin, etiket):
    """'Dist ：13(1-3-3-0-6)' kalıbından (start, 1., 2., 3.) döndürür."""
    m = re.search(re.escape(etiket) + r"\s*：\s*" + _REC.pattern, metin)
    if not m:
        return None
    return {"n": int(m.group(1)), "w": int(m.group(2)),
            "p2": int(m.group(3)), "p3": int(m.group(4))}


def _detay_ayristir(sayfalar, bulten_tarihi):
    """
    B1-B22 form sayfalarından at adı anahtarlı derin istatistikler:
    mesafe/pist+mesafe/sınıf/sezon rekorları, 1st-2nd Up, jokey-antrenör
    ortak geçmişi, zemin (G) kaydı, sağlık notları, son koşudan bu yana gün.
    """
    detay = {}
    isim_kalip = re.compile(r"^([A-Z][A-Z' .\-]+?)\s+\((?:AUS|NZ|IRE|GB|USA|FR|SAF|ARG|GER|JPN|ITY|MAC)\)\s+\d", re.M)
    try:
        y, a, g = (int(x) for x in bulten_tarihi.split("-"))
        import datetime as _dt
        bugun = _dt.date(y, a, g)
    except (ValueError, AttributeError):
        bugun = None

    for sayfa in sayfalar:
        if "HKJC Career" not in sayfa:
            continue
        adlar = list(isim_kalip.finditer(sayfa))
        for i, m in enumerate(adlar):
            blok = sayfa[m.start(): adlar[i+1].start() if i+1 < len(adlar) else len(sayfa)]
            # Form satırları (eski koşular) isimden ÖNCE gelir:
            form_blok = sayfa[adlar[i-1].start() if i > 0 else 0: m.start()]
            kayit = {
                "dist": _rec_oku(blok, "Dist"),
                "trk_dist": _rec_oku(blok, "Trk/Dist"),
                "sinif": _rec_oku(blok, "Class"),
                "sezon": _rec_oku(blok, "25/26") or _rec_oku(blok, "26/27"),
                "ilk_cikis": _rec_oku(blok, "1st Up"),
                "tra_joc": _rec_oku(blok, "Tra/Joc"),
                "zemin_g": _rec_oku(blok, "G"),
                "awt": _rec_oku(blok, "AWT"),
                "st": _rec_oku(blok, "ST"),
                "hv": _rec_oku(blok, "HV"),
                "at_jokey": _rec_oku(blok, "Jockey"),  # BU jokeyin BU attaki ortak sicili
                "saglik": bool(re.search(r"(Bleeding|Heart irregularity|Roarer) record", blok)),
                "gun_farki": None,
                "gecmis": _gecmis_kosulari_oku(form_blok),
            }
            if bugun:
                gunler = []
                for t in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b", blok):
                    try:
                        import datetime as _dt
                        d = _dt.date(2000 + int(t[2]), int(t[1]), int(t[0]))
                        if d < bugun:
                            gunler.append((bugun - d).days)
                    except ValueError:
                        pass
                if gunler:
                    kayit["gun_farki"] = min(gunler)
            detay[m.group(1).strip()] = kayit
    return detay


def _rec_puan(rec, kazanma_carpan=4.0, tabela_carpan=2.0):
    """Rekoru 0-100 puana çevirir; az start = nötre doğru istatistiksel büzülme."""
    if not rec or rec["n"] == 0:
        return NOTR
    n = rec["n"]
    kazanma = min(100, rec["w"] / n * 100 * kazanma_carpan)
    tabela = min(100, (rec["w"] + rec["p2"] + rec["p3"]) / n * 100 * tabela_carpan)
    ham = 0.55 * kazanma + 0.45 * tabela
    guven = n / (n + 3.0)  # 1 start → %25 etki, 10 start → %77 etki
    return NOTR + (ham - NOTR) * guven


def _rec_topla(*kayitlar):
    """Birden fazla rekoru (ör. ST + HV = çim) tek rekorda birleştirir."""
    dolu = [r for r in kayitlar if r]
    if not dolu:
        return None
    return {"n": sum(r["n"] for r in dolu), "w": sum(r["w"] for r in dolu),
            "p2": sum(r["p2"] for r in dolu), "p3": sum(r["p3"] for r in dolu)}


_GECMIS_SATIR = re.compile(
    r"(\d{1,2})/(\d{1,2})\s+\*?\d+\s+\d{1,2}/\d{1,2}/\d{2}.*?"
    r"(ST|HV|AWT)\s+[A-C+3—\-\s]*?(\d{3,4})\s+"
    r"(GF|GY|GD|SE|WS|WF|SL|G|Y|S|H)\b")

def _gecmis_kosulari_oku(form_blok):
    """Eski koşu satırlarından [(derece, saha, pist, mesafe, zemin, zaman bilgileri)]"""
    gecmis = []
    for satir in form_blok.split("\n"):
        m = _GECMIS_SATIR.search(satir)
        if not m:
            continue
        try:
            kayit = {"pos": int(m.group(1)), "alan": int(m.group(2)),
                     "pist": m.group(3), "mesafe": int(m.group(4)), "zemin": m.group(5)}
        except ValueError:
            continue
        zaman = _kosu_zamani_oku(satir)
        if zaman:
            kayit["sinif"], kayit["lider_sn"], kayit["son400"], pos2, kayit["fark"] = zaman
            if pos2:
                kayit["pos"] = pos2
        kayit["erken_poz"] = _erken_pozisyon(satir)
        gecmis.append(kayit)
    return gecmis


def profil_ozeti(gecmis, bugun_mesafe=None, bugun_yuzey=None):
    """Bir atın geçmişinden mesafe/yüzey başarı özeti (arayüz için)."""
    def _grup(anahtar_fn):
        grup = {}
        for g in gecmis:
            k = anahtar_fn(g)
            s = grup.setdefault(k, {"n": 0, "w": 0, "t3": 0})
            s["n"] += 1
            s["w"] += 1 if g["pos"] == 1 else 0
            s["t3"] += 1 if g["pos"] <= 3 else 0
        return grup
    mesafeler = _grup(lambda g: g["mesafe"])
    yuzeyler = _grup(lambda g: "Kum" if g["pist"] == "AWT" else "Çim")
    en_iyi_mesafe = None
    adaylar = [(k, v) for k, v in mesafeler.items() if v["n"] >= 2]
    if adaylar:
        en_iyi_mesafe = max(adaylar, key=lambda x: (x[1]["w"] / x[1]["n"], x[1]["t3"] / x[1]["n"]))[0]
    return {"mesafeler": mesafeler, "yuzeyler": yuzeyler, "en_iyi_mesafe": en_iyi_mesafe}


def _zaman_sn(t):
    """'1.09.74' → 69.74 sn"""
    p = t.split(".")
    return int(p[0]) * 60 + int(p[1]) + int(p[2]) / 100.0


_FARK_HARITA = {"Sh": 0.1, "SH": 0.1, "Nk": 0.3, "NK": 0.3, "Hd": 0.15, "HD": 0.15,
                "Ns": 0.05, "NS": 0.05, "DH": 0.0, "-": 0.0, "": 0.0, "ML": 30.0}

def _fark_boy(s):
    """'3¼' → 3.25 boy; 'Sh' → 0.1 vb."""
    if s in _FARK_HARITA:
        return _FARK_HARITA[s]
    s = s.replace("¼", ".25").replace("½", ".5").replace("¾", ".75")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return None


def _standart_zamanlar_ayristir(metin):
    """C4: {(yüzey, mesafe, sınıf): (toplam_sn, son400_sn)}"""
    tablo = {}
    yuzey, mesafe = "Turf", None
    for satir in metin.split("\n"):
        s = satir.strip()
        if "All Weather" in s:
            yuzey = "AWT"; continue
        if "Turf Track" in s:
            yuzey = "Turf"; continue
        if re.fullmatch(r"\d{4}", s):
            mesafe = int(s); continue
        if s.startswith("Gear Change"):
            mesafe = None
        m = re.match(r"^(Group Race|Class \d|G\S{0,4}in Race)\s+(\d\.\d{2}\.\d{2})(.*)$", s)
        if m and mesafe:
            sinif = "Griffin Race" if "in Race" in m.group(1) else m.group(1)
            son400 = None
            kalan = re.findall(r"\d{2}\.\d{2}", m.group(3))
            if kalan:
                son400 = float(kalan[-1])
            tablo[(yuzey, mesafe, sinif)] = (_zaman_sn(m.group(2)), son400)
    return tablo


_SINIF_TOKEN = re.compile(r"\d{1,2}/\d{1,2}/\d{2}\s+([A-Z0-9]+)")
_ZAMAN_BLOK = re.compile(r"(\d{2}\.\d{2})\s+(\d\.\d{2}\.\d{2})")
_SON_DERECE = re.compile(
    r"\s(\d{1,2})\s+((?:\d+)?[¼½¾]?|Sh|SH|Nk|NK|Hd|HD|Ns|NS|DH|ML|-)\s+(\d{1,3}\.\d)\s*f?\s+(?:[A-Z][A-Z/\-\d]{0,11}\s+)?\d{3,4}\s")

def _kosu_zamani_oku(satir):
    """Form satırından (sınıf_etiketi, lider_zamanı_sn, kendi_son400, bitis_pos, fark_boy)"""
    mz = _ZAMAN_BLOK.search(satir)
    if not mz:
        return None
    son400, lider = float(mz.group(1)), _zaman_sn(mz.group(2))
    ms = _SINIF_TOKEN.search(satir)
    ham = ms.group(1) if ms else ""
    if ham.startswith("G") and (ham in ("G1", "G2", "G3") or "GROUP" in ham.upper()):
        sinif = "Group Race"
    elif "GRIF" in ham.upper():
        sinif = "Griffin Race"
    elif ham[:1].isdigit():
        sinif = f"Class {ham[0]}"
    else:
        sinif = None
    md = _SON_DERECE.search(satir)
    pos = int(md.group(1)) if md else None
    fark = _fark_boy(md.group(2)) if md else None
    return sinif, lider, son400, pos, fark


def _erken_pozisyon(satir):
    """Form satırındaki koşu içi pozisyonlardan İLK çağrı pozisyonunu okur (öncü tespiti)."""
    mz = _ZAMAN_BLOK.search(satir)
    if not mz:
        return None
    kuyruk = satir[mz.end():]
    tokenlar = kuyruk.split()
    i = 0
    while i < len(tokenlar) and (re.fullmatch(r"\d{2}\.\d{2}", tokenlar[i]) or tokenlar[i] == "-"):
        i += 1  # atın kendi ara zamanlarını geç
    if i < len(tokenlar) and re.fullmatch(r"\d{1,2}", tokenlar[i]):
        return int(tokenlar[i])
    return None


def _tempo_ayristir(sayfalar):
    """Speed Map sayfalarından: {race_no: {'pace': ..., 'liderler': {at adları}}}"""
    tempo = {}
    for sayfa in sayfalar:
        if "Speed Map" not in sayfa:
            continue
        bloklar = re.split(r"Race\s+(\d+)\s*\|", sayfa)
        for i in range(1, len(bloklar) - 1, 2):
            rn, metin = int(bloklar[i]), bloklar[i + 1]
            mp = re.search(r"Pace:\s*(GOOD TO SLOW|GOOD TO FAST|GOOD|SLOW|FAST)", metin)
            liderler = set()
            for cumle in re.split(r"(?<=[.!])\s+", metin):
                if re.search(r"\b(led|lead|leader|positive|front|speed)\b", cumle, re.I):
                    liderler.update(re.findall(r"\b([A-Z][A-Z']+(?:\s+[A-Z][A-Z']+)+)\b", cumle))
            tempo[rn] = {"pace": (mp.group(1) if mp else ""), "liderler": liderler}
    return tempo


def _tarih_bul(metin):
    m = re.search(r"(\d{2})\s*\|\s*(\d{2})\s*\|\s*(\d{4})", metin)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r"Quick Reference - (\d+) (\w+) (\d{4})", metin)
    if m:
        aylar = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
                 "July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
        return f"{m.group(3)}-{aylar.get(m.group(2),1):02d}-{int(m.group(1)):02d}"
    return ""


_KOSU_BASLIK = re.compile(r"^Race\s+(\d+)\s+(.+?)\s+\$([\d,]+)\s*$")
_KOSU_DETAY = re.compile(
    r"^(\d{1,2}:\d{2})(am|pm)\s+(.+?)\s+([\d,]+)m\s+(Turf|AWT|All Weather)", re.I)
_AT_SATIRI = re.compile(
    r"^\s*(S\d|\d{1,2})\s+"                 # at no veya S1/S2 (yedek)
    r"([0-9WPDUVNTf]*)\s+"                  # son koşular (form) — boş olabilir
    r"([A-Z][A-Z' .()\-]*[A-Z')])\s+"       # at ismi
    r"(\d{1,3})?\s*"                         # rating — griffin'de yok
    r"(\d{1,3})\[(\d+)-(\d+)-(\d+)\]\s+"     # kariyer: start[1.-2.-3.]
    r"(.+?)\s+\[([\d.]+)%\]\s+"              # antrenör [win%]
    r"(.+?)(?:\s+\[([\d.]+)%\])?\s+"         # jokey [win%] — yedekte '---'
    r"(?:(\d{1,2})\s+)?"                     # draw — yedekte yok
    r"(\d{3})\s*$")                          # kilo (lb)


def _quick_reference_ayristir(sayfalar):
    kosular = []
    aktif = None
    for sayfa in sayfalar:
        if "Quick Reference" not in sayfa:
            continue
        satirlar = sayfa.split("\n")
        i = 0
        while i < len(satirlar):
            s = satirlar[i].strip()
            mb = _KOSU_BASLIK.match(s)
            if mb:
                aktif = {"race_no": int(mb.group(1)), "name": mb.group(2).strip(),
                         "prize": mb.group(3), "time": "", "class": "", "band": None,
                         "distance": 0, "surface": "Turf", "horses": []}
                # detay satırı hemen altta
                if i + 1 < len(satirlar):
                    md = _KOSU_DETAY.match(satirlar[i+1].strip())
                    if md:
                        aktif["time"] = md.group(1) + md.group(2)
                        aktif["class"] = md.group(3).strip()
                        aktif["distance"] = int(md.group(4).replace(",", ""))
                        aktif["surface"] = "AWT" if "w" in md.group(5).lower() and "t" != md.group(5).lower() or "AWT" in md.group(5) or "Weather" in md.group(5) else "Turf"
                        mr = re.search(r"Rated\s+(\d+)-(\d+)", md.group(3))
                        aktif["band"] = (int(mr.group(2)), int(mr.group(1))) if mr else None
                        i += 1
                kosular.append(aktif)
                i += 1
                continue
            if aktif is not None:
                ma = _AT_SATIRI.match(satirlar[i])
                if ma:
                    yedek = ma.group(1).startswith("S")
                    jokey = ma.group(11).strip()
                    aktif["horses"].append({
                        "num": ma.group(1) if yedek else int(ma.group(1)),
                        "yedek": yedek,
                        "form": ma.group(2) or "",
                        "name": ma.group(3).strip(),
                        "rt": int(ma.group(4)) if ma.group(4) else None,
                        "starts": int(ma.group(5)),
                        "w1": int(ma.group(6)), "w2": int(ma.group(7)), "w3": int(ma.group(8)),
                        "trainer": ma.group(9).strip(),
                        "trainer_pct": float(ma.group(10)),
                        "jockey": "" if jokey.startswith("-") else jokey,
                        "jockey_pct": float(ma.group(12)) if ma.group(12) else None,
                        "draw": int(ma.group(13)) if ma.group(13) else None,
                        "weight": int(ma.group(14)),
                    })
            i += 1
    kosular.sort(key=lambda k: k["race_no"])
    return kosular


def _draw_istatistik_ayristir(metin):
    """C1 sayfası: 12 aylık draw istatistikleri → {(mesafe,yüzey):{draw:{W,Q,P,F}}}"""
    tablolar = {}
    bolum = re.search(r"Draw Statistics for the Last 12 Months(.+?)(?:C2|Official Veterinary)", metin, re.S)
    if not bolum:
        return tablolar
    aktif = None
    for satir in bolum.group(1).split("\n"):
        s = satir.strip()
        mh = re.match(r"^([\d,]+)m\s+(Turf|AWT)", s)
        if mh:
            aktif = (int(mh.group(1).replace(",", "")), mh.group(2))
            tablolar[aktif] = {}
            continue
        mr = re.match(r"^(\d{1,2})\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", s)
        if mr and aktif:
            tablolar[aktif][int(mr.group(1))] = {
                "W": int(mr.group(2)), "Q": int(mr.group(3)),
                "P": int(mr.group(4)), "F": int(mr.group(5))}
    return tablolar


def _veteriner_ayristir(sayfalar):
    """C2 sayfası: {(race_no, horse_no)} — resmi veteriner kaydı olan atlar."""
    bayraklar = set()
    for sayfa in sayfalar:
        if "Veterinary Examination Records" not in sayfa:
            continue
        son_race = None
        for satir in sayfa.split("\n"):
            m = re.match(r"^\s*(\d{1,2})\s+(\d{1,2})\s+[A-Z][A-Z' ]+", satir)
            if m:
                son_race = int(m.group(1))
                bayraklar.add((son_race, int(m.group(2))))
    return bayraklar


def _deneme_ayristir(sayfalar):
    """B23: deneme koşuları → {(race_no, at_adi): en iyi (pos, alan, tarih)}"""
    denemeler = {}
    for sayfa in sayfalar:
        if "Barrier Trial Information" not in sayfa:
            continue
        for satir in sayfa.split("\n"):
            m = re.match(r"^\s*(\d{1,2})\s+([A-Z][A-Z' \-]+?)\s+(\d{1,2})/(\d{1,2})\s+(\d{2}/\d{2}/\d{4})", satir)
            if m:
                anahtar = (int(m.group(1)), m.group(2).strip())
                pos, alan = int(m.group(3)), int(m.group(4))
                mevcut = denemeler.get(anahtar)
                # en yeni deneme esas alınır (tarih string GG/AA/YYYY → çevir)
                g, a, y = m.group(5).split("/")
                t = f"{y}{a}{g}"
                if mevcut is None or t >= mevcut[2]:
                    denemeler[anahtar] = (pos, alan, t)
    return denemeler


def _ekipman_ayristir(sayfalar):
    """C5: ekipman değişiklikleri → {(race,horse_no): 'B1' vb.}"""
    degisimler = {}
    for sayfa in sayfalar:
        if "Gear Change Summary" not in sayfa:
            continue
        son_race = None
        for satir in sayfa.split("\n"):
            m = re.match(r"^\s*(\d{1,2})?\s+(\d{1,2})\s+[A-Z][A-Z' ]+?\s+([A-Z/\-\d]+)\s*$", satir)
            if m:
                if m.group(1):
                    son_race = int(m.group(1))
                if son_race:
                    degisimler[(son_race, int(m.group(2)))] = m.group(3)
    return degisimler


# ---------------------------------------------------------------------------
# 2) 40 KRİTERLİ PUANLAMA
# ---------------------------------------------------------------------------
def _n(deger, dizi):
    """Koşu içi min-max normalizasyon (0-100). Tek değer/veri yoksa nötr."""
    d = [x for x in dizi if x is not None]
    if deger is None or len(d) < 2 or max(d) == min(d):
        return NOTR
    return (deger - min(d)) / (max(d) - min(d)) * 100.0


def _form_puani(karakter):
    harita = {"1": 100, "2": 80, "3": 65, "4": 50, "5": 35, "6": 25, "7": 15, "8": 10, "9": 5, "0": 0}
    return harita.get(karakter, 0)  # W/P/D/U vb. = 0


def analiz_et(veri: dict, agirliklar: dict | None = None,
              kriter_agirliklari: dict | None = None) -> list[dict]:
    """Ayrıştırılmış PDF verisini 40 kriterle puanlar (kriterler ağırlıklı)."""
    w = {**VARSAYILAN_AGIRLIKLAR, **(agirliklar or {})}
    kw = {**KRITER_AGIRLIKLARI, **(kriter_agirliklari or {})}
    sonuc = []
    for kosu in veri["kosular"]:
        atlar = [h for h in kosu["horses"] if not h["yedek"]]
        yedekler = [h for h in kosu["horses"] if h["yedek"]]
        n = len(atlar)
        rts = [h["rt"] for h in atlar]
        kilolar = [h["weight"] for h in atlar]
        ort_kilo = sum(kilolar) / max(len(kilolar), 1)
        draw_tbl = veri["draw_istatistik"].get((kosu["distance"], kosu["surface"]), {})

        for h in atlar:
            k = {}  # kriter_adi -> (puan, kaynak_notu)

            # ---- A. RATING & SINIF ----
            k["A1 Resmi Rating"] = _n(h["rt"], rts)
            if h["rt"] is not None and kosu["band"]:
                alt, ust = kosu["band"]
                k["A2 Sınıf Bandı Konumu"] = max(0, min(100, (h["rt"] - alt) / max(ust - alt, 1) * 100))
            else:
                k["A2 Sınıf Bandı Konumu"] = NOTR
            k["A3 Kilo Avantajı"] = 100 - _n(h["weight"], kilolar)
            if h["rt"] is not None:
                deger = h["rt"] - (h["weight"] - ort_kilo)  # kilosuna göre rating değeri
                k["A4 Rating/Kilo Dengesi"] = _n(deger, [x["rt"] - (x["weight"] - ort_kilo) for x in atlar if x["rt"] is not None])
            else:
                k["A4 Rating/Kilo Dengesi"] = NOTR
            gecerli_rt = [x for x in rts if x is not None]
            k["A5 Ortalama Üstü Rating"] = (100 if gecerli_rt and h["rt"] is not None and h["rt"] >= sum(gecerli_rt)/len(gecerli_rt) else 30) if gecerli_rt else NOTR

            # ---- B. FORM ----
            f = h["form"]
            k["B1 Son Koşu"] = _form_puani(f[-1]) if f else NOTR
            k["B2 Son 3 Koşu Ort."] = sum(_form_puani(c) for c in f[-3:]) / max(len(f[-3:]), 1) if f else NOTR
            if f:
                agirlikli = [(_form_puani(c), i + 1) for i, c in enumerate(f)]
                k["B3 Son 6 Ağırlıklı"] = sum(p * g for p, g in agirlikli) / sum(g for _, g in agirlikli)
            else:
                k["B3 Son 6 Ağırlıklı"] = NOTR
            if len(f) >= 4:
                ilk = sum(_form_puani(c) for c in f[:len(f)//2]) / (len(f)//2)
                son = sum(_form_puani(c) for c in f[len(f)//2:]) / (len(f) - len(f)//2)
                k["B4 Form Trendi"] = max(0, min(100, 50 + (son - ilk) / 2))
            else:
                k["B4 Form Trendi"] = NOTR
            st = h["starts"]
            k["B5 Kariyer Kazanma %"] = min(100, (h["w1"] / st * 100) * 4) if st else NOTR
            k["B6 Kariyer İlk-3 %"] = min(100, ((h["w1"] + h["w2"] + h["w3"]) / st * 100) * 2) if st else NOTR
            k["B7 Tutarlılık"] = min(100, ((h["w1"] + h["w2"]) / st * 100) * 3) if st else NOTR
            k["B8 Deneyim"] = min(100, st * 8) if st else 0

            # ---- B (devam): DETAY SAYFALARINDAN DERİN FORM ----
            dt = veri.get("detay", {}).get(h["name"], {})
            k["B9 Mesafe Rekoru"] = _rec_puan(dt.get("dist"))
            k["B10 Pist+Mesafe Rekoru"] = _rec_puan(dt.get("trk_dist"))
            k["B11 Sınıf Rekoru"] = _rec_puan(dt.get("sinif"))
            k["B12 Sezon Formu"] = _rec_puan(dt.get("sezon"))
            gf = dt.get("gun_farki")
            if gf is None:
                k["B13 Dinlenme Uyumu"] = NOTR
            elif gf >= 120:  # uzun aradan dönüş → atın 1st Up geçmişi konuşur
                k["B13 Dinlenme Uyumu"] = _rec_puan(dt.get("ilk_cikis"))
            elif 14 <= gf <= 45:
                k["B13 Dinlenme Uyumu"] = 100
            elif gf < 14:
                k["B13 Dinlenme Uyumu"] = 55
            else:
                k["B13 Dinlenme Uyumu"] = 65
            # Bugünkü yüzey: kum (AWT) günü → AWT sicili; çim günü → ST+HV sicili
            if kosu["surface"] == "AWT":
                k["B14 Yüzey Uyumu (Kum)"] = _rec_puan(dt.get("awt"))
            else:
                k["B14 Yüzey Uyumu (Çim)"] = _rec_puan(_rec_topla(dt.get("st"), dt.get("hv")))

            # ---- C. İNSAN FAKTÖRÜ ----
            jp = h["jockey_pct"]
            k["C1 Jokey Kazanma %"] = min(100, jp * 5) if jp is not None else 0
            k["C2 Antrenör Kazanma %"] = min(100, h["trainer_pct"] * 5)
            k["C3 Jokey×Antrenör"] = min(100, ((jp or 0) * h["trainer_pct"]) ** 0.5 * 10)
            k["C4 Elit Jokey"] = 100 if (jp or 0) >= 12 else (60 if (jp or 0) >= 8 else 25)
            k["C5 Elit Antrenör"] = 100 if h["trainer_pct"] >= 10 else (60 if h["trainer_pct"] >= 7.5 else 25)
            k["C6 Jokey Atanmış"] = 100 if h["jockey"] else 0
            k["C7 Jokey-Antrenör Ortak Geçmişi"] = _rec_puan(dt.get("tra_joc"), 6.0, 3.0)
            k["C8 At-Jokey Ortak Sicili"] = _rec_puan(dt.get("at_jokey"), 5.0, 2.5)

            # ---- D. KOŞUL UYUMU (PDF'in kendi 12 aylık draw tablosu) ----
            d = draw_tbl.get(h["draw"]) if h["draw"] else None
            k["D1 Draw Kazanma % (12ay)"] = min(100, d["W"] * 6) if d else NOTR
            k["D2 Draw Tabela % (12ay)"] = min(100, d["P"] * 2.2) if d else NOTR
            k["D3 Draw İlk-4 % (12ay)"] = min(100, d["F"] * 1.6) if d else NOTR
            k["D4 İç Kulvar"] = 100 - ((h["draw"] - 1) / max(n - 1, 1) * 100) if h["draw"] else NOTR
            k["D5 Geniş Alan Dış Draw Baskısı"] = (100 - max(0, (h["draw"] - 8)) * 12) if (h["draw"] and n >= 12) else NOTR
            if kosu["distance"] >= 1400:
                k["D6 Kilo×Mesafe"] = 100 - _n(h["weight"], kilolar)  # uzun mesafede kilo daha kritik
            else:
                k["D6 Kilo×Mesafe"] = NOTR
            # HK'de baskın zemin 'Good'dur; günün zemini bültende olmadığından
            # atın G zeminindeki geçmişi varsayılan uyum göstergesi kabul edilir.
            k["D7 İyi Zemin (G) Uyumu"] = _rec_puan(dt.get("zemin_g"))

            # ---- E. HAZIRLIK & RİSK ----
            deneme = veri["denemeler"].get((kosu["race_no"], h["name"]))
            if deneme:
                pos, alan, _ = deneme
                oran = pos / max(alan, 1)
                k["E1 Deneme Derecesi"] = 100 if pos == 1 else (75 if oran <= 0.34 else (50 if oran <= 0.67 else 20))
                k["E2 Deneme Galibi"] = 100 if pos == 1 else 30
            else:
                k["E1 Deneme Derecesi"] = NOTR
                k["E2 Deneme Galibi"] = NOTR
            k["E3 Veteriner Kaydı"] = 0 if (kosu["race_no"], h["num"]) in veri["veteriner"] else 100
            ekip = veri["ekipman"].get((kosu["race_no"], h["num"]))
            k["E4 Ekipman Değişikliği"] = 60 if (ekip and "1" in ekip) else (40 if ekip else NOTR)
            k["E5 Az Koşu Belirsizliği"] = 100 if st >= 5 else st * 20
            k["E6 Sağlık Geçmişi"] = 25 if dt.get("saglik") else 100  # resmi kanama/kalp/roarer kaydı

            # ---- F. HIZ & ZAMAN (AVELOR'a özgü — kronometreden bağımsız güç puanı) ----
            figurler, kapanislar = [], []
            for g in (dt.get("gecmis") or [])[:6]:
                std = veri.get("standart", {}).get(
                    ("AWT" if g["pist"] == "AWT" else "Turf", g["mesafe"], g.get("sinif")))
                if std and g.get("lider_sn") and g["pist"] in ("ST", "AWT"):
                    kendi = g["lider_sn"] + (0 if g["pos"] == 1 else (g.get("fark") or 0) * 0.17)
                    figurler.append(std[0] - kendi)  # + = standarttan hızlı
                    if std[1] and g.get("son400"):
                        kapanislar.append(std[1] - g["son400"])  # + = standarttan hızlı kapanış
            h["_fig_max"] = max(figurler) if figurler else None
            h["_fig_ort"] = sum(figurler) / len(figurler) if figurler else None
            h["_kapanis"] = max(kapanislar) if kapanislar else None
            erkenler = [g["erken_poz"] for g in (dt.get("gecmis") or [])[:6] if g.get("erken_poz")]
            h["_oncu"] = (sum(erkenler) / len(erkenler) <= 2.5) if erkenler else None
            h["_k"] = k

        # ---- İKİNCİ GEÇİŞ: hız figürleri (koşu içi normalize) + kategoriler ----
        fig_max_l = [x.get("_fig_max") for x in atlar]
        fig_ort_l = [x.get("_fig_ort") for x in atlar]
        kapanis_l = [x.get("_kapanis") for x in atlar]
        onculer = sum(1 for x in atlar if x.get("_oncu"))
        for h in atlar:
            k = h.pop("_k")
            k["F1 En İyi Hız Figürü"] = _n(h.get("_fig_max"), fig_max_l)
            k["F2 Ortalama Hız Figürü"] = _n(h.get("_fig_ort"), fig_ort_l)
            k["F3 Kapanış Gücü (Son 400m)"] = _n(h.get("_kapanis"), kapanis_l)
            # Tempo: atın kendi koşu stilinden (erken pozisyonlar) + koşudaki öncü sayısından
            if h.get("_oncu") is None:
                k["F4 Tempo Senaryosu"] = NOTR
            elif h["_oncu"]:
                k["F4 Tempo Senaryosu"] = 78 if onculer <= 2 else (58 if onculer == 3 else 38)
            else:
                k["F4 Tempo Senaryosu"] = 42 if onculer <= 1 else (52 if onculer <= 3 else 70)
            for alan in ("_fig_max", "_fig_ort", "_kapanis", "_oncu"):
                h.pop(alan, None)

            def _kat_ort(harf):
                pay = payda = 0.0
                for a, v in k.items():
                    if a.startswith(harf):
                        katsayi = kw.get(a, 1.0)
                        pay += katsayi * v
                        payda += katsayi
                return pay / payda if payda else NOTR
            kat = {"rating": _kat_ort("A"), "form": _kat_ort("B"), "insan": _kat_ort("C"),
                   "kosul": _kat_ort("D"), "risk": _kat_ort("E"), "hiz": _kat_ort("F")}
            h["kriterler"] = {a: round(v, 1) for a, v in k.items()}
            h["kategoriler"] = {a: round(v, 1) for a, v in kat.items()}
            h["profil"] = profil_ozeti(dt.get("gecmis", []), kosu["distance"], kosu["surface"])
            h["score"] = round(sum(w[a] * kat[a] for a in w), 1)
            # Mevcut arayüz alanları (dürüst etiketlerle eşleşir):
            h["bio"] = h["kategoriler"]["form"]        # arayüzde: "Form"
            h["aero"] = h["kategoriler"]["rating"]     # arayüzde: "Rating & Sınıf"
            h["lobby"] = h["kategoriler"]["insan"]     # arayüzde: "İnsan Faktörü"
            h["syn"] = h["kategoriler"]["kosul"]       # arayüzde: "Koşul Uyumu"
            h["val"] = False; h["agf"] = 0.0; h["galop"] = "-"
            h["jockey_full"] = h["jockey"]; h["hp"] = h["rt"]; h["start"] = h["draw"]

        atlar.sort(key=lambda x: x["score"], reverse=True)
        madalya = ["🥇 1. Sıra", "🥈 2. Sıra", "🥉 3. Sıra", "🏅 4. Sıra"]
        for i, h in enumerate(atlar):
            h["medal"] = madalya[i] if i < 4 else f"#{i+1}. Sıra"
        for h in yedekler:
            h["medal"] = "⏸ YEDEK"; h["score"] = 0
            h.setdefault("kriterler", {}); h.setdefault("kategoriler", {})
            h["bio"] = h["aero"] = h["lobby"] = h["syn"] = 0
            h["val"] = False; h["agf"] = 0.0; h["galop"] = "-"
        sonuc.append({"race_no": kosu["race_no"], "name": kosu["name"], "time": kosu["time"],
                      "class": kosu["class"], "distance": kosu["distance"],
                      "surface": kosu["surface"], "horses": atlar + yedekler,
                      "agirliklar": {a: round(v, 3) for a, v in w.items()}})
    return sonuc


# ---------------------------------------------------------------------------
# 3) ÖĞRENME — sonuç girildikçe kategori ağırlıklarını günceller
# ---------------------------------------------------------------------------
def agirliklari_guncelle(agirliklar: dict, analiz: list[dict],
                         sonuclar: dict, hiz: float = 0.06) -> tuple[dict, dict]:
    """
    sonuclar: {race_no: kazanan_no}  VEYA  {race_no: [1., 2., 3., 4. at no]}
    Kategori ağırlıkları: ilk-4'ü toplam skordan daha iyi sıralayan kategoriler
    güçlenir (ağırlıklı: 1.lik×4, 2.lik×3, 3.lük×2, 4.lük×1).
    Ayrıca 40 kriterin her birinin ilk-4'ü ne kadar iyi bildiği ölçülür →
    rapor["kriter_perf"] (0-100; yüksek = o kriter gerçek sonucu iyi biliyor).
    """
    w = {**VARSAYILAN_AGIRLIKLAR, **(agirliklar or {})}
    rapor = {"kosu_sayisi": 0, "top1_isabet": 0, "top3_isabet": 0, "tabela_isabet": 0,
             "detay": [], "degisim": {}, "kriter_perf": {}}
    eski = dict(w)
    kriter_toplam, kriter_sayac = {}, {}
    KATSAYI = [4, 3, 2, 1]

    for kosu in analiz:
        rn = kosu["race_no"]
        if rn not in sonuclar:
            continue
        girilen = sonuclar[rn]
        ilk4_no = [int(x) for x in (girilen if isinstance(girilen, (list, tuple)) else [girilen]) if x]
        atlar = [h for h in kosu["horses"] if not h.get("yedek")]
        no_map = {h["num"]: h for h in atlar}
        ilk4 = [no_map[n] for n in ilk4_no if n in no_map]
        if not ilk4:
            continue
        rapor["kosu_sayisi"] += 1
        n = len(atlar)
        toplam_sirali = sorted(atlar, key=lambda x: x["score"], reverse=True)

        kazanan_sira = toplam_sirali.index(ilk4[0]) + 1
        if kazanan_sira == 1: rapor["top1_isabet"] += 1
        if kazanan_sira <= 3: rapor["top3_isabet"] += 1
        tahmin_ilk4 = {h["num"] for h in toplam_sirali[:4]}
        rapor["tabela_isabet"] += len(tahmin_ilk4 & {h["num"] for h in ilk4})

        # Kategori ağırlık güncellemesi (ilk-4 ağırlıklı)
        for kat in w:
            fark_toplam, agirlik_toplam = 0.0, 0.0
            kat_sirali = sorted(atlar, key=lambda x: x["kategoriler"].get(kat, 0), reverse=True)
            for sira, at in enumerate(ilk4):
                katsayi = KATSAYI[sira] if sira < 4 else 1
                fark = (toplam_sirali.index(at) - kat_sirali.index(at)) / max(n - 1, 1)
                fark_toplam += katsayi * fark
                agirlik_toplam += katsayi
            w[kat] *= (1 + hiz * fark_toplam / max(agirlik_toplam, 1))

        # Kriter performansı: her kriter ilk-4'ü ne kadar üstte tutuyor?
        for kriter in (atlar[0].get("kriterler") or {}):
            payda, pay = 0.0, 0.0
            kr_sirali = sorted(atlar, key=lambda x: x["kriterler"].get(kriter, 0), reverse=True)
            for sira, at in enumerate(ilk4):
                katsayi = KATSAYI[sira] if sira < 4 else 1
                yuzdelik = 1 - kr_sirali.index(at) / max(n - 1, 1)  # 1=en üstte bildi
                pay += katsayi * yuzdelik
                payda += katsayi
            kriter_toplam[kriter] = kriter_toplam.get(kriter, 0.0) + pay / max(payda, 1)
            kriter_sayac[kriter] = kriter_sayac.get(kriter, 0) + 1

        rapor["detay"].append({"kosu": rn, "kazanan": ilk4[0]["name"],
                               "tahmin_sirasi": kazanan_sira, "at_sayisi": n,
                               "tabela": f"{len(tahmin_ilk4 & {h['num'] for h in ilk4})}/4"})

    rapor["kriter_perf"] = {kr: round(kriter_toplam[kr] / kriter_sayac[kr] * 100, 1)
                            for kr in kriter_toplam}
    # sınırla ve normalize et
    for kat in w:
        w[kat] = max(0.05, min(0.50, w[kat]))
    toplam = sum(w.values())
    w = {kat: round(v / toplam, 4) for kat, v in w.items()}
    rapor["degisim"] = {kat: round(w[kat] - eski[kat], 4) for kat in w}
    return w, rapor


if __name__ == "__main__":
    import sys, json
    yol = sys.argv[1] if len(sys.argv) > 1 else "racecard.pdf"
    veri = pdf_ayristir(yol)
    analiz = analiz_et(veri)
    print(f"Tarih: {veri['tarih']} | {len(analiz)} koşu ayrıştırıldı")
    for kosu in analiz:
        print(f"\n— Koşu {kosu['race_no']} ({kosu['time']}, {kosu['distance']}m {kosu['surface']}, {kosu['class']})")
        for h in kosu["horses"][:4]:
            print(f"   {h['medal']:<10} #{h['num']:<3} {h['name']:<22} skor={h['score']}"
                  f"  [R:{h.get('aero',0)} F:{h.get('bio',0)} İ:{h.get('lobby',0)} K:{h.get('syn',0)}]")
