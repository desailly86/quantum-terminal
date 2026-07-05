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
    Kaggle 'gdaley/hkracing' veri setini (races.csv + runs.csv, 1997-2005 arası
    binlerce HK koşusu) bizim kriter adlarımıza çevirir. Her koşu için atların
    O GÜNE KADARKİ geçmişinden kriterler türetilir (geleceğe bakma yok):
    A1 rating, A3 kilo, B2 son-3, B5/B6 kariyer, B8 deneyim, B9 mesafe rekoru,
    B13 dinlenme, B14 yüzey uyumu, D4 kulvar. Çıktı egit_ve_backtest ile uyumlu.
    """
    races = pd.read_csv(races_dosya)
    runs = pd.read_csv(runs_dosya)
    races.columns = [c.strip().lower() for c in races.columns]
    runs.columns = [c.strip().lower() for c in runs.columns]
    gerekli = {"race_id", "horse_id", "result"}
    if not gerekli.issubset(runs.columns):
        raise ValueError(f"runs.csv beklenen kolonları içermiyor: {gerekli - set(runs.columns)}")
    df = runs.merge(races[[c for c in ("race_id", "date", "distance", "surface", "venue")
                           if c in races.columns]], on="race_id", how="left")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values(["date", "race_id"] if "date" in df.columns else ["race_id"])
    if max_kosu:
        secilen = df["race_id"].drop_duplicates().tail(max_kosu)
        df = df[df["race_id"].isin(secilen)]

    gecmis: dict = {}  # horse_id → geçmiş koşu listesi
    satirlar = []
    for race_id, grup in df.groupby("race_id", sort=False):
        kayitlar = []
        for _, row in grup.iterrows():
            hid = row["horse_id"]
            g = gecmis.get(hid, [])
            n = len(g)
            w = sum(1 for x in g if x["result"] == 1)
            t3 = sum(1 for x in g if x["result"] <= 3)
            ayni_mesafe = [x for x in g if x.get("distance") == row.get("distance")]
            ayni_yuzey = [x for x in g if x.get("surface") == row.get("surface")]
            son3 = g[-3:]
            satir = {
                "A1 Resmi Rating": float(row["horse_rating"]) if pd.notna(row.get("horse_rating")) else 50.0,
                "A3 Kilo Avantajı": -float(row["actual_weight"]) if pd.notna(row.get("actual_weight")) else 50.0,
                "B2 Son 3 Koşu Ort.": (sum(max(0, 100 - (x["result"] - 1) * 12) for x in son3) / len(son3)) if son3 else 50.0,
                "B5 Kariyer Kazanma %": min(100, w / n * 400) if n else 50.0,
                "B6 Kariyer İlk-3 %": min(100, t3 / n * 200) if n else 50.0,
                "B8 Deneyim": min(100, n * 8),
                "B9 Mesafe Rekoru": (min(100, sum(1 for x in ayni_mesafe if x["result"] <= 3) /
                                         len(ayni_mesafe) * 200) if ayni_mesafe else 50.0),
                "B14 Yüzey Uyumu (Çim)": (min(100, sum(1 for x in ayni_yuzey if x["result"] <= 3) /
                                              len(ayni_yuzey) * 200) if ayni_yuzey else 50.0),
                "B13 Dinlenme Uyumu": 50.0,
                "D4 İç Kulvar": (100 - (float(row["draw"]) - 1) * 7) if pd.notna(row.get("draw")) else 50.0,
                "kosu_id": str(race_id),
                "kazandi": 1 if row["result"] == 1 else 0,
                "ilk4": 1 if row["result"] <= 4 else 0,
            }
            if "date" in df.columns and g and pd.notna(row.get("date")) and g[-1].get("date") is not None:
                gunler = (row["date"] - g[-1]["date"]).days
                satir["B13 Dinlenme Uyumu"] = 100 if 14 <= gunler <= 45 else (65 if gunler <= 90 else 45)
            satirlar.append(satir)
            kayitlar.append((hid, {"result": int(row["result"]) if pd.notna(row["result"]) else 99,
                                   "distance": row.get("distance"), "surface": row.get("surface"),
                                   "date": row.get("date") if "date" in df.columns else None}))
        for hid, kayit in kayitlar:  # koşu bittikten SONRA geçmişe ekle (sızıntı yok)
            gecmis.setdefault(hid, []).append(kayit)
    out = pd.DataFrame(satirlar)
    # kilo negatif ölçekte; koşu içi min-max ile 0-100'e getir
    if "A3 Kilo Avantajı" in out.columns:
        out["A3 Kilo Avantajı"] = out.groupby("kosu_id")["A3 Kilo Avantajı"].transform(
            lambda s: 50.0 if s.nunique() <= 1 else (s - s.min()) / (s.max() - s.min()) * 100)
    return out


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
