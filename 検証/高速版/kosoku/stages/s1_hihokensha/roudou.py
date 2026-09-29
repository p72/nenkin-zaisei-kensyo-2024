# -*- coding: utf-8 -*-
"""①労働力・就業者・雇用者・自営業者・総労働時間（移植版 `simlroud.c`）
========================================================================
1. 労働力率・就業率を `roudyr` より後へ据え置く
2. 人口 × 率（§2.3）: 労働力人口 `roud_j_c`、就業者 `syugyo_j_c`、雇用者 `koyou_j_c[0]`
3. 正規・非正規の割合を `kijun` より後へ据え置く
4. 非正規短時間の割合を全体の目標に合わせて比例調整（§2.4。有配偶女性の全年齢と
   男・無配偶女性の 60 歳以上だけを動かす）。合計が 1 を超えないように切る
5. 雇用者を正規・非正規フル・非正規の時間 4 区分に割る（§2.4）
6. 自営業者 = 就業者 − 雇用者
7. 平均労働時間と総労働時間 `soroudh_c`（§2.6）
8. 年央 → 年度末（`jinko.nendomatsu`）、年度末の自営業者・総労働時間

港: hihokensha/simlroud.py:simlroud
仕様: §2.3、§2.4、§2.6
"""
import numpy as np

from .jinko import nendomatsu

__all__ = ["simlroud"]


def simlroud(S, H):
    """港: hihokensha/simlroud.py:simlroud。仕様: §2.3、§2.4、§2.6"""
    hy = S.hy
    ny = hy.n
    A = S.pol.get("hihokensha.ages")
    lo, hi = A["roudou"]
    X = slice(lo, hi + 1)
    x60 = int(A["tan_adjust_from"])
    i_rd, i_kj = hy.i(S.roudyr), hy.i(S.kijun)
    jc, jw = H.jinko_c, H.jinko_wari
    rr, sr, kr = H.roud_r, H.syugyo_r, H.koyou_r
    rjc, sjc, kjc = H.roud_j_c, H.syugyo_j_c, H.koyou_j_c
    shr, hjr, htra = H.seiki_hiseiki_r, H.hiseiki_jikan_r, H.hiseiki_tan_r_all
    jgc, hc, sdc = H.jieigyo_j_c, H.heikinh_c, H.soroudh_c

    # 1. 据え置き
    rr[i_rd + 1:, 1:5, X] = rr[i_rd, 1:5, X]
    sr[i_rd + 1:, 1:5, X] = sr[i_rd, 1:5, X]
    # 2. 人口 × 率（§2.3）。率は性 1・3・4 にあり、女（2）は 3+4、計（0）は 1+2
    rjc[:, 1:5, X] = jc[:, 1:5, X] * rr[:, 1:5, X]
    sjc[:, 1:5, X] = jc[:, 1:5, X] * sr[:, 1:5, X]
    kjc[0, :, 1:5, X] = sjc[:, 1:5, X] * kr[:, 1:5, X]
    for a in (rjc, sjc, kjc[0]):
        a[:, 2, X] = a[:, 3, X] + a[:, 4, X]
        a[:, 0, X] = a[:, 1, X] + a[:, 2, X]
    # 3. 割合の据え置き
    shr[1:4, i_kj + 1:, 1:5, X] = shr[1:4, i_kj, 1:5, X][:, None]
    htra[i_rd + 1:] = htra[i_rd]
    hjr[1:5, i_rd + 1:] = hjr[1:5, i_rd][:, None]
    # 4. 非正規短時間の比例調整（§2.4）。kijun+1〜roudyr の各年度は独立
    Y = slice(i_kj + 1, i_rd + 1)
    k0 = kjc[0, Y]
    s3 = shr[3, Y]
    tmp = (k0[:, 0, X] * htra[Y, None]).sum(1)
    tmq = (k0[:, 1, X] * s3[:, 1, X] + k0[:, 3, X] * s3[:, 3, X] + k0[:, 4, X] * s3[:, 4, X]).sum(1)
    tmr = ((k0[:, 3, X] * s3[:, 3, X]).sum(1)
           + (k0[:, 1, x60:hi + 1] * s3[:, 1, x60:hi + 1] + k0[:, 4, x60:hi + 1] * s3[:, 4, x60:hi + 1]).sum(1))
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where((htra[Y] > htra[i_kj]) & (tmp > tmq), 1. + (tmp - tmq) / tmr, 1.)
    shr[3, Y, 3, X] *= f[:, None]
    shr[3, Y, 1, x60:hi + 1] *= f[:, None]
    shr[3, Y, 4, x60:hi + 1] *= f[:, None]
    shr[3, i_rd + 1:, 1:5, X] = shr[3, i_rd, 1:5, X]
    Y = slice(i_kj + 1, ny)
    s1 = shr[1, Y, 1:5, X]
    s3 = shr[3, Y, 1:5, X]
    shr[3, Y, 1:5, X] = np.where(s3 + s1 > 1., 1. - s1, s3)
    shr[2, Y, 1:5, X] = 1. - shr[3, Y, 1:5, X] - s1
    # 5. 雇用者を区分に割る（§2.4）
    kjc[1, :, 1:5, X] = kjc[0, :, 1:5, X] * shr[1, :, 1:5, X]
    kjc[2, :, 1:5, X] = kjc[0, :, 1:5, X] * shr[2, :, 1:5, X]
    for ii in range(3, 7):
        kjc[ii, :, 1:5, X] = kjc[0, :, 1:5, X] * shr[3, :, 1:5, X] * hjr[ii - 2, :][:, None, None]
    kjc[1:7, :, 2, X] = kjc[1:7, :, 3, X] + kjc[1:7, :, 4, X]
    kjc[1:7, :, 0, X] = kjc[1:7, :, 1, X] + kjc[1:7, :, 2, X]
    # 6. 自営業者
    jgc[:, :, X] = sjc[:, :, X] - kjc[0, :, :, X]
    # 7. 平均労働時間の据え置きと総労働時間（§2.6）
    hc[1:10, i_rd + 1:] = hc[1:10, i_rd][:, None]
    _soroudh(sdc, kjc, jgc, hc, X)
    # 8. 年度末
    rjm, sjm, kjm = H.roud_j_m, H.syugyo_j_m, H.koyou_j_m
    b = hy.i(S.sjinkoy)
    rjm[...] = nendomatsu(rjc, jw, lo, hi, b)
    sjm[...] = nendomatsu(sjc, jw, lo, hi, b)
    for ii in range(0, 7):
        kjm[ii] = nendomatsu(kjc[ii], jw, lo, hi, b)
    jgm, sdm, hm = H.jieigyo_j_m, H.soroudh_m, H.heikinh_m
    jgm[:-1, :, X] = sjm[:-1, :, X] - kjm[0, :-1, :, X]
    hm[1:10, :-1] = (hc[1:10, :-1] + hc[1:10, 1:]) / 2.
    _soroudh(sdm, kjm, jgm, hm, X)


def _soroudh(sd, kj, jg, h, X):
    """総労働時間 = Σ 区分の人数 × 平均労働時間（§2.6）。0 計 / 1 正規 / 2 非正規フル / 3 非正規短時間 / 4 自営。"""
    hh = lambda k: h[k][:, None, None]            # noqa: E731
    sd[1, :, 1:5, X] = kj[1, :, 1:5, X] * hh(1)
    sd[2, :, 1:5, X] = kj[2, :, 1:5, X] * hh(2)
    sd[3, :, 1:5, X] = (kj[3, :, 1:5, X] * hh(3) + kj[4, :, 1:5, X] * hh(4)
                        + kj[5, :, 1:5, X] * hh(5) + kj[6, :, 1:5, X] * hh(6))
    sd[4, :, 1:5, X] = jg[:, 1:5, X] * hh(7)
    sd[0, :, 1:5, X] = sd[1, :, 1:5, X] + sd[2, :, 1:5, X] + sd[3, :, 1:5, X] + sd[4, :, 1:5, X]
    sd[0:5, :, 2, X] = sd[0:5, :, 3, X] + sd[0:5, :, 4, X]
    sd[0:5, :, 0, X] = sd[0:5, :, 1, X] + sd[0:5, :, 2, X]
