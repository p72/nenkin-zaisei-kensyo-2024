# -*- coding: utf-8 -*-
"""マクロ経済スライドの終了年度の解法（移植版 `tyousei.c` `Atamawari_cut.c` 相当）
================================================================================
国民年金の積立金が `t_nendo`（2120）年度に支出の `t_doai`（1）年分を残す、
いちばん早い調整終了年度 c を探す。

    積立金[y] = 積立金[y−1] · r[y] + (収入[y] − 支出[y]) · √r[y]          （§7.1）
    収入 = 保険料 ＋ 付加保険料 ＋ 妻積（国年）＋ 住宅融資債権 ＋ こども納付金
    支出（実質）= 拠出金 − 拠出金の国庫負担 ＋ 死亡一時金（納付分 ＋ 付加分×3/4）
                 ＋ 寡婦（新法 ＋ 旧法納付）＋ 付加年金 × 3/4 ＋ 業務勘定への繰入
    条件      積立金[2119] ≥ 支出[2120] × t_doai
              支出 = 拠出金 ＋ 特別国庫 ＋ 死亡一時金 ＋ 寡婦 ＋ 付加年金 ＋ 繰入

解法（港のまま）
  1. c = 2005 から1年ずつ進めて、条件を満たす最初の年度で止める（2024年度より前では止めない）
  2. その年度の中を二分法で 128 回刻む（終了年度が 2024 より後のとき）。
     `cut_ruiseki[c]` を前年度ぶんと当年度ぶんの間で半分にしていく
  3. 改定率を調整後（`kaiteiritu_cut`）に差し替える

候補 c ごとの試算（`atamawari_cut`）は制度計・新旧計・種類計・拠出だけの1本で足りる。
給付費の直積は動かないので、`Tag` から計を1回だけ取り、候補ごとに調整率を掛ける。

港: kiso_nenkin/tyousei.py:tyousei
港: kiso_nenkin/atamawari_cut.py:Atamawari_cut
仕様: §8.1〜8.4
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS, AGES
from .inputs import NA, AGE_LO, AGE_HI, KIHON, KAKYU
from .kyufu import KYO, SHIHARAIOKURE

__all__ = ["CutBase", "cut_base", "atamawari_cut", "fund_path", "solve", "Solution"]


@dataclass
class CutBase:
    """調整前の年度末の給付費の計（制度・新旧・種類の計、拠出）。(YEARS.n, NA, 2 形態)"""
    kyufu_nm: np.ndarray
    kyufu_P: np.ndarray
    kokko_nm: np.ndarray
    kokko_P: np.ndarray
    tokubetu_nm: np.ndarray            # 特別国庫（種類の計）
    tokubetu_P: np.ndarray


def cut_base(kyufu):
    """`kyufu.Kyufu`（調整率 1 で作ったもの）から計を取る。"""
    def b(T):
        return T.K[:, :, :, :, :, KYO, :].sum(axis=(0, 3, 4))
    return CutBase(b(kyufu.nm), b(kyufu.P),
                   kyufu.kokko_nm.sum(axis=(0, 3, 4)), kyufu.kokko_P.sum(axis=(0, 3, 4)),
                   kyufu.nm.tokubetu.sum(axis=2), kyufu.P.tokubetu.sum(axis=2))


def _nendokan_sum(nm, P, kaiteiritu_cut, i0, x67, sho=SHIHARAIOKURE):
    """年度間値の年齢計（64〜115歳・両形態）(YEARS.n,)。`nm/P[YEARS, NA, 2]`。"""
    out = np.zeros(YEARS.n)
    ages = np.arange(AGE_LO, AGE_HI + 1)
    kt = np.empty((YEARS.n, NA - 1, 2))
    kt[:, :, KAKYU] = kaiteiritu_cut[:, x67][:, None]
    kt[:, :, KIHON] = kaiteiritu_cut[:, AGES.i(ages[1:])]
    kt[:, :67 - AGE_LO, KIHON] = kaiteiritu_cut[:, x67][:, None]
    zennen = P[i0 - 1:-1, :-1]                               # (Y', NA-1, 2)
    tounen = nm[i0:, 1:].copy()
    tounen[:, 0] += nm[i0:, 0]
    v = zennen * (sho + 6. * kt[i0:]) / 12. + tounen * (6. - sho) / 12.
    out[i0:] = v.sum(axis=(1, 2))
    return out


def atamawari_cut(base, cr_c, kaiteiritu_cut, santei, D, i0, x67):
    """調整終了年度の候補1つの試算。`cr_c[YEARS.n, NA]` = `cut_ruiseki[c]`。
    戻り値 (支出, 支出（実質）, 拠出金_cut, 拠出金国庫_cut, 特別国庫_cut, 寡婦_cut)。"""
    ck = cr_c[:, :, None].copy()
    ck = np.repeat(ck, 2, axis=2)
    ck[:, :, KAKYU] = cr_c[:, 0:1]                           # 加給は63歳の率
    ky = _nendokan_sum(base.kyufu_nm * ck, base.kyufu_P * ck, kaiteiritu_cut, i0, x67)
    kk = _nendokan_sum(base.kokko_nm * ck, base.kokko_P * ck, kaiteiritu_cut, i0, x67)
    tk = _nendokan_sum(base.tokubetu_nm * ck, base.tokubetu_P * ck, kaiteiritu_cut, i0, x67)
    with np.errstate(divide="ignore", invalid="ignore"):      # 2020年度は 0/0
        share = santei.total[0] / santei.all                 # 国年の頭割り
    share = np.where(np.isfinite(share), share, 0.)
    kyo_cut = ky * share
    kokko_cut = kk * share
    # 寡婦年金は64歳の調整率、死亡一時金は調整しない
    kafu_nm = D.kafu_nm * cr_c[:, 1:2]
    kafu = np.zeros_like(kafu_nm)
    kt = kaiteiritu_cut[i0:, x67][:, None]
    kafu[i0:] = kafu_nm[i0 - 1:-1] * (SHIHARAIOKURE + kt * 6.) / 12. + kafu_nm[i0:] * 4. / 12.
    ichi = D.ichijikin                                       # (YEARS, 2) 納付・付加
    kiso_cut = kyo_cut + tk
    shishutu = kiso_cut + ichi.sum(axis=1) + kafu.sum(axis=1) + D.fuka_sum + D.fukushi
    jisshitu = ((kyo_cut - kokko_cut) + ichi[:, 0] + ichi[:, 1] * 3. / 4.
                + kafu[:, 0] + kafu[:, 1] + D.fuka_sum * 3. / 4. + D.fukushi)
    return shishutu, jisshitu, kyo_cut, kokko_cut, tk, kafu


def fund_path(tumitate0, i_start, income, outgo, interest):
    """積立金の漸化式。`tumitate0` は `i_start − 1` の年度末の値。港: kiso_nenkin/tyousei.py:tyousei"""
    out = np.zeros(YEARS.n)
    out[i_start - 1] = tumitate0
    prev = tumitate0
    for i in range(i_start, YEARS.n):
        r = interest[i]
        prev = prev * r + (income[i] - outgo[i]) * np.sqrt(r)
        out[i] = prev
    return out


@dataclass
class Solution:
    s_c_nendo: int                     # 調整終了年度
    cut_ritu: np.ndarray               # (YEARS.n, NA) 最終的な累積調整率（= cut_ruiseki[c]）
    kaiteiritu_cut: np.ndarray         # (YEARS.n, AGES.n) 調整後の改定率
    saisyu_cut: float                  # 終了年度の63歳の累積調整率
    daitai: float                      # 代替率換算（%）
    tumitate: np.ndarray               # 調整後の積立金
    shishutu: np.ndarray
    margin: float                      # 積立金[t−1] − 支出[t] × 度合（連続量の余裕）
    n_scan: int
    ok: bool                           # 期間内に調整できたか


def solve(pol, E, base, santei, D, income, tumitate0, first_year=2021):
    """終了年度を解く。`E`: `KisoEcon`、`income[YEARS.n]`: 保険料等の収入（拠出金の国庫を除く）。"""
    t_nendo = pol.get("kiso.years.t_nendo")
    t_doai = pol.get("kiso.years.t_doai")
    c_nendo = pol.get("kiso.years.c_nendo")
    kaishi = pol.get("kiso.years.kaishi1")
    min_stop = pol.get("kiso.years.kugiri_stop")            # これより前では止めない（2024）
    n_bisect = pol.get("kiso.macro.bisection_iters")
    x67 = AGES.i(pol.get("kiso.ages.under_67"))
    i0 = YEARS.i(first_year)
    ik = YEARS.i(kaishi)
    it = YEARS.i(t_nendo)
    xs = AGES.s(67, AGE_HI)

    kc = E.kaiteiritu.copy()
    cr = E.cut_ruiseki.copy()

    def trial(c):
        sh, js, *_ = atamawari_cut(base, cr[YEARS.i(c)], kc, santei, D, i0, x67)
        tm = fund_path(tumitate0, ik, income, js, E.interest_rate)
        return sh, js, tm

    ok = True
    n = 0
    c = t_nendo + 1
    for cand in range(c_nendo + 1, t_nendo + 1):
        ci = YEARS.i(cand)
        kc[ci, xs] = E.kaiteiritu[ci, xs] / E.pre_cut[ci, xs]
        sh, js, tm = trial(cand)
        n += 1
        if tm[it - 1] < sh[it] * t_doai:
            if cand >= t_nendo:
                ok = False
                c = cand
                break
        elif cand >= min_stop:
            c = cand
            break
    s_c = c
    si = YEARS.i(s_c)
    if s_c > min_stop and si < YEARS.n:
        a = cr[si - 1, ik:].copy()
        b = cr[si, ik:].copy()
        for _ in range(n_bisect):
            cr[si, ik:] = (a + b) / 2.
            kc[si, xs] = E.kaiteiritu[si, xs] * cr[si, si, 67 - AGE_LO:] / cr[si - 1, si, 67 - AGE_LO:]
            sh, js, tm = trial(s_c)
            n += 1
            if tm[it - 1] < sh[it] * t_doai:
                a = cr[si, ik:].copy()
            else:
                b = cr[si, ik:].copy()
    sh, js, tm = trial(s_c)
    saisyu = cr[si, si, 0]
    act = {int(k): v for k, v in pol.get("kiso.macro.actuals").items()}
    model_pension = pol.get("kiso.model.pension_2024") / (act[2023]["pre_cut_div"] * act[2024]["pre_cut_div"])
    daitai = model_pension * saisyu / pol.get("kiso.model.wage_2024") * 100.
    return Solution(s_c, cr[si].copy(), kc, saisyu, daitai, tm, sh, tm[it - 1] - sh[it] * t_doai, n, ok)
