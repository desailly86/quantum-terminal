# -*- coding: utf-8 -*-
"""
ml_model.py — Gerçek öğrenen model katmanı
===========================================
Girdi: kriter vektörleri (sha_tin_motoru veya evrensel_kriterle çıktısı)
Model: Lojistik regresyon (şeffaf: her kriterin öğrenilmiş katsayısı okunur)
Çıktı: koşu içinde normalize edilmiş KAZANMA OLASILIĞI + value bet hesabı

İki eğitim yolu:
  A) Birikmiş kendi verileriniz: her yarış günü analiz + girilen sonuçlar
     buluta kaydediliyor; egitim_verisi_olustur() bunları satırlaştırır.
  B) Tarihsel CSV: tek sütununda kriter adları olan geniş bir tablo
     (ör. uygulamanın "eğitim verisi indir" çıktısı) yüklenebilir.

DÜRÜSTLÜK: Model ancak yüzlerce koşuyla anlamlı öğrenir; backtest sonucu
ne derse desin gelecekteki isabet garantisi yoktur. HK bahis havuzu çok
verimlidir; hedef küçük ve ölçülebilir bir istatistiksel kenardır.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    SKLEARN_VAR = True
except ImportError:
    SKLEARN_VAR = False


def egitim_verisi_olustur(analizler: list[tuple[str, list]], sonuclar: dict) -> pd.DataFrame:
    """
    analizler: [(tarih, analiz_listesi), ...]
    sonuclar:  {(tarih, race_no): [1., 2., 3., 4. at no]}
    → Satır=at, sütun=kriterler + kosu_id + kazandi/ilk4
    """
    satirlar = []
    for tarih, analiz in analizler:
        for r in analiz:
            anahtar = (tarih, r["race_no"])
            if anahtar not in sonuclar:
                continue
            ilk4 = [int(x) for x in sonuclar[anahtar] if x]
            for h in r["horses"]:
                if h.get("yedek") or not h.get("kriterler"):
                    continue
                satir = dict(h["kriterler"])
                satir["kosu_id"] = f"{tarih}_R{r['race_no']}"
                satir["kazandi"] = 1 if ilk4 and h["num"] == ilk4[0] else 0
                satir["ilk4"] = 1 if h["num"] in ilk4 else 0
                satirlar.append(satir)
    return pd.DataFrame(satirlar)


def egit_ve_backtest(df: pd.DataFrame, hedef: str = "kazandi") -> tuple[object, dict, pd.DataFrame]:
    """
    GroupKFold (koşu bazlı) backtest + tüm veriyle final model.
    Dönüş: (model, rapor, katsayilar_df)
    """
    if not SKLEARN_VAR:
        raise RuntimeError("scikit-learn kurulu değil (requirements.txt'e 'scikit-learn' ekleyin).")
    kriter_kolonlari = [c for c in df.columns if c not in ("kosu_id", "kazandi", "ilk4")]
    X = df[kriter_kolonlari].fillna(50.0).to_numpy()
    y = df[hedef].to_numpy()
    gruplar = df["kosu_id"].to_numpy()
    n_kosu = df["kosu_id"].nunique()

    rapor = {"kosu": int(n_kosu), "at": int(len(df)), "kriter": len(kriter_kolonlari),
             "cv_top1": None, "cv_top3": None}
    if n_kosu >= 10:  # backtest için asgari
    # koşu-bazlı çapraz doğrulama: model hiç görmediği koşularda denenir
        kat = min(5, n_kosu)
        top1 = top3 = toplam = 0
        for egit_idx, test_idx in GroupKFold(n_splits=kat).split(X, y, gruplar):
            model = LogisticRegression(max_iter=2000, C=0.5)
            model.fit(X[egit_idx], y[egit_idx])
            test_df = df.iloc[test_idx].copy()
            test_df["p"] = model.predict_proba(X[test_idx])[:, 1]
            for _, grup in test_df.groupby("kosu_id"):
                if grup["kazandi"].sum() == 0:
                    continue
                sirali = grup.sort_values("p", ascending=False)
                kaz_sira = int(np.where(sirali["kazandi"].to_numpy() == 1)[0][0]) + 1
                top1 += kaz_sira == 1
                top3 += kaz_sira <= 3
                toplam += 1
        if toplam:
            rapor["cv_top1"] = round(top1 / toplam * 100, 1)
            rapor["cv_top3"] = round(top3 / toplam * 100, 1)
            rapor["cv_kosu"] = toplam

    final = LogisticRegression(max_iter=2000, C=0.5)
    final.fit(X, y)
    final.kriter_kolonlari_ = kriter_kolonlari
    katsayilar = pd.DataFrame({"Kriter": kriter_kolonlari,
                               "Katsayı": final.coef_[0].round(4)}).sort_values(
        "Katsayı", ascending=False)
    return final, rapor, katsayilar


def olasilik_ekle(model, analiz: list[dict]) -> list[dict]:
    """Her ata koşu içinde 1'e normalize edilmiş kazanma olasılığı ekler."""
    for r in analiz:
        atlar = [h for h in r["horses"] if not h.get("yedek") and h.get("kriterler")]
        if not atlar:
            continue
        X = np.array([[h["kriterler"].get(c, 50.0) for c in model.kriter_kolonlari_]
                      for h in atlar])
        ham = model.predict_proba(X)[:, 1]
        toplam = ham.sum() or 1.0
        for h, p in zip(atlar, ham):
            h["olasilik"] = round(float(p / toplam) * 100, 1)  # koşu içinde %'ye normalize
    return analiz


def value_hesapla(olasilik_yuzde: float, oran: float) -> dict:
    """Model olasılığı vs bahis oranı → beklenen değer.
    oran: ondalık (ör. 4.50). Value = p * oran - 1  (pozitifse avantaj)."""
    p = olasilik_yuzde / 100.0
    deger = p * oran - 1.0
    return {"ima_edilen": round(100.0 / oran, 1), "model": olasilik_yuzde,
            "value": round(deger * 100, 1), "oynanabilir": deger > 0.05}


def kaggle_hazirla(races_dosya, runs_dosya, max_kosu: int | None = None) -> pd.DataFrame:
    """
    Kaggle 'gdaley/hkracing' setini (1997-2005, 6.349 HK koşusu) MOTORLA AYNI
    kriter adları ve ölçekleriyle eğitim satırlarına çevirir. Her değer atın
    O GÜNE KADARKİ geçmişinden türetilir (geleceğe bakma yok). Jokey/antrenör
    kazanma yüzdeleri de o güne kadarki gerçek sicilden yürütülür.
    """
    races = pd.read_csv(races_dosya)
    runs = pd.read_csv(runs_dosya)
    races.columns = [c.strip().lower() for c in races.columns]
    runs.columns = [c.strip().lower() for c in runs.columns]
    df = runs.merge(races[[c for c in ("race_id", "date", "surface", "distance", "race_class")
                           if c in races.columns]], on="race_id", how="left")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values(["date", "race_id"])
    df = df[pd.notna(df["result"])]
    if max_kosu:
        secilen = df["race_id"].drop_duplicates().tail(max_kosu)
        df = df[df["race_id"].isin(secilen)]

    at_gecmis, jokey, antrenor = {}, {}, {}
    satirlar = []
    for race_id, grup in df.groupby("race_id", sort=False):
        rc = grup.iloc[0]
        alan = len(grup)
        guncel = []
        onculer = 0
        on_kayitlar = []
        for _, r in grup.iterrows():
            g = at_gecmis.get(r["horse_id"], [])
            erken = [x["ep"] for x in g[-3:] if x["ep"] == x["ep"]]  # NaN filtre
            oncu = (sum(erken) / len(erken) <= 2.5) if erken else None
            onculer += 1 if oncu else 0
            on_kayitlar.append((r, g, oncu))
        for r, g, oncu in on_kayitlar:
            n = len(g); w = sum(1 for x in g if x["res"] == 1)
            t3 = sum(1 for x in g if x["res"] <= 3)
            son3 = g[-3:]
            ayni_m = [x for x in g if x["dist"] == rc.get("distance")]
            ayni_y = [x for x in g if x["surf"] == rc.get("surface")]
            js = jokey.get(r.get("jockey_id"), (0, 0))
            ts = antrenor.get(r.get("trainer_id"), (0, 0))
            hizlar = [x["hiz"] for x in g[-5:]]
            yas = r.get("horse_age")
            satir = {
                "A1 Resmi Rating": float(r["horse_rating"]) if pd.notna(r.get("horse_rating")) else np.nan,
                "A3 Kilo Avantajı": -float(r["actual_weight"]) if pd.notna(r.get("actual_weight")) else np.nan,
                "B2 Son 3 Koşu Ort.": (np.mean([max(0, 100 - (x["res"] - 1) * 12) for x in son3])
                                       if son3 else 50.0),
                "B5 Kariyer Kazanma %": min(100, w / n * 400) if n else 50.0,
                "B6 Kariyer İlk-3 %": min(100, t3 / n * 200) if n else 50.0,
                "B8 Deneyim": min(100, n * 8),
                "B9 Mesafe Rekoru": (min(100, sum(1 for x in ayni_m if x["res"] <= 3) / len(ayni_m) * 150)
                                     if len(ayni_m) >= 2 else 50.0),
                "B16 Yaş": (80 if yas == 2 else 100 if 3 <= (yas or 0) <= 5 else 65 if yas == 6 else 45)
                           if pd.notna(yas) else 50.0,
                "C1 Jokey Kazanma %": min(100, js[1] / js[0] * 500) if js[0] >= 20 else 50.0,
                "C2 Antrenör Kazanma %": min(100, ts[1] / ts[0] * 500) if ts[0] >= 20 else 50.0,
                "D4 İç Kulvar": (100 - (float(r["draw"]) - 1) / max(alan - 1, 1) * 100)
                                if pd.notna(r.get("draw")) else 50.0,
                "F1 En İyi Hız Figürü": max(hizlar) * 100 if hizlar else np.nan,
                "F2 Ortalama Hız Figürü": np.mean(hizlar) * 100 if hizlar else np.nan,
                "F4 Tempo Senaryosu": (50.0 if oncu is None else
                                       (78 if oncu and onculer <= 2 else 58 if oncu and onculer == 3
                                        else 38 if oncu else
                                        (42 if onculer <= 1 else 52 if onculer <= 3 else 70))),
                "kosu_id": str(race_id),
                "kazandi": 1 if r["result"] == 1 else 0,
                "ilk4": 1 if r["result"] <= 4 else 0,
            }
            # Yüzey uyumu: bugünkü yüzeye denk gelen kolona yaz (motor adlarıyla)
            uyum = (min(100, sum(1 for x in ayni_y if x["res"] <= 3) / len(ayni_y) * 150)
                    if len(ayni_y) >= 2 else 50.0)
            if rc.get("surface") == 1:
                satir["B14 Yüzey Uyumu (Kum)"] = uyum
                satir["B14 Yüzey Uyumu (Çim)"] = 50.0
            else:
                satir["B14 Yüzey Uyumu (Çim)"] = uyum
                satir["B14 Yüzey Uyumu (Kum)"] = 50.0
            # Dinlenme + sınıf hareketi (motor kovalarıyla)
            if g and "date" in df.columns and pd.notna(rc.get("date")) and g[-1]["tarih"] is not None:
                gun = (rc["date"] - g[-1]["tarih"]).days
                satir["B13 Dinlenme Uyumu"] = (100 if 14 <= gun <= 45 else 55 if gun < 14
                                               else 65 if gun <= 90 else 50)
            else:
                satir["B13 Dinlenme Uyumu"] = 50.0
            if g and pd.notna(g[-1]["cls"]) and pd.notna(rc.get("race_class")):
                hareket = rc["race_class"] - g[-1]["cls"]
                satir["A6 Sınıf Hareketi"] = 75 if hareket > 0 else (50 if hareket == 0 else 30)
            else:
                satir["A6 Sınıf Hareketi"] = 50.0
            satirlar.append(satir)
            hiz_pct = 1 - (r["result"] - 1) / max(alan - 1, 1)
            guncel.append((r["horse_id"], r.get("jockey_id"), r.get("trainer_id"),
                           {"res": int(r["result"]), "dist": rc.get("distance"),
                            "surf": rc.get("surface"), "tarih": rc.get("date"),
                            "cls": rc.get("race_class"), "ep": r.get("position_sec1", np.nan),
                            "hiz": hiz_pct}, int(r["result"] == 1)))
        for hid, jid, tid, kayit, kazandi in guncel:
            at_gecmis.setdefault(hid, []).append(kayit)
            jn, jw = jokey.get(jid, (0, 0)); jokey[jid] = (jn + 1, jw + kazandi)
            tn, tw = antrenor.get(tid, (0, 0)); antrenor[tid] = (tn + 1, tw + kazandi)

    out = pd.DataFrame(satirlar)
    # A1 ve A3'ü koşu içi 0-100'e normalize et (motorla aynı mantık)
    for kol in ("A1 Resmi Rating", "A3 Kilo Avantajı"):
        out[kol] = out.groupby("kosu_id")[kol].transform(
            lambda s: pd.Series(50.0, index=s.index) if s.nunique() <= 1
            else (s - s.min()) / (s.max() - s.min()) * 100)
    return out.fillna(50.0)


def model_kaydet(model) -> str:
    """Modeli JSON'a serileştirir (buluta kaydedilebilir, joblib gerekmez)."""
    return json.dumps({"kolonlar": model.kriter_kolonlari_,
                       "coef": model.coef_[0].tolist(),
                       "intercept": float(model.intercept_[0])})


def model_yukle(js: str):
    if not SKLEARN_VAR:
        raise RuntimeError("scikit-learn kurulu değil.")
    d = json.loads(js)
    model = LogisticRegression()
    model.classes_ = np.array([0, 1])
    model.coef_ = np.array([d["coef"]])
    model.intercept_ = np.array([d["intercept"]])
    model.kriter_kolonlari_ = d["kolonlar"]
    return model
