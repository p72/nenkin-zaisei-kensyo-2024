# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/simlbzw.cpp の忠実移植（標準報酬と平均標準報酬額）
=======================================================================
560 行。年齢 `x`・経過年 `t` の

    bb  [x][t]         標準報酬（年額）
    bbnp[x][t]         うちパート以外
    bbpt[x][t]         うちパート
    z   [x][t][i][j]   加入期間の区分別
    ze  [x][t][i][j]   同（受給待期）
    w   [x][t][0][j][ii] 平均標準報酬額（`ii` は再評価の仕方4通り）
    we  [x][t][0][j][ii] 同（受給待期）
    chwd[x][t][ii]     年度途中の加入ぶんの補正

を、前年の `x - 1` から作る。`simlbzw(x, t)` が `t >= 1`、
`simlbzw0(x)` が `t == 0` を受け持つ。

`ii` — 再評価（過去の報酬を現在価値に直す）の4通り
--------------------------------------------------
| `ii` | `chs`（1年ぶんの伸び） | 使いどころ |
|---|---|---|
| 0 | 67歳以下は `1 + hh`、68歳以上は `1 + ci` | 本来水準 |
| 1 | `1.0`（伸ばさない） | 名目のまま |
| 2 | `1 + ci2[k][max(x, 67)]` | 従前額保障 |
| 3 | `1 + hh`（年齢に関係なく） | 賃金だけ |

`cht` は「足元まで遡って積み上げた再評価率」で、`cht_flg == 1` の
ときだけ作る。`cntl.cpp` は `cht_flg = 1` を直書きしている。

`cht_flg != 1` だと `cht` が未初期化のまま使われる
-------------------------------------------------
```c
double chs, ch9, cht;          /* 初期化なしの自動変数 */
...
FOR(ii, 0, 3) {
  if(ii == 0) {
    ...
    if(cht_flg == 1) { cht = …; }      /* else が無い */
  }
  else if(ii == 1) { chs=1.0; ch9=1.0+h.AT(k); cht=1.0; }
  ...
  if(k-x >= -62) { cht=cht*0.998*0.991*0.995*0.999; }
```

`ii == 0` で `cht_flg != 1` だと、**1回めの `ii` で未初期化の
`cht` を読む**（2回め以降は前の `ii` の値が残る）。
`cntl.cpp` が `cht_flg = 1` 固定なので通る経路では起きない。
`検証/原本の不具合.md` の H4。

移植版は `cht = None` で始めて、その経路に入ったら落ちるようにする。

`bn` `bb` をループの中でゼロにする
----------------------------------
```c
if(j4_calc) {
  if(pseid == 0) {
    if(x >= hihonen) {              /* hihonen = 70 */
      bn.AT(k, x, s) = 0.0;         /* ← グローバル */
      if(s <= 2) bnpt.AT(k, x, s) = 0.0;
    }
  }
  ...
      if(x >= hihonen) {
        bb.AT(x, t)   = 0.0;        /* ← グローバル */
        bbnp.AT(x, t) = 0.0;
        bbpt.AT(x, t) = 0.0;
        if(x >= hihonen+1) {
          bbnp0 = 0.0;              /* ← 局所。次の ii に効く */
          bbpt0 = 0.0;
        }
      }
```

70歳以上の報酬を 0 にする処理が **`ii` のループの中**にある。
`bn` `bb` はグローバルなので4回同じ代入をするだけだが、
`bbnp0` `bbpt0` は局所なので **`ii = 0` で 0 になったあと
`ii = 1, 2, 3` はその 0 を使う**。`ii` の順に依存する。
移植版も同じ順で書く。

`br` が 0 のときの枝
--------------------
```c
if(br.AT(k-1, x-1, s) > 1.0e-6){
    tmp = bbnp0*(1.0+br.AT(k, x, s)/br.AT(k-1, x-1, s))*ch9/2.0*(gz-gzpt) + …;
} else {
    tmp = (bbnp0*ch9+bbnp.AT(x, t))/2.0*(gz-gzpt) + …;
}
```

分母が 0 のときは「前年の伸ばした値と今年の値の平均」に切り替える。
掛け算の並びが2つの枝で違うので、**式をそのまま写す**。

宣言だけのものが6つ
------------------
`bbdum` `bbnpdum` `bbptdum` `bb0dum` `bbnp0dum` `bbpt0dum` `bndum`
`bnptdum` は一度も使われない（F9 の仲間）。`simlbzw0` の
`bndum` `bnptdum` も同じ。
"""
import math

from glva import G
from sepsstd import c_round, std_max, std_min
from setconst import C19, KE

__all__ = ["simlbzw", "simlbzw0"]

# 被保険者の上限年齢（原本は `int hihonen = 70;` を2か所で直書き）
HIHONEN = 70


def _cht_extra(cht, k, x):
    """`k - x`（生年度）で分かれる決め打ちの補正。"""
    if k - x >= -62:
        cht = cht * 0.998 * 0.991 * 0.995 * 0.999
    else:
        cht = cht * 0.991 * 0.995 * 0.999
    return cht


def _houjou(cht, k, s):
    """`houjou >= 1`（保険料率の上乗せ）のときの補正。"""
    if G.houjou >= 1:
        if k == G.houjouyr:
            if s == 1 or s == 3:
                cht = cht * (1.0 + (G.houjour1 - 1.0) * 1.0 / 2.0)
            else:
                cht = cht * (1.0 + (G.houjour2 - 1.0) * 1.0 / 2.0)
        elif k > G.houjouyr:
            if s == 1 or s == 3:
                cht = cht * G.houjour1
            else:
                cht = cht * G.houjour2
    return cht


def simlbzw(x, t):
    """simlbzw.cpp:4 の忠実移植（`t >= 1`）。"""
    k = G.k
    s = G.s
    pseid = G.pseid
    xend = G.xend
    tend = G.tend

    bb = G.bb
    bbnp = G.bbnp
    bbpt = G.bbpt
    bn = G.bn
    bnpt = G.bnpt
    ad = G.ad
    br = G.br
    h = G.h
    hh = G.hh
    ci = G.ci
    w = G.w
    we = G.we
    z = G.z
    ze = G.ze
    g = G.g
    ge = G.ge
    gpt = G.gpt
    gn = G.gn
    gnpt = G.gnpt
    gz = G.gz
    gzpt = G.gzpt
    gez = G.gez
    y = G.y
    ypt = G.ypt

    kou2 = (pseid == 0 and s <= 2)
    kako = (G.key == 12 and k >= G.psly)

    tm = [0.0] * 5
    z0 = [0.0] * 2
    ze0 = [0.0] * 2

    bb0 = bb[x - 1, t - 1]
    if kou2:
        bbnp0 = bbnp[x - 1, t - 1]
        bbpt0 = bbpt[x - 1, t - 1]
    else:
        bbnp0 = bb0
        bbpt0 = 0.0             # 原本は代入しない（この枝では読まない）

    if kou2:
        if g[x, t] - gpt[x, t] > 1.0e-6:
            if x != 15:
                numer = (bn[k, x, s] * ad[k] * (gn[x, t] - gnpt[x, t])
                         + bbnp0 * br[k, x, s] / br[k - 1, x - 1, s]
                         * (1.0 + h[k]) * (gz[x, t] - gzpt[x, t]))
                denom = g[x, t] - gpt[x, t]
                bbnp[x, t] = numer / denom
            else:
                bbnp[x, t] = bn[k, x, s] * ad[k]
        else:
            bbnp[x, t] = 0.0
        if gpt[x, t] > 1.0e-6:
            if x != 15:
                bbpt[x, t] = ((bnpt[k, x, s] * ad[k] * gnpt[x, t]
                               + bbpt0 * (1.0 + h[k]) * gzpt[x, t])
                              / gpt[x, t])
            else:
                bbpt[x, t] = bnpt[k, x, s] * ad[k]
        else:
            bbpt[x, t] = 0.0

        if x == xend:
            bbnp[x, t] = (bbnp0 * br[k, x, s] / br[k - 1, x - 1, s]
                          * (1.0 + h[k]))
            bbpt[x, t] = bbpt0 * (1.0 + h[k])

        if g[x, t] > 1.0e-6:
            bb[x, t] = ((bbnp[x, t] * (g[x, t] - gpt[x, t])
                         + bbpt[x, t] * gpt[x, t]) / g[x, t])
        else:
            bb[x, t] = 0.0
    else:
        if g[x, t] > 1.0e-6:
            if x != 15:
                bb[x, t] = ((bn[k, x, s] * ad[k] * gn[x, t]
                             + bb0 * br[k, x, s] / br[k - 1, x - 1, s]
                             * (1.0 + h[k]) * gz[x, t]) / g[x, t])
            else:
                bb[x, t] = bn[k, x, s] * ad[k]
        else:
            bb[x, t] = 0.0
        if x == xend:
            bb[x, t] = (bb0 * br[k, x, s] / br[k - 1, x - 1, s]
                        * (1.0 + h[k]))

    dx = 60
    kx_74 = max(k - x, -74)
    if G.flg_sigo >= 1:
        dx = 20 + max(int(c_round(G.can[C19(kx_74)])), 40)

    hihonen = HIHONEN

    # ------------------------------------------------------------------
    # 加入期間の区分（z / ze）
    # ------------------------------------------------------------------
    for j in range(0, 6 + 1):
        for i in range(0, 1 + 1):
            z0[i] = z[x - 1, t - 1, i, j]
            if t == tend - 1 and z0[i] <= 1.0e-6:
                z0[i] = z[x - 1, t, i, j]
            ze0[i] = ze[x - 1, t, i, j]

            tm[1] = gn[x, t] * ze0[i] + gz[x, t] * z0[i]
            tm[2] = gez[x, t] * ze0[i] + y[x, t, 1] * z0[i]

            if kako:
                z0[i] = G.psz[x - 1, t - 1, i, j]
                if t == tend - 1 and z0[i] <= 1.0e-6:
                    z0[i] = G.psz[x - 1, t, i, j]

                ze0[i] = G.psze[x - 1, t, i, j]

                tm[3] = gn[x, t] * ze0[i] + gz[x, t] * z0[i]
                tm[4] = gez[x, t] * ze0[i] + y[x, t, 1] * z0[i]

            if (x <= hihonen
                    and (j == 0 or j == 4
                         or (s == 1 and x >= 40 and j == 5)
                         or (s >= 2 and x >= 35 and j == 5)
                         or (20 <= x <= dx and j == 6))):

                if i == 0 or (s == 3 and i == 1):
                    if ((s == 1 and x == 40 and j == 5)
                            or (s >= 2 and x == 35 and j == 5)
                            or ((x == 20 or x == dx) and j == 6)
                            or x == hihonen):
                        tm[0] = gz[x, t] / 2.0 + gn[x, t] / 2.0
                    else:
                        tm[0] = gz[x, t] + gn[x, t] / 2.0
                    if kako:
                        tm[3] += tm[0]
                    else:
                        tm[1] += tm[0]

                    if ((s == 1 and x == 40 and j == 5)
                            or (s >= 2 and x == 35 and j == 5)
                            or (x == 20 and j == 6)):
                        tm[0] = 0.0
                    else:
                        tm[0] = y[x, t, 1] / 2.0
                    if kako:
                        tm[4] += tm[0]
                    else:
                        tm[2] += tm[0]

            z[x, t, i, j] = 0.0
            ze[x, t, i, j] = 0.0

            if g[x, t] > 1.0e-6:
                z[x, t, i, j] = tm[1] / g[x, t]
            if ge[x, t] > 1.0e-6:
                ze[x, t, i, j] = tm[2] / ge[x, t]
            if kako:
                G.psz[x, t, i, j] = 0.0
                G.psze[x, t, i, j] = 0.0
                if g[x, t] > 1.0e-6:
                    G.psz[x, t, i, j] = tm[3] / g[x, t]
                if ge[x, t] > 1.0e-6:
                    G.psze[x, t, i, j] = tm[4] / ge[x, t]

    # ------------------------------------------------------------------
    # 平均標準報酬額（w / we）と chwd
    # ------------------------------------------------------------------
    cht = None                  # cht_flg != 1 だと未初期化（H4）
    for ii in range(0, 3 + 1):
        if ii == 0:
            if x <= 67:
                chs = 1.0 + hh[k]
            else:
                chs = 1.0 + ci[k]
            ch9 = 1.0 + h[k]

            if G.cht_flg == 1:
                kk = min(k, KE - 3)
                cht = (G.dir[k] * (1.0 + G.ci0[kk - 1 + 2])
                       * (1.0 + G.ci0[kk - 1 + 3]))

                if x <= 64:
                    cht = (cht / (1.0 + hh[kk + 1]) / (1.0 + hh[kk + 2])
                           / (1.0 + hh[kk + 3]))
                elif x == 65:
                    cht = (cht / (1.0 + hh[kk + 1]) / (1.0 + hh[kk + 2])
                           / (1.0 + ci[kk + 3]))
                elif x == 66:
                    cht = (cht / (1.0 + hh[kk + 1]) / (1.0 + ci[kk + 2])
                           / (1.0 + ci[kk + 3]))
                else:
                    cht = (cht / (1.0 + ci[kk + 1]) / (1.0 + ci[kk + 2])
                           / (1.0 + ci[kk + 3]))
        elif ii == 1:
            chs = 1.0
            ch9 = 1.0 + h[k]
            cht = 1.0
        elif ii == 2:
            chs = 1.0 + G.ci2[k, max(x, 67)]
            ch9 = 1.0 + h[k]

            if G.cht_flg == 1:
                cht = G.jz_shk[k] * 1.031 * 0.988
                for kk in range(5, k + 1):
                    cht = cht * (1.0 + G.ci2[kk, max(x - k + kk, 67)])
        elif ii == 3:
            chs = 1.0 + hh[k]
            ch9 = 1.0 + h[k]
            if G.cht_flg == 1:
                kk = min(k, KE - 3)
                cht = (G.dir[k] * (1.0 + G.ci0[kk - 1 + 2])
                       * (1.0 + G.ci0[kk - 1 + 3])
                       / (1.0 + hh[kk + 1]) / (1.0 + hh[kk + 2])
                       / (1.0 + hh[kk + 3]))

        cht = _cht_extra(cht, k, x)
        cht = _houjou(cht, k, s)

        if s == 2 and 20 <= x <= 49:
            cht = cht * (1.0 + G.jiiku[k, x])

        G.chwd[x, t, ii] = bb[x, t] / 2.0 * cht
        if G.flg_hiho70 == 0 or k < G.hiho70yr:
            if pseid == 0:
                if x >= hihonen:
                    G.chwd[x, t, ii] = 0.0

        w[x, t, 0, 0, ii] = 0.0
        we[x, t, 0, 0, ii] = 0.0

        for j in range(1, 4 + 1):

            w0 = w[x - 1, t - 1, 0, j, ii]
            if t == tend - 1 and w0 <= 1.0e-6:
                w0 = w[x - 1, t, 0, j, ii]
            we0 = we[x - 1, t, 0, j, ii]

            tmp = gn[x, t] * we0 + gz[x, t] * w0
            tmq = gez[x, t] * we0 + y[x, t, 1] * w0
            tm[1] = tmp * chs
            tm[2] = tmq * chs

            j4_calc = True
            if j <= 3:
                j4_calc = False
            if kako:
                j4_calc = False

            if j4_calc:
                if pseid == 0:
                    if x >= hihonen:
                        bn[k, x, s] = 0.0
                        if s <= 2:
                            bnpt[k, x, s] = 0.0

                if kou2:
                    tm[1] = (tm[1]
                             + (bn[k, x, s] * ad[k]
                                * (gn[x, t] - gnpt[x, t])
                                + bnpt[k, x, s] * ad[k] * gnpt[x, t])
                             / 2.0 * cht)

                    if x > 15:
                        if pseid == 0:
                            if x >= hihonen:
                                bb[x, t] = 0.0
                                bbnp[x, t] = 0.0
                                bbpt[x, t] = 0.0
                                if x >= hihonen + 1:
                                    # 局所なので次の ii に効く
                                    bbnp0 = 0.0
                                    bbpt0 = 0.0
                        if br[k - 1, x - 1, s] > 1.0e-6:
                            tmp = (bbnp0
                                   * (1.0 + br[k, x, s] / br[k - 1, x - 1, s])
                                   * ch9 / 2.0 * (gz[x, t] - gzpt[x, t])
                                   + bbpt0 * ch9 * gzpt[x, t])
                        else:
                            tmp = ((bbnp0 * ch9 + bbnp[x, t]) / 2.0
                                   * (gz[x, t] - gzpt[x, t])
                                   + (bbpt0 * ch9 + bbpt[x, t]) / 2.0
                                   * gzpt[x, t])
                        tmq = ((bbnp0 * ch9 * (y[x, t, 1] - ypt[x, t, 1])
                                + bbpt0 * ch9 * ypt[x, t, 1]) / 2.0)
                        assert not math.isnan(tmp)

                        tm[1] = tm[1] + tmp * cht
                        tm[2] = tm[2] + tmq * cht
                else:
                    tm[1] = (tm[1] + bn[k, x, s] * ad[k] / 2.0
                             * gn[x, t] * cht)
                    if x > 15:
                        if pseid == 0:
                            if x >= hihonen:
                                bb[x, t] = 0.0
                                if x >= hihonen + 1:
                                    bb0 = 0.0
                        if br[k - 1, x - 1, s] > 1.0e-6:
                            tmp = (bb0
                                   * (1.0 + br[k, x, s] / br[k - 1, x - 1, s])
                                   * ch9 / 2.0 * gz[x, t])
                        else:
                            tmp = (bb0 * ch9 + bb[x, t]) / 2.0 * gz[x, t]
                        tmq = bb0 * ch9 / 2.0 * y[x, t, 1]

                        tm[1] = tm[1] + tmp * cht
                        tm[2] = tm[2] + tmq * cht

            w[x, t, 0, j, ii] = 0.0
            we[x, t, 0, j, ii] = 0.0

            if g[x, t] > 1.0e-6:
                w[x, t, 0, j, ii] = tm[1] / g[x, t]
            if ge[x, t] > 1.0e-6:
                we[x, t, 0, j, ii] = tm[2] / ge[x, t]

            if j <= 3:
                w[x, t, 0, 0, ii] = w[x, t, 0, 0, ii] + w[x, t, 0, j, ii]
                we[x, t, 0, 0, ii] = we[x, t, 0, 0, ii] + we[x, t, 0, j, ii]


def simlbzw0(x):
    """simlbzw.cpp:349 の `simlbzw0`（`t == 0`）。"""
    k = G.k
    s = G.s
    pseid = G.pseid
    xend = G.xend

    bb = G.bb
    bbnp = G.bbnp
    bbpt = G.bbpt
    bn = G.bn
    bnpt = G.bnpt
    ad = G.ad
    hh = G.hh
    ci = G.ci
    w = G.w
    we = G.we
    z = G.z
    ze = G.ze
    g = G.g
    ge = G.ge
    gpt = G.gpt
    gn = G.gn
    gez = G.gez

    kou2 = (pseid == 0 and s <= 2)
    kako = (G.key == 12 and k >= G.psly)

    tm = [0.0] * 5
    ze0 = [0.0] * 2

    if g[x, 0] > 1.0e-6:
        if kou2:
            bb[x, 0] = ((bn[k, x, s] * (g[x, 0] - gpt[x, 0])
                         + bnpt[k, x, s] * gpt[x, 0]) * ad[k] / g[x, 0])
            bbnp[x, 0] = bn[k, x, s] * ad[k]
            bbpt[x, 0] = bnpt[k, x, s] * ad[k]
        else:
            bb[x, 0] = bn[k, x, s] * ad[k]
    else:
        bb[x, 0] = 0.0
        bbpt[x, 0] = 0.0
    if x == xend:
        bb[x, 0] = bn[k, x, s] * ad[k]
        if s <= 2:
            bbpt[x, 0] = bnpt[k, x, s] * ad[k]

    dx = 60
    kx_74 = max(k - x, -74)
    if G.flg_sigo >= 1:
        dx = 20 + max(int(c_round(G.can[C19(kx_74)])), 40)

    hihonen = HIHONEN

    for j in range(0, 6 + 1):
        for i in range(0, 1 + 1):
            ze0[i] = ze[x - 1, 0, i, j]

            tm[1] = gn[x, 0] * ze0[i]
            tm[2] = gez[x, 0] * ze0[i]
            if kako:
                ze0[i] = G.psze[x - 1, 0, i, j]
                tm[3] = gn[x, 0] * ze0[i]
                tm[4] = gez[x, 0] * ze0[i]
            if (x <= hihonen
                    and (j == 0 or j == 4
                         or (s == 1 and x >= 40 and j == 5)
                         or (s >= 2 and x >= 35 and j == 5)
                         or (20 <= x <= dx and j == 6))):
                tm[0] = 0.0
                if i == 0 or (s == 3 and i == 1):
                    tm[0] = (G.gnn[x] + gn[x, 0]) / 2.0
                if kako:
                    tm[3] = tm[3] + tm[0]
                else:
                    tm[1] = tm[1] + tm[0]

            z[x, 0, i, j] = 0.0
            ze[x, 0, i, j] = 0.0

            if g[x, 0] > 1.0e-6:
                z[x, 0, i, j] = tm[1] / g[x, 0]
            if ge[x, 0] > 1.0e-6:
                ze[x, 0, i, j] = tm[2] / ge[x, 0]
            if kako:
                G.psz[x, 0, i, j] = 0.0
                G.psze[x, 0, i, j] = 0.0

                if g[x, 0] > 1.0e-6:
                    G.psz[x, 0, i, j] = tm[3] / g[x, 0]
                if ge[x, 0] > 1.0e-6:
                    G.psze[x, 0, i, j] = tm[4] / ge[x, 0]

    cht = None                  # cht_flg != 1 だと未初期化（H4）
    for ii in range(0, 3 + 1):
        if ii == 0:
            if x <= 67:
                chs = 1.0 + hh[k]
            else:
                chs = 1.0 + ci[k]

            if G.cht_flg == 1:
                kk = min(k, KE - 3)
                cht = (G.dir[k] * (1.0 + G.ci0[kk - 1 + 2])
                       * (1.0 + G.ci0[kk - 1 + 3]))

                if x <= 64:
                    cht = (cht / (1.0 + hh[kk + 1]) / (1.0 + hh[kk + 2])
                           / (1.0 + hh[kk + 3]))
                elif x == 65:
                    cht = (cht / (1.0 + hh[kk + 1]) / (1.0 + hh[kk + 2])
                           / (1.0 + ci[kk + 3]))
                elif x == 66:
                    cht = (cht / (1.0 + hh[kk + 1]) / (1.0 + ci[kk + 2])
                           / (1.0 + ci[kk + 3]))
                else:
                    cht = (cht / (1.0 + ci[kk + 1]) / (1.0 + ci[kk + 2])
                           / (1.0 + ci[kk + 3]))
        elif ii == 1:
            chs = 1.0
            cht = 1.0
        elif ii == 2:
            chs = 1.0 + G.ci2[k, max(x, 67)]

            if G.cht_flg == 1:
                cht = G.jz_shk[k] * 1.031 * 0.988
                for kk in range(5, k + 1):
                    cht = cht * (1.0 + G.ci2[kk, max(x - k + kk, 67)])
        elif ii == 3:
            chs = 1.0 + hh[k]
            if G.cht_flg == 1:
                kk = min(k, KE - 3)
                cht = (G.dir[k] * (1.0 + G.ci0[kk - 1 + 2])
                       * (1.0 + G.ci0[kk - 1 + 3])
                       / (1.0 + hh[kk + 1]) / (1.0 + hh[kk + 2])
                       / (1.0 + hh[kk + 3]))

        cht = _cht_extra(cht, k, x)

        G.chwd[x, 0, ii] = bb[x, 0] / 2.0 * cht
        if G.flg_hiho70 == 0 or k < G.hiho70yr:
            if pseid == 0:
                if x >= hihonen:
                    G.chwd[x, 0, ii] = 0.0

        # `simlbzw` と違って `houjou` の補正は chwd のあと、
        # `jiiku`（2種の標準報酬比率）の補正は無い
        cht = _houjou(cht, k, s)

        w[x, 0, 0, 0, ii] = 0.0
        we[x, 0, 0, 0, ii] = 0.0

        for j in range(1, 4 + 1):

            tmp = gn[x, 0] * we[x - 1, 0, 0, j, ii]
            tmq = gez[x, 0] * we[x - 1, 0, 0, j, ii]

            tm[1] = tmp * chs
            tm[2] = tmq * chs

            j4_calc = True
            if j <= 3:
                j4_calc = False
            if kako:
                j4_calc = False

            if j4_calc:
                if pseid == 0:
                    if x >= hihonen:
                        bn[k, x, s] = 0.0
                        if s <= 2:
                            bnpt[k, x, s] = 0.0

                if kou2:
                    tm[1] = (tm[1]
                             + (bn[k, x, s] * (g[x, 0] - gpt[x, 0])
                                + bnpt[k, x, s] * gpt[x, 0])
                             / 2.0 * ad[k] * cht)
                else:
                    tm[1] = (tm[1] + bn[k, x, s] * ad[k] / 2.0
                             * g[x, 0] * cht)

            w[x, 0, 0, j, ii] = 0.0
            we[x, 0, 0, j, ii] = 0.0

            if g[x, 0] > 1.0e-6:
                w[x, 0, 0, j, ii] = tm[1] / g[x, 0]
            if ge[x, 0] > 1.0e-6:
                we[x, 0, 0, j, ii] = tm[2] / ge[x, 0]

            if j <= 3:
                w[x, 0, 0, 0, ii] = w[x, 0, 0, 0, ii] + w[x, 0, 0, j, ii]
                we[x, 0, 0, 0, ii] = we[x, 0, 0, 0, ii] + we[x, 0, 0, j, ii]
