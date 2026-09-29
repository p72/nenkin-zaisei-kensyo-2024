# -*- coding: utf-8 -*-
"""被保険者・待期者の1年の遷移（§4.2）
=======================================
状態は年齢 × 加入期間 × 欄（`layouts.HIHOKENSHA` の21スロット、スロット0 が人数、
残りは**1人あたり**の期間・納付月数・免除月数・付加）。年齢は AGES の軸
（20〜70歳だけ使う）、加入期間は 0〜50年。

1年の操作（移植版 `siml.c:100-520` を (年齢, 期間) の両軸でまとめたもの）

    ① 残存   H̃[x,t] = H[y−1][x−1,t−1] · (1 − 脱退力[y,x])     （t = 50 は吸収: [x−1,50] も足す）
              T̃[x,t] = T[y−1][x−1,t]   · (1 − 待期者の失権率[y,x])
    ② 外枠   Σ_t H̃[x,t] > 外枠[y,x] なら比例で縮める
    ③ 再加入 R = min((外枠 − Σ H̃) · 再加入率, Σ T̃)。**再加入率は入力**（既定 0。台帳 D6）
    ④ 新規   N[x] = 外枠[y,x] − Σ_t (H̃ + R)
    ⑤ 確定   H[y][x,t] = H̃ + R、H[y][x,0] = N + R[x,0]
              脱退者 D = H[y−1][x−1,t−1] − H̃、うち死亡 M = H[y−1][x−1,t−1] · 死亡力
              T[y][x,t] = T̃ + (D − M)
    ⑥ 属性   人数加重平均。流入分は年度の半分だけ保険料を納める（× 0.5）

20歳のとき前年の「19歳」を読まず 0 とする（台帳 B10。原本は配列の外 = 70歳を読むが、70歳は全年度 0 なので
結果は原本と同じ。切り替えは置かない）。

港: nat/siml.py:siml
仕様: §4.2
"""
from dataclasses import dataclass

import numpy as np

from ...algebra import average_by_ninzu, scalar_split
from ...axis import AGES
from .layouts import HIHOKENSHA, MENJO_DANKAI

__all__ = ["HihoState", "Flows", "transition_year", "noufu_jokyo", "kokko_frac",
           "AGE_MIN", "AGE_MAX", "KIKAN_MAX", "K"]

AGE_MIN, AGE_MAX = 20, 70       # 被保険者の年齢（港: MIN_HIHO_NENREI / MAX_HIHO_NENREI）
KIKAN_MAX = 50                  # 加入期間の上限（港: MAX_HIHO_KIKAN）
K = KIKAN_MAX + 1
L = HIHOKENSHA
_S = L.n
I_NINZU = 0
I_KIKAN = L.i("kikan")
I_NOUFU = L.i("noufu")
I_GAKUSEI, I_WAKAMONO, I_FUKA = L.i("gakusei"), L.i("wakamono"), L.i("fuka")
_M_OLD = tuple("menjo[%d][1]" % d for d in range(MENJO_DANKAI))
_M_NEW = tuple("menjo[%d][2]" % d for d in range(MENJO_DANKAI))
_M_SUM = tuple("menjo[%d][0]" % d for d in range(MENJO_DANKAI))
A = slice(AGES.i(AGE_MIN), AGES.i(AGE_MAX) + 1)     # 年齢 20〜70 の51本


@dataclass
class HihoState:
    """ある年度末の被保険者 `H` と待期者 `T`。形は (AGES.n, K, 21)。"""
    H: np.ndarray
    T: np.ndarray

    @classmethod
    def zeros(cls):
        return cls(np.zeros((AGES.n, K, _S)), np.zeros((AGES.n, K, _S)))


@dataclass
class Flows:
    """遷移で出た流れ。給付の新規発生が読む。形は (AGES.n, K[, 21])。"""
    hiho_shibou: np.ndarray      # 被保険者の死亡（人数 ＋ 1人あたりの属性）
    taiki_shibou: np.ndarray     # 待期者の死亡（同）
    hasseisha_shogai: np.ndarray  # 障害の発生者数（前年度の被保険者 × 発生力）
    dattaisha_seizon: np.ndarray  # 生存脱退者数
    shinkikanyu: np.ndarray       # 新規加入者数 (AGES.n,)


def kokko_frac(pol, year):
    """国庫負担 1/2 の時代の月数割合（`scalar_2` の按分）。港: nat/str_op.py:scalar_2"""
    t_nendo = pol.get("kokunen.years.tokutei_nendo")
    t_tuki = pol.get("kokunen.years.tokutei_tuki")
    if year < t_nendo:
        return 0.
    if year == t_nendo:
        return (16 - t_tuki) / 12.
    return 1.


def noufu_jokyo(noufuritu_row, noufuritu_fuka_row):
    """当年度の納付状況（年齢ごとの「1年ぶんの期間の内訳」）。形 (AGES.n, 21)。

    `noufuritu_row[x, kubun]`: 納付区分 0〜10 の割合（港: `Noufuritu[shubetu][y]`）。
    港: nat/siml.py:siml（`Noufu_Jokyo` の組み立て）
    """
    from .layouts import MENJO
    nj = np.zeros((AGES.n, _S))
    nj[:, I_KIKAN] = 1.
    nj[:, I_NOUFU] = noufuritu_row[:, 1]                       # NOUFU
    zen = noufuritu_row[:, 5] + noufuritu_row[:, 6]            # 法定 ＋ 申請
    for d in range(MENJO_DANKAI):
        v = zen if d == 1 else noufuritu_row[:, d]              # ZENGAKU = 1
        for k in range(3):
            nj[:, L.i("menjo[%d][%d]" % (d, k))] = v
    nj[:, I_GAKUSEI] = noufuritu_row[:, 7]
    nj[:, I_WAKAMONO] = noufuritu_row[:, 8]
    nj[:, I_FUKA] = noufuritu_fuka_row
    return nj


def _fdiv(a, b):
    """0 で割るときは 0（港: stdfm.nenkin_fdiv）。"""
    out = np.zeros_like(a, dtype=np.float64)
    np.divide(a, b, out=out, where=b != 0.)
    return out


def transition_year(prev, waku, dattai_gokei, dattai_shibou, shikken_rorei, saikanyuritu,
                    hasseiryoku_shogai, nj, frac_new):
    """1年進める。

    引数（年齢の配列は AGES の軸。20〜70歳だけ読む）:
      prev            前年度末の `HihoState`
      waku            外枠（この区分の被保険者数）
      dattai_gokei    脱退力（死亡を含む）、dattai_shibou 死亡力
      shikken_rorei   待期者の失権率（死亡率）
      saikanyuritu    再加入率（入力。既定 0）
      hasseiryoku_shogai 障害の発生力
      nj              当年度の納付状況 (AGES.n, 21)
      frac_new        国庫負担 1/2 の月数割合（`kokko_frac`）
    戻り値: (cur: HihoState, flows: Flows)
    """
    Hp = prev.H[:, :, I_NINZU]           # (AGES.n, K)
    Tp = prev.T[:, :, I_NINZU]
    n_age = AGES.n

    # 前年度の [x−1, t−1] と [x−1, t]（20歳は 0。B10: 原本が読む 70歳も 0 なので同じ）
    H_shift = np.zeros((n_age, K))       # H[y−1][x−1, t−1]
    H_shift[A.start + 1:A.stop, 1:] = Hp[A.start:A.stop - 1, :-1]
    H_absorb = np.zeros((n_age, K))      # t = 50 の吸収: H[y−1][x−1, 50]
    H_absorb[A.start + 1:A.stop, K - 1] = Hp[A.start:A.stop - 1, K - 1]
    T_shift = np.zeros((n_age, K))       # T[y−1][x−1, t]
    T_shift[A.start + 1:A.stop, :] = Tp[A.start:A.stop - 1, :]

    d = dattai_gokei[:, None]
    hiho_zanzon = (H_shift + H_absorb) * (1. - d)
    hiho_zanzon[:, 0] = 0.
    hzg = hiho_zanzon.sum(axis=1)

    taiki_zanzon = T_shift * (1. - shikken_rorei[:, None])
    taiki_shibou_n = T_shift - taiki_zanzon
    tzg = taiki_zanzon.sum(axis=1)

    # ② 外枠で縮める
    over = waku < hzg
    r = np.where(over, _fdiv(waku, hzg), 1.)
    hiho_zanzon = hiho_zanzon * r[:, None]

    # ③ 再加入（率は入力。既定 0）
    saikanyu_gokei = np.minimum((waku - hzg) * saikanyuritu, tzg)
    rs = _fdiv(saikanyu_gokei, tzg)
    saikanyu = taiki_zanzon * rs[:, None]
    taiki_zanzon = taiki_zanzon - saikanyu

    # ④ 新規加入
    shinki = waku - saikanyu[:, 0] - (hiho_zanzon[:, 1:] + saikanyu[:, 1:]).sum(axis=1)

    # ⑤ 確定（人数）
    H_n = hiho_zanzon + saikanyu
    H_n[:, 0] = shinki + saikanyu[:, 0]
    dattaisha_gokei = (H_shift + H_absorb) - hiho_zanzon
    hasseisha_shogai = (H_shift + H_absorb) * hasseiryoku_shogai[:, None]
    hiho_shibou_n = (H_shift + H_absorb) * dattai_shibou[:, None]
    dattaisha_seizon = dattaisha_gokei - hiho_shibou_n
    for arr in (dattaisha_gokei, hasseisha_shogai, hiho_shibou_n, dattaisha_seizon):
        arr[:, 0] = 0.
    T_n = taiki_zanzon + dattaisha_seizon
    T_n[:, 0] = taiki_zanzon[:, 0]
    # 20〜70歳の外は触らない
    outside = np.ones(n_age, dtype=bool)
    outside[A] = False
    for arr in (H_n, T_n, hiho_shibou_n, taiki_shibou_n, hasseisha_shogai,
                dattaisha_seizon, saikanyu, hiho_zanzon, taiki_zanzon):
        arr[outside] = 0.
    shinki[outside] = 0.

    # ⑥ 属性の人数加重平均
    Hs = np.zeros((n_age, K, _S))        # 前年度の属性（ずらしたもの）
    Hs[A.start + 1:A.stop, 1:] = prev.H[A.start:A.stop - 1, :-1]
    Ts = np.zeros((n_age, K, _S))
    Ts[A.start + 1:A.stop, :] = prev.T[A.start:A.stop - 1, :]
    nj_b = nj[:, None, :]                 # 年齢 → 期間へ放送

    c_hiho = saikanyu * 0.5 + hiho_zanzon
    c_hiho[:, 0] = (saikanyu[:, 0] + shinki) * 0.5
    H = (saikanyu[:, :, None] * Ts + hiho_zanzon[:, :, None] * Hs
         + scalar_split(L, c_hiho[:, :, None], nj_b, _M_OLD, _M_NEW, _M_SUM, frac_new))
    H[:, :, I_NINZU] = H_n
    H = average_by_ninzu(H)

    T = (taiki_zanzon[:, :, None] * Ts + dattaisha_seizon[:, :, None] * Hs
         + scalar_split(L, (dattaisha_seizon * 0.5)[:, :, None], nj_b,
                        _M_OLD, _M_NEW, _M_SUM, frac_new))
    T[:, :, I_NINZU] = T_n
    T = average_by_ninzu(T)

    # 死亡した人の属性は「前年度の属性 ＋ 当年度の半年ぶん」（人数で割らない）
    hiho_shibou = Hs + scalar_split(L, 0.5, nj_b, _M_OLD, _M_NEW, _M_SUM, frac_new)
    hiho_shibou[:, :, I_NINZU] = hiho_shibou_n
    taiki_shibou = Ts.copy()
    taiki_shibou[:, :, I_NINZU] = taiki_shibou_n

    return HihoState(H, T), Flows(hiho_shibou, taiki_shibou, hasseisha_shogai,
                                  dattaisha_seizon, shinki)
