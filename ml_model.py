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
