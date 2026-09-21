# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/econ.c の忠実移植
===============================================
経済前提（物価上昇率・賃金上昇率・運用利回り）を読み、年度ごとの
名目の率と、保険料改定率の累積（Id_Hhd）・物価の累積（Id_Cid, Id_Cid_2）を作る。

原本の癖をそのまま残しているところ
----------------------------------
1. **HCdum は上書き前の H を使う**（econ.c:59-81）
   ループの中で HCdum を先に計算し、そのあとで k=1〜22 の Ri と H を実績値へ
   上書きしている。つまり HCdum（賃金/物価の比。jh_kaite が3年幾何平均を
   取るのに使う）は **ファイルから読んだ H** で作られ、Ri2 は **上書き後の
   Ri** で作られる。順序を入れ替えると値が変わる。

2. **Id_Cid と Id_Cid_2 で参照する年度が1つずれる**（econ.c:102-110）
       Id_Cid[k]   = Id_Cid[k-1]   * (1 + Ci[k-1])
       Id_Cid_2[k] = Id_Cid_2[k-1] * (1 + Ci[k])
   前者は前年度の物価上昇率、後者は当年度のもの。誤記に見えるが、
   公表値と一致するのはこの形（Id_Cid_2 は zan_jimu==0 のときだけ作る）。

3. **HCdum[0] は 0 のまま**
   ループが k=1 から始まるので添字 0 には何も入らない。jh_kaite() が触る
   最小の添字は 1 なので実害は無い。

4. 率の定数は `1.99/100.` の形で書く。`0.0199` と書くと double の値が
   変わってビット一致が崩れる。
"""
import math

from cnum import nround
from glva import G
from setconst import ECEDY, ECSTY, MAX_REC_LEN
from stdfun import rd_drec

KAKAKU = 24      # econ.c:9 価格基準年度（2024年度）

# econ.c:60-81 の実績値。k は年度−2000。
# 原本は if の羅列だが、値と順序はそのまま。除算の形も原本どおり
# （`1.99/100.` と `0.0199` は double として別の値になる）。
_JISSEKI = {
    1:  (1.99 / 100.,   0.38 / 100.),
    2:  (0.21 / 100.,  -0.66 / 100.),
    3:  (4.91 / 100.,  -0.61 / 100.),
    4:  (2.73 / 100.,  -0.18 / 100.),
    5:  (6.82 / 100.,  -0.24 / 100.),
    6:  (3.10 / 100.,  -0.25 / 100.),
    7:  (-3.54 / 100., -0.46 / 100.),
    8:  (-6.83 / 100., -0.49 / 100.),
    9:  (7.54 / 100.,  -3.03 / 100.),
    10: (-0.26 / 100., -0.44 / 100.),
    11: (2.17 / 100.,  -0.08 / 100.),
    12: (9.57 / 100.,  -0.32 / 100.),
    13: (8.22 / 100.,  -0.14 / 100.),
    14: (11.61 / 100.,  1.06 / 100.),
    15: (-3.14 / 100.,  0.33 / 100.),
    16: (5.30 / 100.,  -0.05 / 100.),
    17: (6.50 / 100.,   0.26 / 100.),
    18: (1.42 / 100.,   0.79 / 100.),
    19: (-4.96 / 100.,  0.60 / 100.),
    20: (23.90 / 100., -0.52 / 100.),
    21: (5.19 / 100.,   1.04 / 100.),
    22: (1.44 / 100.,   1.39 / 100.),
}


def econ():
    """econ.c:13 void econ(void) の忠実移植。"""
    num_dtemp = 7                    # sizeof dtemp / sizeof dtemp[0]
    dtemp = [0.0] * num_dtemp

    for k in range(0, ECEDY - ECSTY + 1):
        G.Id_Hhd[k] = 1.
        G.Id_Cid[k] = 1.
        G.Id_Cid_2[k] = 1.

    ifp = G.ifp_econ
    k = 1
    for rec in ifp:                  # while(fgets(rec, MAX_REC_LEN, ifp)!=NULL)
        rec = rec[:MAX_REC_LEN - 1]  # fgets は MAX_REC_LEN-1 バイトで切る
        rd_drec(rec, dtemp, num_dtemp)
        if k != int(dtemp[0]):
            print(f"Econの年度が違います。({k}<>{int(dtemp[0])})")
            raise SystemExit(1)
        else:
            Ridum = dtemp[1] / 100.
            Hdum = dtemp[5] / 100.
            Cidum = dtemp[6] / 100.
            G.Ri[k - ECSTY] = (1. + Ridum) * (1. + Cidum) - 1.
            G.H[k - ECSTY] = (1. + Hdum) * (1. + Cidum) - 1.
            G.Ci[k - ECSTY] = Cidum
        k += 1

    # econ.c:51 ファイルが尽きたら最終年度の値を横に延ばす
    while k <= ECEDY:
        G.Ri[k - ECSTY] = G.Ri[k - 1 - ECSTY]
        G.H[k - ECSTY] = G.H[k - 1 - ECSTY]
        G.Ci[k - ECSTY] = G.Ci[k - 1 - ECSTY]
        k += 1

    for k in range(1, ECEDY + 1):
        # 【重要】HCdum は下の実績値上書きより「先」に計算される（econ.c:59）
        G.HCdum[k - ECSTY] = (1. + G.H[k - ECSTY]) / (1. + G.Ci[k - ECSTY])

        if k in _JISSEKI:            # econ.c:60-81
            ri, h = _JISSEKI[k]
            G.Ri[k - ECSTY] = ri
            G.H[k - ECSTY] = h

        # Ri2 は上書き「後」の Ri を使う（econ.c:82）
        G.Ri2[k - ECSTY] = math.pow(1. + G.Ri[k - ECSTY], 0.5) - 1.

    G.Id_Hhd[5 - ECSTY] = 1.         # econ.c:85（上の初期化と同値なので冗長）

    for k in range(6, ECEDY + 1):
        if k <= KAKAKU + 1:
            # 価格基準年度までは 3 桁に丸めながら積む（econ.c:89-94）
            kaite_ci = nround(G.Ci[k - 2 - ECSTY], 3)
            kaite_hp = nround((1.0 + kaite_ci)
                              * nround(1.0 + jh_kaite(k - 1), 3), 3) - 1.
            if k <= 7:
                kaite_hp = kaite_ci
            if k == 18:
                kaite_hp = -0.009

            G.Id_Hhd[k - ECSTY] = nround(
                G.Id_Hhd[k - 1 - ECSTY] * (1.0 + kaite_hp), 3)
        else:
            # 以降は丸めない（econ.c:96-99）
            kaite_ci = G.Ci[k - 2 - ECSTY]
            kaite_hp = (1.0 + kaite_ci) * (1.0 + jh_kaite(k - 1)) - 1.

            G.Id_Hhd[k - ECSTY] = G.Id_Hhd[k - 1 - ECSTY] * (1.0 + kaite_hp)

        if k > KAKAKU:
            # 参照するのは「前年度」の物価上昇率（econ.c:103）
            G.Id_Cid[k - ECSTY] = G.Id_Cid[k - 1 - ECSTY] * (1. + G.Ci[k - 1 - ECSTY])

        if G.zan_jimu == 0:
            if k > 24:
                # こちらは「当年度」。Id_Cid と1年ずれる（econ.c:108）
                G.Id_Cid_2[k - ECSTY] = G.Id_Cid_2[k - 1 - ECSTY] * (1. + G.Ci[k - ECSTY])

    # econ.c:114 価格基準年度で 1 になるよう全体を割り戻す
    dtemp[0] = float(G.Id_Hhd[KAKAKU - ECSTY])
    if dtemp[0] > 0.:
        for k in range(ECSTY, ECEDY + 1):
            G.Id_Hhd[k - ECSTY] /= dtemp[0]
    else:
        print(f"保険料改定率({dtemp[0]:f})、価格基準年度({KAKAKU})の設定が"
              "おかしいです")
        raise SystemExit(1)


def jh_kaite(k):
    """econ.c:125 double jh_kaite(int k) の忠実移植。

    HCdum[k-2], HCdum[k-3], HCdum[k-4] の積の立方根から 1 を引く。
    賃金上昇率（物価で割り戻したもの）の3年幾何平均。
    """
    if k <= 4 or ECEDY < k:
        print("econ.c中のjh_kaite()の引数年度が想定範囲外です。")
        raise SystemExit(1)
    else:
        djh = 1.
        for n in range(2, 5):        # for(n=2; n<=4; n++)
            djh *= G.HCdum[k - n - ECSTY]
        djh = math.pow(djh, 1. / 3.) - 1.
    return djh
