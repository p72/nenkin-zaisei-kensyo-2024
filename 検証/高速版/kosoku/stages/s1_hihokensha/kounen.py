# -*- coding: utf-8 -*-
"""①共済と厚年の2号被保険者（移植版 `simlkyos.c` `simlkou.c`）
=================================================================
共済（`simlkyos`）
    1. `fjinkoy` より後を、総人口に対する割合の伸び（fjinkoy−1 → fjinkoy）で延ばす
    2. 70 歳以上を 69 歳に寄せる
    3. 女を有配偶・無配偶に割る（正規雇用者の比。港どおり分母は正規だけ）

厚年（`simlkou`、§2.5）
    1. 適用率 `kounenteki` の据え置きと年度末値
    2. パートを `kijunmap` より後へ短時間雇用者（区分 4+5）の伸びで延ばし、女を有配偶・無配偶に割る
    3. 調整係数 θ（`kounen_cho`）: 実績年度は (厚年 ＋ パート ＋ 共済 3 つ) / Σ 雇用者 × 適用率、
       以降は 69 歳以下を据え置き、70 歳以上は前年度の同じ年齢と 1 歳下の小さい方
    4. 厚年 = Σ 雇用者 × 適用率 × θ − パート − 共済 3 つ
    5. 70 歳以上は前年度の 1 歳下の `cap_70`（0.98）倍を上限に（年度の漸化式）
    6. 厚年の被用者を正規・非正規フル・非正規フル以外に割る（`koyou_j_m[7..10]`）
    7. 旧厚3種の割合: 実績は 3種/厚年、29 歳以下は実績 4 年度の平均、85 歳以上は 0、間はコホートで送る
    8. 年度末の総労働時間と年度末→年央、被用者の平均労働時間
    9. `kounen[0]`（計）と `nigou`（2号の合計。厚年は 69 歳以下だけ）

港: hihokensha/simlkyos.py:simlkyos
港: hihokensha/simlkou.py:simlkou
仕様: §2.5、§2.6
"""
import numpy as np

__all__ = ["simlkyos", "simlkou"]

_ERR = dict(divide="ignore", invalid="ignore")


def simlkyos(S, H):
    """港: hihokensha/simlkyos.py:simlkyos。仕様: §2.5"""
    hy = S.hy
    ny = hy.n
    A = S.pol.get("hihokensha.ages")
    lo, hi = A["kounen"]
    X = slice(lo, hi + 1)
    fold = int(A["kyos_fold"])
    kounen, sc, kjm = H.kounen, H.sojinko_c, H.koyou_j_m
    f0 = hy.i(S.fjinkoy)
    f1 = f0 - 1
    # 1. fjinkoy より後へ延ばす
    if ny - 1 > f0:
        for seido in (4, 5, 6):
            tmp = kounen[seido, f1, 1:3, X].sum()
            tmq = kounen[seido, f0, 1:3, X].sum()
            tmr, w0 = 0., 0.
            if tmp * sc[f1, 0] * sc[f0, 0] > 0.:
                w1 = tmp / sc[f1, 0]
                w0 = tmq / sc[f0, 0]
                tmr = w0 / w1
            n = ny - f0 - 1
            sw = w0 * tmr ** np.arange(1, n + 1)             # 割合[y] = 割合[y−1] × tmr
            den = w0 * sc[f0, 0]
            if den > 0.:
                kounen[seido, f0 + 1:, 1:3, X] = (kounen[seido, f0, 1:3, X][None]
                                                  * (sw * sc[f0 + 1:, 0] / den)[:, None, None])
            else:
                kounen[seido, f0 + 1:, 1:3, X] = 0.
                H.notes.append("共済 %d の %d 年度以降の補正がゼロ" % (seido, S.fjinkoy + 1))
    # 2. 70 歳以上を 69 歳に寄せる
    kounen[4:7, :, 1:3, fold] += kounen[4:7, :, 1:3, fold + 1:hi + 1].sum(-1)
    kounen[4:7, :, 1:3, fold + 1:hi + 1] = 0.
    # 3. 女を有配偶・無配偶に割る（年度 endy を除く）
    Y = slice(0, ny - 1)
    cond = (kjm[1, Y, 2, X] + kjm[2, Y, 2, X]) > 0.
    with np.errstate(**_ERR):
        r3 = kjm[1, Y, 3, X] / kjm[1, Y, 2, X]
        r4 = kjm[1, Y, 4, X] / kjm[1, Y, 2, X]
    for seido in (4, 5, 6):
        k2 = kounen[seido, Y, 2, X]
        kounen[seido, Y, 3, X] = np.where(cond, k2 * r3, kounen[seido, Y, 3, X])
        kounen[seido, Y, 4, X] = np.where(cond, k2 * r4, kounen[seido, Y, 4, X])
        kounen[seido, Y, 0, X] = kounen[seido, Y, 1, X] + k2


def simlkou(S, H):
    """港: hihokensha/simlkou.py:simlkou。仕様: §2.5、§2.6"""
    hy = S.hy
    ny = hy.n
    A = S.pol.get("hihokensha.ages")
    K = S.pol.get("hihokensha.kounen")
    lo, hi = A["kounen"]
    X = slice(lo, hi + 1)
    x70 = int(A["kounen_cap_from"])
    x69 = int(A["nigou_max"])
    i_rd, k0 = hy.i(S.roudyr), hy.i(S.kijunmap)
    kounen, partnin, nigou = H.kounen, H.partnin, H.nigou
    kjm, kjc = H.koyou_j_m, H.koyou_j_c
    ktc, ktm = H.kounenteki_c, H.kounenteki_m
    sdm, sdc, hm, hc = H.soroudh_m, H.soroudh_c, H.heikinh_m, H.heikinh_c
    pn0 = partnin[0, 0, 0]                       # view: パート（現行）の計

    # 1. 適用率
    ktc[1:7, i_rd + 1:] = ktc[1:7, i_rd][:, None]
    ktm[1:7, :-1] = (ktc[1:7, :-1] + ktc[1:7, 1:]) / 2.
    # 2. パートを延ばし、女を有配偶・無配偶に割る
    Y = slice(k0 + 1, ny - 1)
    tan = kjm[4] + kjm[5]
    with np.errstate(**_ERR):
        pn0[Y, 1:3, X] = pn0[k0, 1:3, X][None] * tan[Y, 1:3, X] / tan[k0, 1:3, X][None]
    Y = slice(0, ny - 1)
    tmp, tmq = tan[Y, 3, X], tan[Y, 4, X]
    with np.errstate(**_ERR):
        r = np.where(tmp + tmq > 0., tmp / (tmp + tmq), 0.)
    p2 = pn0[Y, 2, X]
    pn0[Y, 3, X] = p2 * r
    pn0[Y, 4, X] = p2 * (1. - r)
    pn0[Y, 0, X] = pn0[Y, 1, X] + p2
    # 3. 調整係数 θ
    teki = np.zeros((ny, 5, hi - lo + 1))                 # Σ 雇用者 × 適用率（年度末）
    for ii in range(1, 7):
        teki += kjm[ii, :, :, X] * ktm[ii][:, None, None]
    cho = np.zeros((ny, 5, hi - lo + 1))
    Y = slice(0, k0 + 1)
    num = kounen[1, Y, 1:3, X] + pn0[Y, 1:3, X] + kounen[4:7, Y, 1:3, X].sum(0)
    with np.errstate(**_ERR):
        cho[Y, 1:3] = np.where(teki[Y, 1:3] > 0., num / teki[Y, 1:3], 0.)
    c70 = x70 - lo
    for y in range(k0 + 1, ny):
        cho[y, 1:3, :c70] = cho[y - 1, 1:3, :c70]
        cho[y, 1:3, c70:] = np.minimum(cho[y - 1, 1:3, c70:], cho[y - 1, 1:3, c70 - 1:-1])
    cho[:, 3] = cho[:, 2]
    cho[:, 4] = cho[:, 2]
    # 4. 厚年 = Σ 雇用者 × 適用率 × θ − パート − 共済
    Y = slice(0, ny - 1)
    kounen[1, Y, 1:5, X] = teki[Y, 1:5] * cho[Y, 1:5] - pn0[Y, 1:5, X] - kounen[4:7, Y, 1:5, X].sum(0)
    kounen[1, Y, 0, X] = kounen[1, Y, 1, X] + kounen[1, Y, 2, X]
    # 5. 70 歳以上の上限（前年度の 1 歳下 × cap）。年度の漸化式なので年度ごとに
    cap = float(K["cap_70"])
    for y in range(k0 + 1, ny - 1):
        k = kounen[1, y, 1:5, x70:hi + 1]
        np.minimum(k, kounen[1, y - 1, 1:5, x70 - 1:hi] * cap, out=k)
        kounen[1, y, 2, x70:hi + 1] = kounen[1, y, 3, x70:hi + 1] + kounen[1, y, 4, x70:hi + 1]
        kounen[1, y, 0, x70:hi + 1] = kounen[1, y, 1, x70:hi + 1] + kounen[1, y, 2, x70:hi + 1]
    # （港はここで 70 歳以上の θ を作り直すが、以降 θ を読むのは 69 歳以下だけなので要らない）
    # 6. 厚年の被用者を区分に割る（69 歳以下）
    X7 = slice(lo, x69 + 1)
    c = cho[Y, 1:5, :x69 + 1 - lo]
    kjm[8, Y, 1:5, X7] = kjm[1, Y, 1:5, X7] * ktm[1, Y][:, None, None] * c
    kjm[9, Y, 1:5, X7] = kjm[2, Y, 1:5, X7] * ktm[2, Y][:, None, None] * c
    kjm[10, Y, 1:5, X7] = (kjm[3, Y, 1:5, X7] * ktm[3, Y][:, None, None]
                           + kjm[4, Y, 1:5, X7] * ktm[4, Y][:, None, None]
                           + kjm[5, Y, 1:5, X7] * ktm[5, Y][:, None, None]
                           + kjm[6, Y, 1:5, X7] * ktm[6, Y][:, None, None]) * c
    kjm[7, Y, 1:5, X7] = kjm[8, Y, 1:5, X7] + kjm[9, Y, 1:5, X7] + kjm[10, Y, 1:5, X7]
    kjm[7:11, Y, 0, X7] = kjm[7:11, Y, 1, X7] + kjm[7:11, Y, 2, X7]
    # 7. 旧厚3種の割合
    rk = np.zeros((ny, 5, hi - lo + 1))
    Y0 = slice(0, k0 + 1)
    with np.errstate(**_ERR):
        rk[Y0, 1:3] = np.where(kounen[1, Y0, 1:3, X] > 0., kounen[3, Y0, 1:3, X] / kounen[1, Y0, 1:3, X], 0.)
    young = int(K["rk_sen_young_max"]) - lo + 1
    old = int(K["rk_sen_old_min"]) - lo
    mean_young = rk[Y0, 1, :young].mean(0)
    for y in range(k0 + 1, ny):
        rk[y, 1, :young] = mean_young
        rk[y, 1, young:old] = rk[y - 1, 1, young - 1:old - 1]
        rk[y, 1, old:] = 0.
    kounen[3, Y, 1:5, X] = kounen[1, Y, 1:5, X] * rk[Y, 1:5]
    kounen[2, Y, 1:5, X] = kounen[1, Y, 1:5, X] - kounen[3, Y, 1:5, X]
    kounen[2:4, Y, 0, X] = kounen[2:4, Y, 1, X] + kounen[2:4, Y, 2, X]
    # 8. 年度末の総労働時間（被用者）と年度末→年央
    sdm[6, Y, :, X] = kjm[8, Y, :, X] * hm[1, Y][:, None, None]
    sdm[7, Y, :, X] = kjm[9, Y, :, X] * hm[2, Y][:, None, None]
    sdm[8, Y, :, X] = kjm[10, Y, :, X] * hm[8, Y][:, None, None]
    sdm[9, Y, :, X] = sdm[6, Y, :, X] + sdm[7, Y, :, X] + sdm[8, Y, :, X]
    with np.errstate(**_ERR):
        hm[10, Y] = sdm[9, Y, 0, X7].sum(-1) / kjm[7, Y, 0, X7].sum(-1)
    Y1 = slice(1, ny - 1)
    kjc[8:11, Y1, :, X] = (kjm[8:11, 0:ny - 2, :, X] + kjm[8:11, Y1, :, X]) / 2.
    kjc[7, Y1, :, X] = kjc[8, Y1, :, X] + kjc[9, Y1, :, X] + kjc[10, Y1, :, X]
    sdc[6, Y1, :, X] = kjc[8, Y1, :, X] * hc[1, Y1][:, None, None]
    sdc[7, Y1, :, X] = kjc[9, Y1, :, X] * hc[2, Y1][:, None, None]
    sdc[8, Y1, :, X] = kjc[10, Y1, :, X] * hc[8, Y1][:, None, None]
    sdc[9, Y1, :, X] = sdc[6, Y1, :, X] + sdc[7, Y1, :, X] + sdc[8, Y1, :, X]
    with np.errstate(**_ERR):
        hc[10, Y1] = sdc[9, Y1, 0, X7].sum(-1) / kjc[7, Y1, 0, X7].sum(-1)
    # 9. 計と 2号
    kounen[1, Y, :, X] = kounen[2, Y, :, X] + kounen[3, Y, :, X]
    kyosai = kounen[4:7, Y, :, X].sum(0)
    kounen[0, Y, :, X] = kounen[1, Y, :, X] + kyosai
    nigou[Y, :, X] = kyosai
    nigou[Y, :, X7] += kounen[1, Y, :, X7]
