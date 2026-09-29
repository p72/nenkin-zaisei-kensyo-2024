# -*- coding: utf-8 -*-
"""収支の台帳（移植版 `shus.c` `shus_calc.c:shus_ave, shus_shushi` 相当）
=========================================================================
制度ごとに 31 列 × 年度の台帳 `Cc[制度, 列, 年度]` を持つ。列の名前は `C`。

給付費の年度間値（`nendokan`）
    年齢別の年度末値を 2:6:4 の月数で年度間に直す（§7.2 と同じ骨格）
        年度間[y] = Σ_x ( 前[y, x] × 2 + 前[y, x] × riv × 6 + 当[y, x] × 4 ) / 12
        前 = 前年度末[x−1] × 累積調整率[y−1, x−1]、当 = 当年度末[x] × 累積調整率[y, x]
        riv = 改定率[y, x] × 累積調整率[y, x] / 累積調整率[y−1, x−1]
    比例の系列は比例の改定率 `krb` と厚年の調整率、定額系は定額の改定率 `kra` と
    国年の調整率（調整期間の一致では厚年の率）。加給と④の翌年度分は 67 歳の率。
    x の和は 66〜115 歳。66 歳には 67 歳未満が寄せてある（`collapse_below_67`）

収支（`balance`）
    運用収入[y] = 積立金[y−1] × Ri[y] + (保険料 + 国庫 + 支援 + 納付金 − 支出 + 妻積) × Ri2[y]
    収入計 = 保険料 + 運用 + 国庫 + 支援 + 納付金 + 妻積、収支差 = 収入計 − 支出計
    積立金[y] = 積立金[y−1] + 収支差[y]（基準年度の翌年度から）

港: emp_shushi/shus.py:shus_init, shus_premium, shus_fukkjn
港: emp_shushi/shus_calc.py:shus_ave, shus_shushi
仕様: §7.2（厚生年金の収支）、§7.3（年金給付費の月割り）
"""
from enum import IntEnum

import numpy as np

from ...axis import YEARS, AGES
from .inputs import SYSTEMS, NSYS, KOFU, AGE_HI, collapse_below_67

__all__ = ["C", "NCOL", "SERIES", "benefit_by_age", "premium_income", "fixed_items",
           "nendokan", "balance", "totals", "fund_margin"]


class C(IntEnum):
    """`01shushi` の 31 列（港の `Cc[ii][i]` の i）。"""
    SHUNYU = 0            # 収入計
    HOKENRYO = 1          # 保険料収入
    UWANOSE = 2           # (再)上乗せ分（第3種）
    UNYO = 3              # 運用収入
    KOKKO = 4             # 国庫負担
    KOKKO_KISO = 5        # (再)国庫基礎
    KOKKO_KEIKA_HIREI = 6     # (再)国庫経過比例
    KOKKO_KEIKA_TEIGAKU = 7   # (再)国庫経過定額
    KOKKO_KASAAGE = 8     # (再)国庫かさ上げ
    SHIEN_IN = 9          # 支援額収入
    NOFUKIN = 10          # 納付金
    SHISHUTU = 11         # 支出計
    DOKUJI = 12           # 独自給付
    DOKUJI_HIREI = 13     # (再)独自比例
    DOKUJI_TEIGAKU = 14   # (再)独自定額系
    DOKUJI_KAKYU = 15     # (再)独自加給
    KYOSHUTUKIN = 16      # 基礎年金拠出金
    JIMU = 17             # 事務費
    SHIEN_OUT = 18        # 支援額支出
    SHUSHISA = 19         # 収支差
    TUMITATE = 20         # 年度末積立金
    TUMITATE_GENZAI = 21  # 積立金(現在価格)
    PART_HOKENRYO = 22    # (再)パート保険料
    SOHOSHU_SOGAKU = 23   # 総報酬総額
    SOHOSHU = 24          # 総報酬額
    IKUJI_HOSHU = 25      # 育児報酬額
    TUMITATE_DOAI = 26    # 積立度合
    HOKENRYORITU = 27     # 保険料率
    FUKA_RITU = 28        # 賦課保険料率
    YOBI = 29             # （空）
    TUMATUMI = 30         # 妻積み分配等


NCOL = len(C)

# 年齢別の給付の系列（港の E3dxb の jj）と列・改定率の種類
#   kind 'h': 比例（krb と厚年の調整率）、't': 定額（kra と国年の調整率）
#   fixed67: 67 歳の率を使う（加給・④の翌年度分）
#   pre/end: 前年度末・当年度末に使う系列。pre_shift=1 なら前年度の行を読む
#   (jj, 列, kind, fixed67, pre, end, pre_shift)
SERIES = (
    (0, C.DOKUJI_HIREI, "h", False, 0, 0, 1),
    (1, C.DOKUJI_TEIGAKU, "t", False, 1, 1, 1),
    (2, C.DOKUJI_KAKYU, "t", True, 2, 2, 1),
    (3, C.KOKKO_KEIKA_HIREI, "h", False, 3, 3, 1),
    (4, C.KOKKO_KEIKA_TEIGAKU, "t", False, 4, 4, 1),
    (5, C.KOKKO_KASAAGE, "t", False, 5, 5, 1),
    (6, C.KYOSHUTUKIN, "t", False, 6, 10, 0),      # 基本: 前年度末の翌年度分 → 当年度末
    (7, C.KOKKO_KISO, "t", False, 7, 11, 0),
    (8, C.KYOSHUTUKIN, "t", True, 8, 12, 0),       # 加給: 67 歳の率
    (9, C.KOKKO_KISO, "t", True, 9, 13, 0),
)
NENDOHOSEI_SERIES = (0, 1, 2)                     # 年度補正を掛ける系列（独自給付）
BENEFIT_COLS = tuple(sorted(set(s[1] for s in SERIES)))


def benefit_by_age(shus, kyos, kokusyushi=None, nendohosei=1.):
    """年齢別の給付の系列 `E[制度, 14, YEARS.n, AGES.n]`（港の E3dxb。67 歳未満は 66 歳へ）。
    `kokusyushi`（調整期間の一致）があれば国年の拠出金・特別国庫（`kyos.extra`）を厚年の拠出金の系列に、
    新法寡婦年金（年度末）を加給の系列（66 歳）に足す（港 shus.c の Touitu の枝）。"""
    E = np.zeros((NSYS, 14, YEARS.n, AGES.n))
    for s, name in enumerate(SYSTEMS):
        sh = shus[name]
        E[s, 0] = sh.hirei
        E[s, 1] = sh.teigaku
        E[s, 2] = sh.kakyu
        E[s, 3] = sh.kokko_hirei
        E[s, 4] = sh.kokko_teigaku
        E[s, 5] = sh.kokko_kasaage
    for kt in range(2):
        E[:, 6 + 2 * kt] = kyos.kyos[kt, :, 0]         # 前年度末の翌年度分
        E[:, 7 + 2 * kt] = kyos.kokko[kt, :, 0]
        E[:, 10 + 2 * kt] = kyos.kyos[kt, :, 1]        # 当年度末
        E[:, 11 + 2 * kt] = kyos.kokko[kt, :, 1]
    if kokusyushi is not None:
        if kyos.extra is None:
            raise ValueError("調整期間の一致には kyos.extra（国年 ss=7,8）が要る")
        for kt in range(2):
            E[0, 6 + 2 * kt] += kyos.extra[kt, 0, 0]
            E[0, 7 + 2 * kt] += kyos.extra[kt, 1, 0]
            E[0, 10 + 2 * kt] += kyos.extra[kt, 0, 1]
            E[0, 11 + 2 * kt] += kyos.extra[kt, 1, 1]
        E = collapse_below_67(E)
        E[0, 2, :, AGES.i(66)] += kokusyushi[9] / nendohosei
        return E
    return collapse_below_67(E)


def premium_income(pol, shus, prem, Cc, ks, houjou=0, kokusyushi=None):
    """保険料収入と報酬総額（`Cc[1][2][22][23][24][25]`）。適用拡大の年度は
    `PARTHOU` の分を報酬と被保険者数に足す。戻り値は足した後の A・An 等。
    `houjou` 1〜3 は標準報酬上限の見直し（レバー）: 報酬を施行年度は半分、以降は倍率で増やす。"""
    shunor = pol.get("shushi.shunor")
    cbm = pol.get("shushi.part.cbm_pt1")
    i0 = YEARS.i(ks) + 1
    A = {}
    hf = None
    if houjou:
        r = [float(v) for v in pol.get("shushi.houjou")[("r75", "r83", "r98")[houjou - 1]]]
        hy = YEARS.i(pol.get("shushi.years.houjou_yr"))
        rs = np.array([1., r[0], r[1], r[0]])                       # 性 0 計 / 1 男 / 2 女 / 3 第3種
        hf = np.ones((4, YEARS.n))
        hf[:, hy] = 1. + (rs - 1.) / 2.
        hf[:, hy + 1:] = rs[:, None]
    for s, name in enumerate(SYSTEMS):
        sh = shus[name]
        snc = shunor if name == "kou" else 1.
        a, aiku, a60, a65, a70 = (x.copy() for x in (sh.a, sh.aiku, sh.a60, sh.a65, sh.a70))
        part = sh.part
        if hf is not None:
            a = a * hf; aiku = aiku * hf
            a[0] = a[1:4].sum(0); aiku[0] = aiku[1:4].sum(0)
            part = {}
            for y, p in sh.part.items():
                q = {k: v.copy() for k, v in p.items()}
                if YEARS.i(y) >= hy:
                    q["a"] = q["a"] * rs; q["aiku"] = q["aiku"] * rs
                    q["a"][0] = q["a"][1:4].sum(); q["aiku"][0] = q["aiku"][1:4].sum()
                part[y] = q
        an, aniku = a * snc, aiku * snc
        pb = prem.avg[name]
        if name == "kou":
            pk = prem.rate["kou"]
            uwa = an[3] * (prem.avg[KOFU] - pb)
            Cc[s, C.HOKENRYO, i0:] = an[0, i0:] * pb[i0:] + uwa[i0:]
            Cc[s, C.UWANOSE, i0:] = uwa[i0:]
            for y, p in part.items():
                i = YEARS.i(y)
                if i < i0:
                    continue
                f = cbm / 12.
                if cbm <= 6.:
                    r = pk[i]
                else:
                    r = ((cbm - 6.) * pk[i - 1] + 6. * pk[i]) / cbm
                anpart = p["a"] * f * snc
                Cc[s, C.PART_HOKENRYO, i] = anpart[0] * r
                Cc[s, C.HOKENRYO, i] += Cc[s, C.PART_HOKENRYO, i]
                a[:, i] += p["a"] * f
                aiku[:, i] += p["aiku"] * f
                a60[:, i] += p["a60"] * f
                a65[:, i] += p["a65"] * f
                a70[:, i] += p["a70"] * f
                an[:, i] += anpart
                aniku[:, i] += p["aiku"] * f * snc
        else:
            Cc[s, C.HOKENRYO, i0:] = an[0, i0:] * pb[i0:]
        if kokusyushi is not None and name == "kou":
            Cc[s, C.HOKENRYO, i0:] += kokusyushi[0, i0:]              # 調整期間の一致: 国年の保険料収入
        Cc[s, C.SOHOSHU_SOGAKU, i0:] = a[0, i0:] + aiku[0, i0:]
        Cc[s, C.SOHOSHU, i0:] = an[0, i0:]
        Cc[s, C.IKUJI_HOSHU, i0:] = aniku[0, i0:]
        A[name] = dict(a=a, aiku=aiku, a60=a60, a65=a65, a70=a70, an=an, aniku=aniku)
    return A


def fixed_items(pol, shus, E, nofu, tumazumi, Cc, ks, kokusyushi=None):
    """積立金の期首残高、納付金、事務費、妻積（`Cc[9][10][17][18][20][30]`）。
    事務費は実績のあと、2025年度以降を被保険者数と物価（当年度）で延ばす。
    `kokusyushi`（調整期間の一致）があれば国年の積立金・支援額・融資債権・一時金等・妻積を厚年に足す。"""
    i0 = YEARS.i(ks) + 1
    kijun = YEARS.i(pol.get("shushi.years.kijun"))
    funds = pol.get("shushi.tumitate_2022")
    J = pol.get("shushi.jimu")
    ext_from = YEARS.i(J["extend_from"])
    ext_base = YEARS.i(J["extend_base"])
    for s, name in enumerate(SYSTEMS):
        Cc[s, C.TUMITATE, kijun] = funds[name]
        Cc[s, C.SHIEN_IN, i0:] = 0.
        Cc[s, C.SHIEN_OUT, i0:] = 0.
        if name == "kou":
            Cc[s, C.NOFUKIN, i0:] = nofu[i0:]
        jimu = YEARS.zeros()
        for y, v in sorted((int(y), v) for y, v in J[name].items()):
            jimu[YEARS.i(y):] = v
        ap = shus[name].ap[0]
        with np.errstate(divide="ignore", invalid="ignore"):
            ext = jimu[ext_base] / ap[ext_base] * ap * E.id_cid_2
        jimu[ext_from:] = ext[ext_from:]
        Cc[s, C.JIMU, i0:] = jimu[i0:]
        Cc[s, C.TUMATUMI, i0:] = tumazumi[s, i0:]
        if kokusyushi is not None and name == "kou":
            K = kokusyushi
            ikan = {int(y): v for y, v in pol.get("shushi.kokunen_tumitate_ikan").items()}
            Cc[s, C.TUMITATE, kijun] += ikan[YEARS.label(kijun)]
            Cc[s, C.SHIEN_IN, i0:] += K[1, i0:] + K[2, i0:]
            Cc[s, C.NOFUKIN, i0:] += K[3, i0:]
            Cc[s, C.JIMU, i0:] += K[5, i0:] + K[6, i0:] + K[7, i0:] + K[8, i0:]
            Cc[s, C.TUMATUMI, i0:] += K[4, i0:]


def nendokan(Cc, E, Sh, St, kra, krb, i_from, i_to, nendohosei=1., touitu=False):
    """年齢別の年度末値を年度間値に直して給付の列に入れる（年度 `i_from`〜`i_to` を作り直す）。
    `Sh/St[YEARS.n, AGES.n]` 厚年・国年の累積調整率、`kra/krb` 定額・比例の改定率。"""
    ys = np.arange(i_from, i_to + 1)
    xs = np.arange(AGES.i(66), AGES.i(AGE_HI) + 1)
    x67 = np.full_like(xs, AGES.i(67))
    for col in BENEFIT_COLS:
        Cc[:, col, ys] = 0.
    for jj, col, kind, fixed, pre, end, shift in SERIES:
        if kind == "h" or touitu:
            S = Sh
        else:
            S = St
        R = krb if kind == "h" else kra
        dx = x67 if fixed else xs
        S_k = S[np.ix_(ys, dx)]
        S_km1 = S[np.ix_(ys - 1, dx - 1)]
        riv = R[np.ix_(ys, dx)] * S_k / S_km1
        Epre = E[:, pre][:, ys - shift][:, :, xs - 1]
        Eend = E[:, end][:, ys][:, :, xs]
        bpre = Epre * S_km1[None]
        bend = Eend * S_k[None]
        term = (bpre * 2. + bpre * riv[None] * 6. + bend * 4.) / 12.
        v = term.sum(axis=2)
        if jj in NENDOHOSEI_SERIES:
            v = v * nendohosei
        Cc[:, col, ys] += v


def balance(Cc, E, kijun_i, i_from, i_to):
    """収支と積立金（年度 `i_from`〜`i_to`）。積立金の漸化式だけ年度を逐次に回す。"""
    ys = slice(i_from, i_to + 1)
    Cc[:, C.KOKKO, ys] = (Cc[:, C.KOKKO_KISO, ys] + Cc[:, C.KOKKO_KEIKA_HIREI, ys]
                          + Cc[:, C.KOKKO_KEIKA_TEIGAKU, ys] + Cc[:, C.KOKKO_KASAAGE, ys])
    Cc[:, C.DOKUJI, ys] = (Cc[:, C.DOKUJI_HIREI, ys] + Cc[:, C.DOKUJI_TEIGAKU, ys]
                           + Cc[:, C.DOKUJI_KAKYU, ys])
    Cc[:, C.SHISHUTU, ys] = (Cc[:, C.DOKUJI, ys] + Cc[:, C.KYOSHUTUKIN, ys]
                             + Cc[:, C.JIMU, ys] + Cc[:, C.SHIEN_OUT, ys])
    net = (Cc[:, C.HOKENRYO, ys] + Cc[:, C.KOKKO, ys] + Cc[:, C.SHIEN_IN, ys]
           + Cc[:, C.NOFUKIN, ys] - Cc[:, C.SHISHUTU, ys])
    for i in range(i_from, i_to + 1):
        j = i - i_from
        unyo = Cc[:, C.TUMITATE, i - 1] * E.ri[i] + (net[:, j] + Cc[:, C.TUMATUMI, i]) * E.ri2[i]
        Cc[:, C.UNYO, i] = unyo
        Cc[:, C.SHUNYU, i] = (Cc[:, C.HOKENRYO, i] + unyo + Cc[:, C.KOKKO, i] + Cc[:, C.SHIEN_IN, i]
                              + Cc[:, C.NOFUKIN, i] + Cc[:, C.TUMATUMI, i])
        Cc[:, C.SHUSHISA, i] = Cc[:, C.SHUNYU, i] - Cc[:, C.SHISHUTU, i]
        if i > kijun_i:
            Cc[:, C.TUMITATE, i] = Cc[:, C.TUMITATE, i - 1] + Cc[:, C.SHUSHISA, i]
        else:
            Cc[:, C.SHUNYU, i] = 0.
            Cc[:, C.UNYO, i] = 0.
            Cc[:, C.SHUSHISA, i] = 0.


def totals(Cc):
    """制度計（Σ制度）を先頭に足して `(NSYS + 1, NCOL, YEARS.n)` に。計は計算で出す。"""
    return np.concatenate([Cc.sum(axis=0, keepdims=True), Cc], axis=0)


def fund_margin(Cc, kend_i, ca):
    """有限均衡の条件: 積立金[kend−1] − 支出[kend] × 積立度合（制度計）。"""
    return Cc[:, C.TUMITATE, kend_i - 1].sum() - Cc[:, C.SHISHUTU, kend_i].sum() * ca
