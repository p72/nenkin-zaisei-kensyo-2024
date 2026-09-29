# -*- coding: utf-8 -*-
"""⑤の出力（移植版 `shus_out.c` 相当）— `01shushi` `03summary` `cuta/cutb` `Tokutyo` の書き手と読み手
==========================================================================================================
列の並びと書式は港と同じにして、`検証/オプション試算/compare_option.py` が無改造で読めるようにする。
港が①のヘッダを写す部分（`flck.c`）と `shus_fullout.c` の詳細表は出さない。

派生の列（港は出力のついでに作る）
    積立金(現在価格) = 年度末積立金 / Id_Hhd
    積立度合 = 前年度末積立金 / 当年度の支出計
    保険料率 = 制度の保険料率（制度計は厚年）
    賦課保険料率 = (支出計 − 上乗せ分 − 国庫負担 − 支援額収入 − 納付金) / 総報酬額
制度計は Σ制度（港は基準年度の積立金だけ厚年のみを出す。高速版は計を出す）。

港: emp_shushi/shus_out.py:shus_econ_out, shus_nin_out, shus_shushiout, shus_cutout, shus_summary, shus_Tokutyoout
仕様: §12.4（出力）
"""
import os

import numpy as np

from ...axis import YEARS, AGES
from ...io_port import lines_of
from .inputs import SYSTEMS, NSYS, AGE_LO, AGE_HI
from .shushi import C, NCOL, totals

__all__ = ["SYS_OUT", "COLS_SHUSHI", "TITLE_BEFORE", "TITLE_AFTER", "shushi_table", "kend_of",
           "summary_table", "write_shushi", "write_summary", "write_cut", "write_tokutyo",
           "to_port_csv", "read_shushi", "read_summary", "read_cut"]

SYS_OUT = ("tou",) + SYSTEMS
SYS_LABEL = {"tou": "全厚年", "kou": "旧厚年", "kok": "国共", "ren": "地共", "sig": "私学"}
COLS_SHUSHI = ("収入計", "保険料収入", "(再)上乗せ分", "運用収入", "国庫負担", "(再)国庫基礎",
               "(再)国庫経過比例", "(再)国庫経過定額", "(再)国庫かさ上げ", "支援額収入", "納付金",
               "支出計", "独自給付", "(再)独自比例", "(再)独自定額系", "(再)独自加給",
               "基礎年金拠出金", "事務費", "支援額支出", "収支差", "年度末積立金", "積立金(現在価格)",
               "(再)パート保険料", "総報酬総額", "総報酬額", "育児報酬額", "積立度合", "保険料率",
               "賦課保険料率", "", "妻積み分配等")
TITLE_ECON = "経済前提等"
TITLE_BEFORE = "収支見通し【スライド調整前】"
TITLE_AFTER = "収支見通し【スライド調整後】"
TITLE_KEND = "調整最終年度"
SUMMARY_COLS = ("年度", "物価", "賃金", "運用利回り", "比例改定率", "比例既裁68歳", "基礎改定率", "基礎既裁68歳",
                "モデル年金額", "うち比例", "うち基礎", "可処分所得",
                "所得代替率", "うち比例", "うち基礎", "（参考）所得代替率(一元化前)",
                "比例カット67", "比例カット68", "基礎カット67", "基礎カット68", "mファイル",
                "モデル年金額（物価割り戻し）", "うち比例（物価割り戻し）", "うち基礎（物価割り戻し）",
                "可処分所得（物価割り戻し）")
_E = "%20.13e"
_E14 = "%20.14e"


def _tanni(i):
    if i <= C.IKUJI_HOSHU or i == C.TUMATUMI:
        return 1e-8
    if i in (C.HOKENRYORITU, C.FUKA_RITU):
        return 1e2
    return 1.


def shushi_table(r, Cc):
    """台帳 `Cc[NSYS, NCOL, YEARS.n]` → 制度計つき `(NSYS + 1, NCOL, YEARS.n)` に派生の列を足したもの。"""
    T = totals(Cc)
    T[:, C.TUMITATE_GENZAI] = T[:, C.TUMITATE] / r.E.id_hhd[None]
    prev = np.zeros_like(T[:, C.TUMITATE])
    prev[:, 1:] = T[:, C.TUMITATE, :-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        T[:, C.TUMITATE_DOAI] = np.where(T[:, C.SHISHUTU] > 0., prev / T[:, C.SHISHUTU], 0.)
        fuka = (T[:, C.SHISHUTU] - T[:, C.UWANOSE] - T[:, C.KOKKO] - T[:, C.SHIEN_IN]
                - T[:, C.NOFUKIN]) / T[:, C.SOHOSHU]
        T[:, C.FUKA_RITU] = np.where(T[:, C.SOHOSHU_SOGAKU] > 0., fuka, 0.)
    for j, name in enumerate(SYS_OUT):
        T[j, C.HOKENRYORITU] = r.prem.rate["kou" if name == "tou" else name]
    return T


def kend_of(S, ks, ke):
    """調整最終年度を後ろから探す（港 `_kend`）。67 歳の率が前年より 1e-13 より大きくなった最初の年度。"""
    x67 = AGES.i(67)
    ie = YEARS.i(ke)
    dtemp = S[ie - 1, x67]
    for i in range(ie - 1, YEARS.i(ks), -1):
        if S[i - 1, x67] - dtemp > 1e-13:
            return YEARS.label(i)
        dtemp = S[i - 1, x67]
    return 0


def summary_table(r):
    """`03summary` の「経済前提等」の表（列名 → (YEARS.n,)）。モデル年金額は 2024年度だけ円に丸める。"""
    pol = r.inp.pol
    M = r.model
    Sh, St = r.sol.Sh, r.sol.St
    x67, x68 = AGES.i(67), AGES.i(68)
    i0 = YEARS.i(pol.get("shushi.model.mdlk"))
    E = r.E
    n = YEARS.n
    r1h = M.mhirei[:, 0] * Sh[:, x67]
    r1k = M.mkiso * St[:, x67]
    r2h = M.mhirei[:, 1] * Sh[:, x67]
    r2k = M.mkiso * St[:, x67]
    for a in (r1h, r1k, r2h, r2k):
        a[:i0] = 0.
        a[i0] = np.floor(abs(a[i0]) + 0.5) * np.sign(a[i0])
    r1, r2 = r1h + r1k, r2h + r2k
    kw0 = np.where(np.arange(n) >= i0, M.kw[:, 0], 0.)
    kw1 = np.where(np.arange(n) >= i0, M.kw[:, 1], 0.)
    with np.errstate(divide="ignore", invalid="ignore"):
        def pct(a, b):
            return np.where(b > 0., a / b * 100., 0.)
        out = {
            "物価": E.ci * 100., "賃金": E.h * 100., "運用利回り": E.ri * 100.,
            "比例改定率": (r.inp.krb[:, x67] - 1.) * 100., "比例既裁68歳": (r.inp.krb[:, x68] - 1.) * 100.,
            "基礎改定率": (r.inp.kra[:, x67] - 1.) * 100., "基礎既裁68歳": (r.inp.kra[:, x68] - 1.) * 100.,
            "モデル年金額": r1, "うち比例": r1h, "うち基礎": r1k, "可処分所得": kw0,
            "所得代替率": pct(r1, kw0), "所得代替率(比例)": pct(r1h, kw0), "所得代替率(基礎)": pct(r1k, kw0),
            "（参考）所得代替率(一元化前)": pct(r2, kw1),
            "比例カット67": Sh[:, x67], "比例カット68": Sh[:, x68], "基礎カット67": St[:, x67],
            "基礎カット68": St[:, x68], "mファイル": r.inp.scutrk1,
            "モデル年金額（物価割り戻し）": np.where(kw0 > 0, r1 / E.id_cid, 0.),
            "うち比例（物価割り戻し）": np.where(kw0 > 0, r1h / E.id_cid, 0.),
            "うち基礎（物価割り戻し）": np.where(kw0 > 0, r1k / E.id_cid, 0.),
            "可処分所得（物価割り戻し）": np.where(kw0 > 0, kw0 / E.id_cid, 0.),
        }
    return out


# ---------------------------------------------------------------- 書き手

def _econ_lines(r, ke, first_year=2005):
    E, krb, kra = r.E, r.inp.krb, r.inp.kra
    x67, x68 = AGES.i(67), AGES.i(68)
    yield TITLE_ECON + "\n"
    yield "年度,物価,賃金,運用利回り,比例改定率,比例既裁68歳,基礎改定率,基礎既裁68歳,\n"
    for y in range(first_year, ke + 1):
        i = YEARS.i(y)
        yield "%3d, %5.2f, %5.2f, %5.2f, %5.2f, %5.2f, %5.2f, %5.2f,\n" % (
            i, E.ci[i] * 100., E.h[i] * 100., E.ri[i] * 100.,
            (krb[i, x67] - 1.) * 100., (krb[i, x68] - 1.) * 100.,
            (kra[i, x67] - 1.) * 100., (kra[i, x68] - 1.) * 100.)
    yield "\n"


def _nin_lines(r, j, first_year, ke):
    """被保険者数・受給者数の表（`shus_nin_out`）。"""
    name = SYS_OUT[j]
    if name == "tou":
        ap = sum(r.inp.shus[s].ap for s in SYSTEMS)
        ap65 = sum(r.inp.shus[s].ap65 for s in SYSTEMS)
        t4 = sum(r.inp.shus[s].t4 for s in SYSTEMS)
        s2 = 3
    else:
        sh = r.inp.shus[name]
        ap, ap65, t4 = sh.ap, sh.ap65, sh.t4
        s2 = 3 if name == "kou" else 2
    head = ["年度", "被保険者", "老齢", "老在", "通老", "通在", "障害", "遺族", "被保険者・男", "被保険者・女",
            "65歳以上被保険者・男", "65歳以上被保険者・女"]
    for s, mark in zip(range(1, s2 + 1), "①②③"):
        head += [x + mark for x in ("老齢", "老在", "通老", "通在", "障害", "遺族")]
    yield ",".join(head) + ("\n" if s2 == 3 else ",\n")
    for y in range(first_year, ke + 1):
        i = YEARS.i(y)
        f = ["%3d" % i, "%14.8e" % ap[0, i]] + ["%14.8e" % t4[0, k, i] for k in range(1, 7)]
        f += ["%14.8e" % (ap[1, i] + ap[3, i]), "%14.8e" % ap[2, i],
              "%14.8e" % (ap65[1, i] + ap65[3, i]), "%14.8e" % ap65[2, i]]
        for s in range(1, s2 + 1):
            f += ["%14.8e" % t4[s, k, i] for k in range(1, 7)]
        yield ",".join(f) + ",\n"


def _shushi_lines(T, j, first_year, ke, title):
    yield "\n" + title + "\n"
    yield "年度," + ",".join(COLS_SHUSHI) + ",\n"
    for y in range(first_year, ke + 1):
        i = YEARS.i(y)
        yield "%3d," % i + ",".join(_E % (T[j, c, i] * _tanni(c)) for c in range(NCOL)) + ",\n"


def _kend_line(r):
    ks, ke = r.inp.ks, r.inp.ke
    x67 = AGES.i(67)
    out = "\n" + TITLE_KEND + ", "
    for S, label in ((r.sol.Sh, "厚年"), (r.sol.St, "国年")):
        kend = kend_of(S, ks, ke)
        if kend != 0 and kend != ke - 1:
            out += " %s, %3d, %s, " % (label, YEARS.i(kend), _E14 % S[YEARS.i(kend), x67])
        else:
            out += " %s, - , - , " % label
    return out.rstrip(", ") + "\n"


def write_shushi(r, directory, case, yobi="000", first_year=2015):
    """`01shushi.*_08{tou,kou,kok,ren,sig}.csv` の5本。戻り値は書いたパスの dict。"""
    T_b = shushi_table(r, r.Cc_before)
    T_a = shushi_table(r, r.Cc)
    ke = r.inp.ke
    paths = {}
    for j, name in enumerate(SYS_OUT):
        p = os.path.join(directory, "01shushi.%s-%s-%s-%s-1120-%se_08%s.csv" % ((case,) * 4 + (yobi, name)))
        with open(p, "w", encoding="utf-8") as fp:
            fp.write("#99-0000-0000\n%s, %s, %s\n%s, %s\n%s\n\n" % ((case,) * 6))
            fp.writelines(_econ_lines(r, ke))
            fp.writelines(_nin_lines(r, j, first_year, ke))
            fp.write("\n")
            fp.writelines(_shushi_lines(T_b, j, first_year, ke, TITLE_BEFORE))
            fp.write(_kend_line(r))
            fp.write("\n")
            fp.writelines(_shushi_lines(T_a, j, first_year, ke, TITLE_AFTER))
        paths[name] = p
    return paths


_SUMMARY_SHUSHI_COLS = [c for c in range(NCOL)
                        if not (c in (C.UWANOSE, C.KOKKO_KEIKA_TEIGAKU, C.KOKKO_KASAAGE, C.PART_HOKENRYO)
                                or C.DOKUJI_HIREI <= c <= C.DOKUJI_KAKYU
                                or (c >= C.IKUJI_HOSHU and c not in (C.HOKENRYORITU, C.TUMATUMI)))]


def _summary_shushi_lines(T, j, r, first_year, ke, ukyu):
    yield "年度,"
    yield ("収入計, 保険料, 運用収入, 国庫負担, うち基礎, うち経過的国庫, 支援入, 納付金,"
           "支出計,独自給付,基礎年金拠出金,福祉,支援出,収支差,"
           "積立金, 現在価値, 総報酬, 総報酬(育児等除く), 保険料率,妻積み,住宅融資（別掲）,,"
           "老齢相当,通老相当,障害,遺族\n")
    for y in range(first_year, ke + 1):
        i = YEARS.i(y)
        f = ["%3d" % i]
        for c in _SUMMARY_SHUSHI_COLS:
            if c == C.KOKKO_KEIKA_HIREI:
                v = T[j, C.KOKKO_KEIKA_HIREI, i] + T[j, C.KOKKO_KEIKA_TEIGAKU, i] + T[j, C.KOKKO_KASAAGE, i]
            else:
                v = T[j, c, i]
            v = v * 100. if c == C.HOKENRYORITU else v / 1e8
            f.append(_E14 % v)
        f.append(_E14 % (r.inp.jyutaku[i] / 1e8 if j <= 1 else 0.))
        f.append("")
        f += [_E14 % ukyu[j, k, i] for k in range(4)]
        yield ",".join(f) + ",\n"


def _ukyu(r):
    """受給者数の区分計（老齢相当・通老相当・障害・遺族）`[NSYS + 1, 4, YEARS.n]`。"""
    u = np.zeros((NSYS + 1, 4, YEARS.n))
    for s, name in enumerate(SYSTEMS, start=1):
        t4 = r.inp.shus[name].t4[0]
        u[s, 0] = t4[1] + t4[2]
        u[s, 1] = t4[3] + t4[4]
        u[s, 2] = t4[5]
        u[s, 3] = t4[6]
    u[0] = u[1:].sum(axis=0)
    return u


def write_summary(r, path, case, yobi="000", first_year=2015, econ_first_year=2005):
    """`03summary.*_08sum.csv`。"""
    ks, ke = r.inp.ks, r.inp.ke
    x67 = AGES.i(67)
    ie = YEARS.i(ke)
    S = summary_table(r)
    ukyu = _ukyu(r)
    T = shushi_table(r, r.Cc)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("%s, %s, %s\n%s, %s\n%s\n" % ((case,) * 6))
        fp.write("100, 予備:, %s, Cntlset:, 1, Seidn:, 0\n\n" % yobi)
        fp.write("Flg_Part,0,, Flg_Dmakuro,0\n\n")
        kh, kt = kend_of(r.sol.Sh, ks, ke), kend_of(r.sol.St, ks, ke)
        fp.write("終了年度：,厚年,%d,%s,国年,%d, %s\n\n" % (
            YEARS.i(kh) if kh else 0, _E14 % (1. - r.sol.Sh[ie, x67]),
            YEARS.i(kt) if kt else 0, _E14 % (1. - r.sol.St[ie, x67])))
        fp.write(TITLE_ECON + "\n")
        fp.write(",".join(SUMMARY_COLS) + "\n")
        keys = ("モデル年金額", "うち比例", "うち基礎", "可処分所得", "所得代替率", "所得代替率(比例)",
                "所得代替率(基礎)", "（参考）所得代替率(一元化前)")
        for y in range(econ_first_year, ke + 1):
            i = YEARS.i(y)
            f = ["%3d" % i] + [" %5.2f" % S[k][i] for k in ("物価", "賃金", "運用利回り")]
            f += [" " + _E14 % S[k][i] for k in ("比例改定率", "比例既裁68歳", "基礎改定率", "基礎既裁68歳")]
            f += [" " + _E14 % S[k][i] for k in keys]
            f += [" " + _E14 % S[k][i] for k in ("比例カット67", "比例カット68", "基礎カット67", "基礎カット68")]
            f += [" " + _E14 % S["mファイル"][i]]
            f += [_E14 % S[k][i] for k in ("モデル年金額（物価割り戻し）", "うち比例（物価割り戻し）",
                                          "うち基礎（物価割り戻し）", "可処分所得（物価割り戻し）")]
            fp.write(",".join(f) + ",\n")
        fp.write("\n\n,全厚年,,,,,旧厚年,,,,,国共,,,,,地共,,,,,私学,,,,,\n")
        fp.write("年度," + "被保険者,老齢相当,通老相当,障害,遺族," * (NSYS + 1) + "\n")
        ap = np.stack([sum(r.inp.shus[s].ap[0] for s in SYSTEMS)] + [r.inp.shus[s].ap[0] for s in SYSTEMS])
        for y in range(first_year, ke + 1):
            i = YEARS.i(y)
            f = ["%3d" % i]
            for j in range(NSYS + 1):
                f.append(_E14 % ap[j, i] + ", " + ", ".join(_E14 % ukyu[j, k, i] for k in range(4)))
            fp.write(",".join(f) + ",\n")
        fp.write("\n")
        for j, title in enumerate(("収支[全厚年１:tou]", "収支[旧厚年]", "収支[国共済]", "収支[地共済]", "収支[私学共済]")):
            fp.write("\n" + title + "\n\n")
            fp.writelines(_summary_shushi_lines(T, j, r, first_year, ke, ukyu))
            fp.write("\n\n")
    return path


def write_cut(S, path, first_year=2005):
    """`cuta`（国年）/ `cutb`（厚年）。2005〜2008年度は 1.0。"""
    xs = AGES.s(AGE_LO, AGE_HI)
    with open(path, "w", encoding="utf-8") as fp:
        for y in range(first_year, YEARS.last + 1):
            i = YEARS.i(y)
            row = S[i, xs] if y >= first_year + 4 else np.ones(AGE_HI - AGE_LO + 1)
            fp.write("%4d," % i + ",".join(_E14 % v for v in row) + ",\n")


def write_tokutyo(tok, path, ke, first_year=2005):
    xs = AGES.s(67, AGE_HI)
    with open(path, "w", encoding="utf-8") as fp:
        for y in range(first_year, ke + 1):
            i = YEARS.i(y)
            fp.write("%d," % i + ",".join("%.15f" % v for v in tok[i, xs]) + ",\n")


def to_port_csv(r, case, directory, yobi="000"):
    """港の配置で書く。戻り値 {名前: パス}。"""
    shushi = os.path.join(directory, "shushi")
    cutr = os.path.join(directory, "cutr")
    os.makedirs(shushi, exist_ok=True)
    os.makedirs(cutr, exist_ok=True)
    paths = write_shushi(r, shushi, case, yobi)
    paths["summary"] = write_summary(
        r, os.path.join(shushi, "03summary.%s-%s-%s-%s-1120-%s_08sum.csv" % ((case,) * 4 + (yobi,))), case, yobi)
    paths["cuta"] = os.path.join(cutr, "cuta-%s-%s-%s-%s-1120-%s.csv" % ((case,) * 4 + (yobi,)))
    paths["cutb"] = os.path.join(cutr, "cutb-%s-%s-%s-%s-1120-%s.csv" % ((case,) * 4 + (yobi,)))
    paths["tokutyo"] = os.path.join(cutr, "Tokutyo.%s-%s-%s-%s-1120_%s.csv" % ((case,) * 4 + (yobi,)))
    write_cut(r.sol.St, paths["cuta"])
    write_cut(r.sol.Sh, paths["cutb"])
    write_tokutyo(r.sol.slide.tokutyo, paths["tokutyo"], r.inp.ke)
    return paths


# ---------------------------------------------------------------- 読み手（比較用）

def _numeric_rows(L, start):
    rows = {}
    for l in L[start:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].lstrip("-").isdigit():
            if rows:
                break
            continue
        rows[int(f[0]) + YEARS.first] = np.array([float(x) for x in f[1:] if x != ""])
    return rows


def read_shushi(path):
    """`01shushi` → {ブロック名: {西暦: 値の配列}} と 調整最終年度（`kend`: {厚年, 国年}）。"""
    L = lines_of(path)
    out = {}
    for title in (TITLE_ECON, TITLE_BEFORE, TITLE_AFTER):
        hits = [i for i, l in enumerate(L) if l.strip() == title]
        if hits:
            out[title] = _numeric_rows(L, hits[0] + 2)
    kend = {}
    for l in L:
        if l.startswith(TITLE_KEND):
            f = [x.strip() for x in l.split(",")]
            for label in ("厚年", "国年"):
                j = f.index(label)
                kend[label] = (int(f[j + 1]) + YEARS.first if f[j + 1].isdigit() else None,
                               float(f[j + 2]) if f[j + 2] not in ("-", "") else None)
    out["kend"] = kend
    return out


def read_summary(path):
    """`03summary` → {"kend": {厚年: (年度, 最終カット率), 国年: …}, "table": {西暦: {列名: 値}}}。
    列名は `SUMMARY_COLS`（所得代替率の「うち比例」「うち基礎」は `所得代替率(比例)` `所得代替率(基礎)`）。"""
    L = lines_of(path)
    out = {"kend": {}}
    for l in L:
        if l.startswith("終了年度"):
            f = [x.strip() for x in l.split(",")]
            out["kend"]["厚年"] = (int(f[2]) + YEARS.first, float(f[3]))
            out["kend"]["国年"] = (int(f[5]) + YEARS.first, float(f[6]))
            break
    hi = [i for i, l in enumerate(L) if l.startswith("年度,物価")][0]
    cols = list(SUMMARY_COLS[1:])
    cols[12], cols[13] = "所得代替率(比例)", "所得代替率(基礎)"
    table = {}
    for y, v in _numeric_rows(L, hi + 1).items():
        table[y] = dict(zip(cols, v))
    out["table"] = table
    return out


def read_cut(path):
    """`cuta/cutb` → {西暦: (53,)}。"""
    from ...io_port import read_year_rows
    return read_year_rows(path, YEARS.first)
