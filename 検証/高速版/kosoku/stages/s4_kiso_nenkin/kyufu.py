# -*- coding: utf-8 -*-
"""基礎年金給付費の直積と拠出金の頭割り（移植版 `Atamawari.c` 相当）
======================================================================
受給者の年金額（`inputs.Jukyu`）を「制度 × 年齢 × 新旧 × 種類 × 対象 × 形態」の
直積 `K[s, y, x, sk, kb, ts, kt]` に scatter し、周辺和は要るときに `sum` で出す
（港は 2^6 通りの周辺和を毎年度作って持ち回す。高速版は持たない）。

    年度末値   K_nm[y, x]   受給者の年金額を特別国庫の割合で拠出／特別に振り分けたもの
    翌年度割   K_P[y, x]    同じものを翌年度の割合で（被保険者数の翌年度割り用）
    調整       K ×= 調整率[y, x]（加給は63歳の率）
    国庫       Kokko = K[拠出] × 国庫負担割合[y]
    年度間値   K[y, x] = K_P[y−1, x−1] · (2 + 6·改定率) / 12 + K_nm[y, x] · 4 / 12
               （64歳は当年度末の63歳も足す。改定率は67歳以下と加給が67歳の率）
    単価       Tanka[y, x, kt] = Σ_{s, sk, kb} K[拠出] / 算定対象者(全制度)[y] / 12
    拠出金     Kyoshutukin[s, y, x, kt] = 算定対象者[s, y] × Tanka × 12

港: kiso_nenkin/atamawari.py:Atamawari
仕様: §6.1、§6.2、§7.3
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS, AGES
from .inputs import (NS, NA, AGE_LO, AGE_HI, KIHON, KAKYU, RN, RO, SN, SO, FK)

__all__ = ["Tag", "Kyufu", "Kyoshutu", "build_nendomatu", "apply_cut", "kokko", "nendokan_tag",
           "nendokan_kokko", "tanka_kyoshutukin", "build_kyufu", "kokko_wariai_table",
           "TOK", "SHIHARAIOKURE", "with_totals", "NEW", "OLD", "ROREI", "SHOGAI", "IZOKU",
           "KYO", "TOKU"]

SHIHARAIOKURE = 2                     # 支払遅れ（月）。港: kiso_nenkin/atamawari.py:99
NEW, OLD = 0, 1                       # 新旧
ROREI, SHOGAI, IZOKU = 0, 1, 2        # 種類
KYO, TOKU = 0, 1                      # 対象（拠出・特別）


class _Idx:
    def __init__(self, *names):
        for i, n in enumerate(names):
            setattr(self, n, i)
        self.n = len(names)


TOK = _Idx("menjo", "kasaage", "kasamenjo", "shitasasae", "gonen", "hatachimae")   # 特別国庫の種類


@dataclass
class Tag:
    """給付費の直積。`K[NS, YEARS.n, NA, 2 新旧, 3 種類, 2 対象, 2 形態]`、
    `tokubetu[YEARS.n, NA, TOK.n, 2 形態]`。"""
    K: np.ndarray
    tokubetu: np.ndarray

    @classmethod
    def zeros(cls):
        return cls(np.zeros((NS, YEARS.n, NA, 2, 3, 2, 2)), np.zeros((YEARS.n, NA, TOK.n, 2)))

    def copy(self):
        return Tag(self.K.copy(), self.tokubetu.copy())


@dataclass
class Kyufu:
    """年度末値（`nm`）・翌年度割（`P`）・年度間値（`k`）と、それぞれの国庫負担分。"""
    nm: Tag
    P: Tag
    k: Tag = None
    kokko_nm: np.ndarray = None       # (NS, YEARS.n, NA, 2, 3, 2)  対象は拠出だけ
    kokko_P: np.ndarray = None
    kokko_k: np.ndarray = None


def _tkw_table(pol):
    """特別国庫負担の割合 (YEARS.n, TOK.n)。20歳前だけ 2009年度で変わる。"""
    t = np.zeros((YEARS.n, TOK.n))
    p = "kiso.tokubetu_kokko."
    t[:, TOK.menjo] = pol.get(p + "menjo")
    t[:, TOK.kasaage] = pol.get(p + "kasaage")
    t[:, TOK.kasamenjo] = pol.get(p + "kasamenjo")
    t[:, TOK.shitasasae] = pol.get(p + "shitasasae")
    t[:, TOK.gonen] = pol.get(p + "gonen")
    hik = YEARS.i(pol.get("kiso.years.kokko_hikiage"))
    t[:hik, TOK.hatachimae] = pol.get(p + "hatachimae_before")
    t[hik:, TOK.hatachimae] = pol.get(p + "hatachimae_after")
    return t


def kokko_wariai_table(pol):
    """国庫負担割合 (YEARS.n,)。2009年度から 1/2。"""
    w = np.full(YEARS.n, pol.get("kiso.kokko.before"))
    w[YEARS.i(pol.get("kiso.years.kokko_hikiage")):] = pol.get("kiso.kokko.after")
    return w


def build_nendomatu(pol, J, shift=0):
    """受給者の年金額 → 年度末の給付費の直積。`shift` 1 なら翌年度の割合（最終年度は当年度）。"""
    tkw_all = _tkw_table(pol)
    if shift:
        tkw_all = np.concatenate([tkw_all[1:], tkw_all[-1:]], axis=0)
    tk = tkw_all[None, :, None, :]                        # (1, YEARS, 1, TOK.n) 制度・年齢へ放送
    T = Tag.zeros()
    K, TK = T.K, T.tokubetu
    rn, ro, sg, so, iz, zo, fk = (J.rorei_new, J.rorei_old, J.shogai_new, J.shogai_old,
                                  J.izoku_new, J.izoku_old, J.furikae)
    w = lambda name: tk[..., getattr(TOK, name)]          # noqa: E731  (1, YEARS, 1)

    # ---- 国年（s = 0） ----
    s = 0
    K[s, :, :, NEW, ROREI, KYO, KIHON] += rn[s, ..., RN.noufu]
    K[s, :, :, OLD, ROREI, KYO, KIHON] += (ro[s, ..., RO.noufu]
                                           + ro[s, ..., RO.kasanoufu] * (1. - w("kasaage")[0])
                                           + ro[s, ..., RO.gonen] * (1. - w("gonen")[0]))
    K[s, :, :, NEW, ROREI, TOKU, KIHON] += rn[s, ..., RN.menjo_zenhan] + rn[s, ..., RN.menjo_kouhan]
    K[s, :, :, OLD, ROREI, TOKU, KIHON] += (ro[s, ..., RO.menjo] * w("menjo")[0]
                                            + ro[s, ..., RO.kasanoufu] * w("kasaage")[0]
                                            + ro[s, ..., RO.kasamenjo] * w("kasamenjo")[0]
                                            + ro[s, ..., RO.rofuku_shitasasae] * w("shitasasae")[0]
                                            + ro[s, ..., RO.gonen] * w("gonen")[0])
    for k in (KIHON, KAKYU):
        K[s, :, :, NEW, SHOGAI, KYO, k] += (sg[s, ..., SN.ippan, k]
                                            + sg[s, ..., SN.hatachimae, k] * (1. - w("hatachimae")[0]))
        K[s, :, :, OLD, SHOGAI, KYO, k] += so[s, ..., k, SO.noufu]
        K[s, :, :, NEW, SHOGAI, TOKU, k] += sg[s, ..., SN.hatachimae, k] * w("hatachimae")[0]
        K[s, :, :, OLD, SHOGAI, TOKU, k] += so[s, ..., k, SO.menjo] * w("menjo")[0]
        K[s, :, :, NEW, IZOKU, KYO, k] += iz[s, ..., k]
        K[s, :, :, OLD, IZOKU, KYO, k] += zo[s, ..., k, SO.noufu]
        K[s, :, :, OLD, IZOKU, TOKU, k] += zo[s, ..., k, SO.menjo] * w("menjo")[0]

    # ---- 被用者（s = 1〜4） ----
    S = slice(1, NS)
    K[S, :, :, NEW, ROREI, KYO, KIHON] += rn[S, ..., RN.noufu]
    K[S, :, :, OLD, ROREI, KYO, KIHON] += (ro[S, ..., RO.noufu] + ro[S, ..., RO.kasanoufu]
                                           + ro[S, ..., RO.gonen])
    K[S, :, :, OLD, ROREI, KYO, KAKYU] += ro[S, ..., RO.kakyu_noufu]
    for k in (KIHON, KAKYU):
        K[S, :, :, NEW, SHOGAI, KYO, k] += sg[S, ..., SN.ippan, k] + sg[S, ..., SN.hatachimae, k]
        K[S, :, :, OLD, SHOGAI, KYO, k] += so[S, ..., k, SO.noufu]
        K[S, :, :, NEW, IZOKU, KYO, k] += iz[S, ..., k]
        K[S, :, :, OLD, IZOKU, KYO, k] += zo[S, ..., k, SO.noufu]

    # ---- 振替加算は全制度ぶんを国年に寄せる ----
    K[0, :, :, NEW, ROREI, KYO, KIHON] += fk[..., FK.rorei].sum(axis=0)
    K[0, :, :, NEW, SHOGAI, KYO, KIHON] += fk[..., FK.shogai].sum(axis=0)

    # ---- 特別国庫負担の内訳（国年だけ） ----
    TK[:, :, TOK.menjo, KIHON] += (rn[0, ..., RN.menjo_zenhan] + rn[0, ..., RN.menjo_kouhan]
                                   + ro[0, ..., RO.menjo] * w("menjo")[0])
    for name, col in (("kasaage", RO.kasanoufu), ("kasamenjo", RO.kasamenjo),
                      ("shitasasae", RO.rofuku_shitasasae), ("gonen", RO.gonen)):
        TK[:, :, getattr(TOK, name), KIHON] += ro[0, ..., col] * w(name)[0]
    for k in (KIHON, KAKYU):
        TK[:, :, TOK.hatachimae, k] += sg[0, ..., SN.hatachimae, k] * w("hatachimae")[0]
        TK[:, :, TOK.menjo, k] += (so[0, ..., k, SO.menjo] + zo[0, ..., k, SO.menjo]) * w("menjo")[0]
    return T


def apply_cut(T, cut):
    """調整率 `cut[YEARS.n, NA]` を掛ける（加給は63歳の率）。その場で書き換える。"""
    T.K[..., KIHON] *= cut[None, :, :, None, None, None]
    T.K[..., KAKYU] *= cut[None, :, 0:1, None, None, None]
    T.tokubetu[..., KIHON] *= cut[:, :, None]
    T.tokubetu[..., KAKYU] *= cut[:, 0:1, None]
    return T


def kokko(T, kokko_wariai):
    """国庫負担分 (NS, YEARS.n, NA, 2, 3, 2) = 拠出の給付費 × 国庫負担割合[y]。"""
    return T.K[:, :, :, :, :, KYO, :] * kokko_wariai[None, :, None, None, None, None]


def _kaitei_matrix(kaiteiritu, yi):
    """改定率 (NA, 2 形態)。67歳以下と加給は67歳の率、68歳以上の基本は年齢別。"""
    m = np.empty((NA, 2))
    m[:, KAKYU] = kaiteiritu[yi, AGES.i(67)]
    m[:, KIHON] = kaiteiritu[yi, AGES.s(AGE_LO, AGE_HI)]
    m[:67 - AGE_LO + 1, KIHON] = kaiteiritu[yi, AGES.i(67)]
    return m


def _nendokan_arr(nm, P, kaiteiritu, first_year, y_axis, sho=SHIHARAIOKURE):
    """年度末値2つ → 年度間値。`nm[..., y, x, ..., kt]` で年度が軸 `y_axis`、年齢がその次、
    形態が最後。戻り値は同じ形（63歳と `first_year` より前は 0）。"""
    out = np.zeros_like(nm)
    i0 = YEARS.i(first_year)
    nd = nm.ndim
    # 軸を (年度, 年齢, …, 形態) の順に見るための移動
    src_nm = np.moveaxis(nm, (y_axis, y_axis + 1), (0, 1))
    src_P = np.moveaxis(P, (y_axis, y_axis + 1), (0, 1))
    dst = np.moveaxis(out, (y_axis, y_axis + 1), (0, 1))
    for yi in range(i0, YEARS.n):
        km = _kaitei_matrix(kaiteiritu, yi)                       # (NA, 2)
        shape = (NA,) + (1,) * (nd - 3) + (2,)
        km = km.reshape(shape)[1:]
        zennen = src_P[yi - 1, :-1]                               # x−1 = 63 … 114
        tounen = src_nm[yi, 1:].copy()                            # 64 … 115
        tounen[0] += src_nm[yi, 0]                                # 64歳は63歳も足す
        dst[yi, 1:] = zennen * (sho + 6. * km) / 12. + tounen * (6. - sho) / 12.
    return out


def nendokan_tag(nm, P, kaiteiritu, first_year):
    """`Tag` の年度間値。"""
    return Tag(_nendokan_arr(nm.K, P.K, kaiteiritu, first_year, 1),
               _nendokan_arr(nm.tokubetu, P.tokubetu, kaiteiritu, first_year, 0))


def nendokan_kokko(nm, P, kaiteiritu, first_year):
    return _nendokan_arr(nm, P, kaiteiritu, first_year, 1)


def with_totals(a, age_axis):
    """年齢の軸に「計」（先頭）を、形態の軸（最後）に「計」（先頭）を足して港の並びにする。
    (…, NA, …, 2) → (…, NA+1, …, 3)。年齢の計は 64〜115歳なら呼び手が絞る。"""
    a = np.concatenate([a.sum(axis=age_axis, keepdims=True), a], axis=age_axis)
    a = np.concatenate([a.sum(axis=-1, keepdims=True), a], axis=-1)
    return a


@dataclass
class Kyoshutu:
    """単価と拠出金（港の並び: 年齢 0 = 計、1〜53 = 63〜115歳。形態 0 = 計）。"""
    tanka: np.ndarray                  # (YEARS.n, NA+1, 3) 年度間値（年齢計は 64〜115）
    tanka_kokko: np.ndarray
    kyoshutukin: np.ndarray            # (NS, YEARS.n, NA+1, 3)
    kyoshutukin_kokko: np.ndarray
    tanka_nm: np.ndarray               # 年度末値（63〜115）
    tanka_kokko_nm: np.ndarray
    tanka_P: np.ndarray
    tanka_kokko_P: np.ndarray
    kyoshutukin_nm: np.ndarray
    kyoshutukin_kokko_nm: np.ndarray
    kyoshutukin_P: np.ndarray
    kyoshutukin_kokko_P: np.ndarray


def _safe_div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0., a / np.where(b > 0., b, 1.), 0.)


def tanka_kyoshutukin(kyufu, santei, first_year, last_year_kokko_P_from_nm=True):
    """単価と拠出金。港: kiso_nenkin/atamawari.py:Atamawari（`_tanka_kyoshutukin`）

    `last_year_kokko_P_from_nm`: 最終年度の翌年度割の国庫単価は港が `_P` でない方を読む
    （原本の癖。E群として据え置き）。
    """
    st_all = santei.all                                     # (YEARS,)
    st_sys = santei.total                                   # (NS, YEARS)
    st_next = np.concatenate([st_all[1:], st_all[-1:]])
    st_sys_next = np.concatenate([st_sys[:, 1:], st_sys[:, -1:]], axis=1)

    def base(T):                                            # 拠出の給付費、制度・新旧・種類の計 (YEARS, NA, 2)
        return T.K[:, :, :, :, :, KYO, :].sum(axis=(0, 3, 4))

    def base_kokko(Kk):
        return Kk.sum(axis=(0, 3, 4))

    i0 = YEARS.i(first_year)
    # ---- 年度間値（64〜115歳） ----
    bk, bkk = base(kyufu.k), base_kokko(kyufu.kokko_k)
    tanka = _safe_div(bk, st_all[:, None, None]) / 12.
    tanka_kokko = _safe_div(bkk, st_all[:, None, None]) / 12.
    tanka[:i0] = 0.
    tanka_kokko[:i0] = 0.
    tanka[:, 0] = 0.                                        # 63歳の年度間値は無い
    tanka_kokko[:, 0] = 0.
    kyo = st_sys[:, :, None, None] * tanka[None] * 12.
    kyo_kokko = st_sys[:, :, None, None] * tanka_kokko[None] * 12.

    # ---- 年度末値（63〜115歳）と翌年度割 ----
    bnm, bP = base(kyufu.nm), base(kyufu.P)
    bknm, bkP = base_kokko(kyufu.kokko_nm), base_kokko(kyufu.kokko_P)
    tanka_nm = _safe_div(bnm, st_all[:, None, None]) / 12.
    tanka_kokko_nm = _safe_div(bknm, st_all[:, None, None]) / 12.
    tanka_P = _safe_div(bP, st_next[:, None, None]) / 12.
    tanka_kokko_P = _safe_div(bkP, st_next[:, None, None]) / 12.
    if last_year_kokko_P_from_nm:
        tanka_kokko_P[-1] = _safe_div(bknm[-1], st_all[-1]) / 12.
    for a in (tanka_nm, tanka_kokko_nm, tanka_P, tanka_kokko_P):
        a[:i0] = 0.
    kyo_nm = st_sys[:, :, None, None] * tanka_nm[None] * 12.
    kyo_kokko_nm = st_sys[:, :, None, None] * tanka_kokko_nm[None] * 12.
    kyo_P = st_sys_next[:, :, None, None] * tanka_P[None] * 12.
    kyo_kokko_P = st_sys_next[:, :, None, None] * tanka_kokko_P[None] * 12.

    return Kyoshutu(with_totals(tanka, 1), with_totals(tanka_kokko, 1),
                    with_totals(kyo, 2), with_totals(kyo_kokko, 2),
                    with_totals(tanka_nm, 1), with_totals(tanka_kokko_nm, 1),
                    with_totals(tanka_P, 1), with_totals(tanka_kokko_P, 1),
                    with_totals(kyo_nm, 2), with_totals(kyo_kokko_nm, 2),
                    with_totals(kyo_P, 2), with_totals(kyo_kokko_P, 2))


def build_kyufu(pol, J, cut, kaiteiritu, first_year):
    """受給者の年金額 → 年度末・翌年度割・年度間の給付費と国庫負担分（調整率 `cut` を掛けて）。"""
    nm = apply_cut(build_nendomatu(pol, J, 0), cut)
    P = apply_cut(build_nendomatu(pol, J, 1), cut)
    kw = kokko_wariai_table(pol)
    kk_nm, kk_P = kokko(nm, kw), kokko(P, kw)
    k = nendokan_tag(nm, P, kaiteiritu, first_year)
    kk_k = nendokan_kokko(kk_nm, kk_P, kaiteiritu, first_year)
    return Kyufu(nm, P, k, kk_nm, kk_P, kk_k)
