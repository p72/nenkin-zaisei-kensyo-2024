# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/econ.cpp の忠実移植（経済前提と改定率）
=============================================================
`econ-{番号}.csv` を読んで、名目の運用利回り `ri`・賃金上昇率 `h`・
物価上昇率 `ci0` を作り、そこから**改定率**（年金額をどう改定するか）を
年度と年齢ごとに組み立てる。②でいちばん込み入った 578 行。

読むもの
--------
`econ-{iecon}.csv` の1行が1年度（`k` = 西暦 − 2000）。使う列は

    vals[0]  年度（`assert(k == kk)` で確かめる）
    vals[1]  実質の運用利回り（％）  → ridum
    vals[5]  実質の賃金上昇率（％）  → hdum
    vals[6]  物価上昇率（％）        → ci0dum

名目化は `(1 + 実質) × (1 + 物価) − 1`。ただし**2001〜2022年度は実績が
決め打ち**で、ファイルから読んだ値を上書きする（`econ.cpp:80-101`）。

改定率の骨格
------------
年金額の改定は「本来水準」と「特例水準（従前額保障）」の高い方を使う、
という制度をそのまま書いている。

    id_hh_juzen[k]       従前額保障の水準（賃金スライド）
    id_hh_hon0[k][x]     本来水準（年齢 x ごと。68歳以降は物価スライド）
    id_hh_honju8w[k][x]  本来と従前の高い方（下限は67歳の8割）
    id_hh_toku[k][x]     特例水準
    id_hh_siku[k][x]     実際に適用する水準 ＝ max(本来, 特例)
    arv_hh[k][x]         前年度からの伸び（実際の改定率）

`hp`（報酬比例の年金額）側も同じ形で、`idg_hp_hon8w` が円単位の
決め打ち（7809 円）から積み上がる。

`tamari_ci` — 物価下落の「たまり」
---------------------------------
```c
tamari_ci = -1.7e-2;                                      /* 初期値 */
...
tamari_ci = sst::roundn(tamari_ci + kaite_cird - cid, 3);  /* 毎年度更新 */
```

特例水準を解消するまでのあいだ、物価下落で使わなかったぶんを溜めておく。
`tamari_ci < 0.0 || k <= marume_yr`（24）のあいだは**3桁・4桁に丸めながら**
進み、解消後は丸めずに進む。**丸めるかどうかがここで切り替わる**のが
②の改定率のいちばん厄介なところ。

`jitsuchin_kashobun()` — 実質賃金の3年平均と可処分所得割合
----------------------------------------------------------
    jh_kaite[k] = ( (1+h[k-4])(1+h[k-3])(1+h[k-2]) ) ^ (1/3)
    prema[k]    = 前年 + 0.354%（上限 18.3%）        保険料率
    koujor[k]   = ( 0.910 − prema[k-3]/2 ) / ( 0.910 − prema[k-4]/2 )

`koujor` は可処分所得割合の変化率。保険料率の半分（本人負担）が
増えるぶん手取りが減る。`k <= 6` は 1.0。

`rv[k][j]` — 給付種別ごとの改定率
---------------------------------
`j` は 1〜23 の給付の種類。`j <= 14 && j != 13` は個別に作り、
`j == 13` は 0、それ以外（15〜23）は `same[j]` の種類を**そのまま写す**。

    same = { …, 15→14, 16→14, 17→14, 18→6, 19→4, 20→5, 21→5, 22→13, 23→4 }

`ad[k]` `ad2[k]` `bd[k][j]` — 累積
----------------------------------
    ad[k]     賃金の累積（基準年度 = 1.0）
    ad2[k]    改定率の累積（2004年度 = 0.988 から基準年度まで）
    bd[k][j]  給付種別ごとの改定率の累積（基準年度 = 1.0）

`k <= marume_yr` のあいだは毎年度 3 桁に丸める。

書き出すもの
------------
    kaiteb   `arv_hh`（年度, 67〜115歳の49列）  ← ③国民年金が読む
    kaitea   `arv_hp`（同）
    prtfil   「経済的要素」の表（`%8.5f`）

原本の癖をそのまま残しているところ
----------------------------------
1. **`fp_map["kaitea"]` を `if(pseid == 0)` の前に引く**
   （`econ.cpp:518-520`）。`std::map::operator[]` は無いキーで
   **NULL を挿入する**ので、厚年以外の制度では `fp_map` に NULL が
   2つ混ざる。`fcls()` が `fclose(NULL)` で落ちるので移植パッチで
   ガードしてある（`検証/原本の不具合.md` A2）。
   移植版も同じく `None` を挿入する。

2. **`kaitea` に `arv_hp`、`kaiteb` に `arv_hh` を書く**
   （`econ.cpp:537-538`）。名前と中身の対応が入れ替わって見える。
   ③国民年金の `KOKUKAITE-*` の作り方に合わせたものと読める。

3. **`marume_yr` が `double`。**`int` で足りるのに `double` で持ち、
   `k <= marume_yr` で `int` を `double` に上げて比べる。

4. **`ri` と `h` はファイルを読んでから上書きされる。**
   2001〜2022年度は `econ.cpp:80-101` の決め打ちが勝つので、
   `econ-*.csv` の該当年度の列1・列5は**使われない**。
   ただし `ci0`（列6）はそのまま使い、`hdum` も
   `jitsuchin_kashobun()` が読むので、列5は間接的に効く。

5. **`assert(cid == kaite_hhrd && cid == kaite_cird)` が `k == 13` に
   だけある**（`econ.cpp:266`）。浮動小数の等値比較だが、どちらも
   `roundn(.., 3)` を通った値なので一致する。

6. **`else` の枝が `k < 21` と `k >= 21` で入れ替わる書き方**
   （`econ.cpp:171-180`）。`if(k < 21){ … } else if(hhd < cid){ … }` と
   `else if` にしているので、`k >= 21` かつ `hhd >= cid` のときは
   何もしない。

7. **同じ計算が「丸める版」と「丸めない版」で2回書かれている**
   （`econ.cpp:182-243` と `:277-292`）。`tamari_ci` の符号で
   どちらかだけが効く。72行のうち実質36行。

8. **`ci_kijun` `hhd` `cid` を使い回す。**`hhd` は「賃金の改定率」
   だったものが `ci_kijun` の判定のあとは「特例水準の下げ幅」に
   意味が変わる（`econ.cpp:261`）。

9. **`vals_hh` の `else` の枝（0 埋め）に届かない。**
   `for(k = 5; k <= FLKE; k++)` で `FLKE == KE == 125` なので
   `5 <= k && k <= KE` は常に真。
"""
import math

import numpy as np

from csvio import getnums, join
from glva import G
from sepsstd import roundn, std_max, std_min, c_round
from setconst import ECEDY, FLKE, KE, KIJUN

__all__ = ["econ"]

# `econ.cpp:41-48` の `same`。`rv[k][j]` を写す先（添字 15〜23 だけ使う）
_SAME = (0, 0, 0, 0, 0,
         0, 0, 0, 0, 0,
         0, 0, 0, 0, 0,
         14, 14, 14, 6, 4,
         5, 5, 13, 4)

# `econ.cpp:80-101` の決め打ち（2001〜2022年度の実績）。(ri, h) を％で
_JISSEKI = {
    1: (1.99, 0.38), 2: (0.21, -0.66), 3: (4.91, -0.61), 4: (2.73, -0.18),
    5: (6.82, -0.24), 6: (3.10, -0.25), 7: (-3.54, -0.46), 8: (-6.83, -0.49),
    9: (7.54, -3.03), 10: (-0.26, -0.44), 11: (2.17, -0.08),
    12: (9.57, -0.32), 13: (8.22, -0.14), 14: (11.61, 1.06),
    15: (-3.14, 0.33), 16: (5.30, -0.05), 17: (6.50, 0.26),
    18: (1.42, 0.79), 19: (-4.96, 0.60), 20: (23.90, -0.52),
    21: (5.19, 1.04), 22: (1.44, 1.39),
}

# `id_hh_hon0.AT(4, x)`（`econ.cpp:110-118`）。2004年度の本来水準
_HON0_2004 = {
    67: 0.990, 68: 0.982, 69: 0.975, 70: 0.971, 71: 0.971, 72: 0.971,
    73: 0.971 * 1.064 / 1.069,
    74: 0.971 * 1.041 / 1.069,
    75: 0.971 * 1.031 / 1.069,
}


def econ():
    """econ.cpp:15 の忠実移植。"""
    n = ECEDY + 1
    ridum = np.zeros(n)
    ci0dum = np.zeros(n)
    jh_kaite = np.zeros(n)
    koujor = np.zeros(n)
    id_hh_juzen = np.zeros(n)
    id_hh_hon0 = np.zeros((n, 116))
    id_hh_honju8w = np.zeros((n, 116))
    id_hh_toku = np.zeros((n, 116))
    id_hh_siku = np.zeros((n, 116))
    arv_hh = np.zeros((n, 116))
    idr_hp_hon = np.zeros((n, 116))
    idg_hp_hon8w = np.zeros((n, 116))
    idr_hp_toku = np.zeros((n, 116))
    idg_hp_toku = np.zeros((n, 116))
    idg_hp_siku = np.zeros((n, 116))
    arv_hp = np.zeros((n, 116))
    rv = np.zeros((n, 24))

    marume_yr = 24.0                    # 癖 3. double で持つ

    # ---- econ-*.csv を読む ----
    fp = G.fp_map["econ"]
    for k in range(1, KE + 1):
        G.k = k
        result = fp.fgets()

        if result is not None and len(fp.line) > 2:
            vals = getnums(fp.line)
            kk = int(vals[0])
            assert k == kk, "econ: k = %d, kk = %d" % (k, kk)

            ridum[k] = vals[1] * 1.0e-2
            G.hdum[k] = vals[5] * 1.0e-2
            ci0dum[k] = vals[6] * 1.0e-2
        else:
            ridum[k] = ridum[k - 1]
            G.hdum[k] = G.hdum[k - 1]
            ci0dum[k] = ci0dum[k - 1]

        G.ri[k] = (1.0 + ridum[k]) * (1.0 + ci0dum[k]) - 1.0
        G.h[k] = (1.0 + G.hdum[k]) * (1.0 + ci0dum[k]) - 1.0
        G.ci0[k] = ci0dum[k]

        # 癖 4. 2001〜2022年度は実績で上書き
        j = _JISSEKI.get(k)
        if j is not None:
            G.ri[k] = j[0] * 1.0e-2
            G.h[k] = j[1] * 1.0e-2

    tamari_ci = -1.7e-2

    # ---- 2004年度の初期値 ----
    id_hh_juzen[4] = 0.986
    for x, v in _HON0_2004.items():
        id_hh_hon0[4][x] = v

    id_hh_honju8w[4][67] = std_max(
        std_max(id_hh_juzen[4], id_hh_hon0[4][67]), id_hh_hon0[4][67] * 0.8)

    id_hh_toku[4][67] = 1.003
    id_hh_siku[4][67] = std_max(id_hh_honju8w[4][67], id_hh_toku[4][67])

    idr_hp_hon[4][67] = 1.000
    idg_hp_hon8w[4][67] = 7809
    idr_hp_toku[4][67] = 0.988
    idg_hp_toku[4][67] = c_round(idr_hp_toku[4][67] * 8042)
    idg_hp_siku[4][67] = std_max(idg_hp_hon8w[4][67], idg_hp_toku[4][67])

    for x in range(68, 116):
        if x >= 76:
            id_hh_hon0[4][x] = id_hh_hon0[4][75]

        id_hh_honju8w[4][x] = std_max(
            std_max(id_hh_juzen[4], id_hh_hon0[4][x]),
            id_hh_hon0[4][67] * 0.8)
        id_hh_toku[4][x] = id_hh_toku[4][67]
        id_hh_siku[4][x] = std_max(id_hh_honju8w[4][x], id_hh_toku[4][x])

        idr_hp_hon[4][x] = idr_hp_hon[4][67]
        idg_hp_hon8w[4][x] = idg_hp_hon8w[4][67]
        idr_hp_toku[4][x] = idr_hp_toku[4][67]
        idg_hp_toku[4][x] = idg_hp_toku[4][67]
        idg_hp_siku[4][x] = idg_hp_siku[4][67]

    G.jz_shk[4] = roundn(0.917 / 0.990, 3)
    G.dir[4] = 0.980

    ci_kijun = 1.0

    _jitsuchin_kashobun(jh_kaite, koujor)

    # ---- 2005年度から順に改定率を積む ----
    for k in range(5, KE + 1):
        kaite_ci = G.ci0[k - 1]
        kaite_hh = (1.0 + kaite_ci) * jh_kaite[k] * koujor[k] - 1.0

        kaite_cird = roundn(G.ci0[k - 1], 3)

        jh_kaite_k_rd = roundn(jh_kaite[k], 3)
        koujour_k_rd = roundn(koujor[k], 3)

        kaite_hhrd = (1.0 + kaite_cird) * jh_kaite_k_rd * koujour_k_rd - 1.0
        kaite_hhrd = roundn(kaite_hhrd, 3)

        hhd = kaite_hh
        cid = kaite_ci

        # 癖 6. `k >= 21` かつ `hhd >= cid` のときは何もしない
        if k < 21:
            if hhd < cid and hhd < 0.0:
                kaite_hh = std_min(cid, 0.0)
            if hhd < cid and cid > 0.0:
                kaite_ci = std_max(hhd, 0.0)
        elif hhd < cid:
            kaite_ci = hhd

        # 癖 7. 丸めない版（たまりが解消したあと）
        if tamari_ci >= 0.0 and k > marume_yr:
            if k >= 21:
                G.jz_shk[k] = (G.jz_shk[k - 1] / (1.0 + G.ci0[k - 1])
                               / jh_kaite[k])
            else:
                if hhd < cid:
                    if hhd < 0.0 and cid < 0.0:
                        G.jz_shk[k] = G.jz_shk[k - 1] / (1.0 + G.ci0[k - 1])
                    elif hhd < 0.0 and cid >= 0.0:
                        G.jz_shk[k] = G.jz_shk[k - 1]
                    else:
                        G.jz_shk[k] = (G.jz_shk[k - 1] / (1.0 + G.ci0[k - 1])
                                       / jh_kaite[k])
                else:
                    G.jz_shk[k] = (G.jz_shk[k - 1] / (1.0 + G.ci0[k - 1])
                                   / jh_kaite[k])

        hhd = kaite_hhrd
        cid = kaite_cird

        if k < 21:
            if hhd < cid and hhd < 0.0:
                kaite_hhrd = std_min(cid, 0.0)
            if hhd < cid and cid > 0.0:
                kaite_cird = std_max(hhd, 0.0)
        elif hhd < cid:
            kaite_cird = hhd

        # 癖 7. 丸める版
        if tamari_ci < 0.0 or k <= marume_yr:
            if k >= 21:
                _jz_shk_prev = G.jz_shk[k - 1]
                _ci_prev = (1.0 + G.ci0[k - 1])
                _jh_kaite_rd = roundn(jh_kaite[k], 3)
                _jz_shk_tmp = (_jz_shk_prev / _ci_prev) / _jh_kaite_rd
                G.jz_shk[k] = roundn(_jz_shk_tmp, 3)
            else:
                if hhd < cid:
                    if hhd < 0.0 and cid < 0.0:
                        _jz_shk_tmp = (G.jz_shk[k - 1]
                                       / (1.0 + G.ci0[k - 1]))
                        G.jz_shk[k] = roundn(_jz_shk_tmp, 3)
                    elif hhd < 0.0 and cid >= 0.0:
                        G.jz_shk[k] = G.jz_shk[k - 1]
                    else:
                        _jz_shk_prev = G.jz_shk[k - 1]
                        _ci_prev = (1.0 + G.ci0[k - 1])
                        _jh_kaite_rd = roundn(jh_kaite[k], 3)
                        _jz_shk_tmp = (_jz_shk_prev / _ci_prev) / _jh_kaite_rd
                        G.jz_shk[k] = roundn(_jz_shk_tmp, 3)
                else:
                    _jz_shk_prev = G.jz_shk[k - 1]
                    _ci_prev = (1.0 + G.ci0[k - 1])
                    _jh_kaite_rd = roundn(jh_kaite[k], 3)
                    _jz_shk_tmp = (_jz_shk_prev / _ci_prev) / _jh_kaite_rd
                    G.jz_shk[k] = roundn(_jz_shk_tmp, 3)

        if k >= 7:
            kaite_hp = kaite_hh
            kaite_hprd = kaite_hhrd
        else:
            kaite_hp = kaite_ci
            kaite_hprd = kaite_cird

        ci_kijun = roundn(ci_kijun * (1.0 + G.ci0[k - 1]), 3)

        # 癖 8. ここから `hhd` `cid` は「特例水準の下げ幅」に変わる
        if ci_kijun < 1.0:
            cid = ci_kijun - 1.0
            ci_kijun = 1.0
        else:
            cid = 0.0
        hhd = cid

        if G.flg_kaisho == 2:
            if k == 13 or k == 14:
                if k == 13:
                    # 癖 5. 浮動小数の等値比較。どちらも roundn(.., 3) 済み
                    assert cid == kaite_hhrd and cid == kaite_cird, (
                        "econ: k=13 の assert（cid=%r hhrd=%r cird=%r）"
                        % (cid, kaite_hhrd, kaite_cird))
                hhd = std_min(1.0, roundn((1.0 + kaite_hhrd) * 0.99, 3)) - 1.0
                cid = std_min(1.0, roundn((1.0 + kaite_cird) * 0.99, 3)) - 1.0
            elif k >= 15:
                hhd = -1.0
                cid = -1.0

        if tamari_ci < 0.0 or k <= marume_yr:
            id_hh_juzen[k] = roundn(id_hh_juzen[k - 1] * (1.0 + kaite_cird), 4)
            id_hh_hon0[k][67] = roundn(
                id_hh_hon0[k - 1][67] * (1.0 + kaite_hhrd), 4)

            for x in range(68, 116):
                id_hh_hon0[k][x] = roundn(
                    id_hh_hon0[k - 1][x - 1] * (1.0 + kaite_cird), 4)
            G.dir[k] = roundn(G.dir[k - 1] * roundn(koujor[k], 3), 3)
        else:
            id_hh_juzen[k] = id_hh_juzen[k - 1] * (1.0 + kaite_ci)
            id_hh_hon0[k][67] = id_hh_hon0[k - 1][67] * (1.0 + kaite_hh)
            for x in range(68, 116):
                id_hh_hon0[k][x] = id_hh_hon0[k - 1][x - 1] * (1.0 + kaite_ci)
            G.dir[k] = G.dir[k - 1] * koujor[k]

        id_hh_honju8w[k][67] = std_max(
            std_max(id_hh_juzen[k], id_hh_hon0[k][67]),
            id_hh_hon0[k][67] * 0.8)

        id_hh_toku[k][67] = roundn(id_hh_toku[k - 1][67] * (1.0 + hhd), 4)
        if k == 6:
            id_hh_toku[k][67] = 0.9999

        id_hh_siku[k][67] = std_max(id_hh_honju8w[k][67], id_hh_toku[k][67])

        if id_hh_honju8w[k][67] < id_hh_toku[k][67]:
            arv_hh[k][67] = 1.0 + hhd
        elif (k <= marume_yr
              and id_hh_honju8w[k - 1][67] >= id_hh_toku[k - 1][67]):
            arv_hh[k][67] = roundn(
                id_hh_siku[k][67] / id_hh_siku[k - 1][67], 3)
        else:
            arv_hh[k][67] = id_hh_siku[k][67] / id_hh_siku[k - 1][67]

        if (idg_hp_hon8w[k - 1][67] < idg_hp_toku[k - 1][67]
                or k <= marume_yr):
            idr_hp_hon[k][67] = roundn(
                idr_hp_hon[k - 1][67] * (1.0 + kaite_hprd), 3)
            idg_hp_hon8w[k][67] = c_round(idr_hp_hon[k][67] * 7809)
        else:
            idr_hp_hon[k][67] = idr_hp_hon[k - 1][67] * (1.0 + kaite_hp)
            idg_hp_hon8w[k][67] = idg_hp_hon8w[k - 1][67] * (1.0 + kaite_hp)

        idr_hp_toku[k][67] = roundn(idr_hp_toku[k - 1][67] * (1.0 + hhd), 3)
        idg_hp_toku[k][67] = c_round(idr_hp_toku[k][67] * 8042)

        idg_hp_siku[k][67] = std_max(idg_hp_hon8w[k][67], idg_hp_toku[k][67])

        if idg_hp_hon8w[k][67] < idg_hp_toku[k][67]:
            arv_hp[k][67] = 1.0 + hhd
        elif (k <= marume_yr
              and idg_hp_hon8w[k - 1][67] >= idg_hp_toku[k - 1][67]):
            arv_hp[k][67] = roundn(
                idg_hp_siku[k][67] / idg_hp_siku[k - 1][67], 3)
        else:
            arv_hp[k][67] = idg_hp_siku[k][67] / idg_hp_siku[k - 1][67]

        for x in range(68, 116):
            id_hh_honju8w[k][x] = std_max(
                std_max(id_hh_juzen[k], id_hh_hon0[k][x]),
                id_hh_hon0[k][67] * 0.8)
            id_hh_toku[k][x] = roundn(
                id_hh_toku[k - 1][x - 1] * (1.0 + cid), 4)
            if k == 6:
                id_hh_toku[k][x] = 0.9999

            id_hh_siku[k][x] = std_max(id_hh_honju8w[k][x], id_hh_toku[k][x])
            if id_hh_honju8w[k][x] < id_hh_toku[k][x]:
                arv_hh[k][x] = 1.0 + cid
            elif (k <= marume_yr
                  and id_hh_honju8w[k - 1][x - 1]
                  >= id_hh_toku[k - 1][x - 1]):
                arv_hh[k][x] = roundn(
                    id_hh_siku[k][x] / id_hh_siku[k - 1][x - 1], 3)
            else:
                arv_hh[k][x] = id_hh_siku[k][x] / id_hh_siku[k - 1][x - 1]

            if idg_hp_hon8w[k - 1][x - 1] < idg_hp_toku[k - 1][x - 1]:
                idr_hp_hon[k][x] = roundn(
                    idr_hp_hon[k - 1][x - 1] * (1.0 + kaite_cird), 3)
                idg_hp_hon8w[k][x] = c_round(
                    std_max(idr_hp_hon[k][x], idr_hp_hon[k][67] * 0.8) * 7809)
            else:
                idr_hp_hon[k][x] = (idr_hp_hon[k - 1][x - 1]
                                    * (1.0 + kaite_ci))
                idg_hp_hon8w[k][x] = std_max(
                    idg_hp_hon8w[k][67] * 0.8,
                    idg_hp_hon8w[k - 1][x - 1] * (1.0 + kaite_ci))
            idr_hp_toku[k][x] = roundn(
                idr_hp_toku[k - 1][x - 1] * (1.0 + cid), 3)
            idg_hp_toku[k][x] = c_round(idr_hp_toku[k][x] * 8042)

            idg_hp_siku[k][x] = std_max(idg_hp_hon8w[k][x],
                                        idg_hp_toku[k][x])
            if idg_hp_hon8w[k][x] < idg_hp_toku[k][x]:
                arv_hp[k][x] = 1.0 + cid
            elif (k <= marume_yr
                  and idg_hp_hon8w[k - 1][x - 1]
                  >= idg_hp_toku[k - 1][x - 1]):
                arv_hp[k][x] = roundn(
                    idg_hp_siku[k][x] / idg_hp_siku[k - 1][x - 1], 3)
            else:
                arv_hp[k][x] = (idg_hp_siku[k][x]
                                / idg_hp_siku[k - 1][x - 1])

        if tamari_ci < 0.0 or k <= marume_yr:
            G.hh[k] = kaite_hhrd
            G.ci[k] = kaite_cird
        else:
            G.hh[k] = kaite_hh
            G.ci[k] = kaite_ci

        if id_hh_juzen[k] < id_hh_toku[k][67]:
            G.ci2[k][67] = hhd
        elif id_hh_juzen[k - 1] < id_hh_toku[k - 1][67]:
            G.ci2[k][67] = id_hh_juzen[k] / id_hh_toku[k - 1][67] - 1.0
        else:
            if G.chinsura == 1 and k >= 21:
                G.ci2[k][67] = G.ci[k]
            else:
                if hhd < 0.0 and cid > 0.0:
                    G.ci2[k][67] = 0.0
                else:
                    G.ci2[k][67] = G.ci[k]

        for x in range(68, 116):
            if id_hh_juzen[k] < id_hh_toku[k][x]:
                G.ci2[k][x] = cid
            elif id_hh_juzen[k - 1] < id_hh_toku[k - 1][x - 1]:
                G.ci2[k][x] = (id_hh_juzen[k] / id_hh_toku[k - 1][x - 1]
                               - 1.0)
            else:
                G.ci2[k][x] = G.ci[k]

        if idg_hp_hon8w[k - 1][67] < idg_hp_toku[k - 1][67]:
            G.hp2[k][67] = arv_hp[k][67] - 1.0
        elif k <= marume_yr:
            G.hp2[k][67] = kaite_hprd
        else:
            G.hp2[k][67] = kaite_hp

        for x in range(68, 116):
            if idg_hp_hon8w[k - 1][x - 1] < idg_hp_toku[k - 1][x - 1]:
                G.hp2[k][x] = arv_hp[k][x] - 1.0
            elif k <= marume_yr:
                G.hp2[k][x] = kaite_cird
            else:
                G.hp2[k][x] = kaite_ci

        tamari_ci = roundn(tamari_ci + kaite_cird - cid, 3)

    G.hh2_1999 = 0.4e-2
    G.hh2_2000 = 0.7e-2
    G.hh2_2001 = 0.8e-2

    for k in range(1, 5):
        G.k = k
        G.ci[k] = 0.0
        if k == 3 or k == 4:
            G.ci[k] = G.ci0[k - 1]

        for x in range(67, 116):
            G.ci2[k][x] = G.ci[k]
            G.hp2[k][x] = G.ci[k]

    # ---- 給付種別ごとの改定率 ----
    for j in range(1, 24):
        for k in range(1, KE + 1):
            if j <= 14 and j != 13:
                if k <= 3:
                    rv[k][j] = G.ci[k]
                    if k == 1 or k == 2:
                        rv[k][j] = 0.0
                elif k == 4:
                    if j == 1 or j == 10:
                        rv[k][j] = (1.0 + G.ci0[3]) * roundn(
                            (1.0 + G.hh2_1999) * (1.0 + G.hh2_2000)
                            * (1.0 + G.hh2_2001), 3)
                        rv[k][j] = roundn(rv[k][j], 3) - 1.0
                    else:
                        rv[k][j] = G.hp2[k][67]
                else:
                    if j == 1 or j == 10:
                        rv[k][j] = G.hh[k]
                    else:
                        rv[k][j] = G.hp2[k][67]
            elif j == 13:
                rv[k][j] = 0.0
            else:
                rv[k][j] = rv[k][_SAME[j]]

    # ---- 累積 ----
    G.ad[KIJUN] = 1.0
    for k in range(KIJUN + 1, KE + 1):
        G.k = k
        G.ad[k] = G.ad[k - 1] * (1.0 + G.h[k])
        if k <= marume_yr:
            G.ad[k] = roundn(G.ad[k], 3)

    G.ad2[4] = 0.988
    for k in range(5, KIJUN + 1):
        if k == 15:
            G.ad2[k] = G.ad2[k - 1] * (1.0 + G.hp2[k][67]) * 0.991
        elif k == 19:
            G.ad2[k] = G.ad2[k - 1] * (1.0 + G.hp2[k][67]) * 0.995
        elif k == 20:
            G.ad2[k] = G.ad2[k - 1] * (1.0 + G.hp2[k][67]) * 0.999
        else:
            G.ad2[k] = G.ad2[k - 1] * (1.0 + G.hp2[k][67])
        if k <= marume_yr:
            G.ad2[k] = roundn(G.ad2[k], 3)

    for j in range(1, 24):
        G.bd[KIJUN][j] = 1.0
        for k in range(KIJUN + 1, KE + 1):
            G.bd[k][j] = G.bd[k - 1][j] * (1.0 + rv[k][j])
            if k <= marume_yr:
                G.bd[k][j] = roundn(G.bd[k][j], 3)

    # ---- kaitea / kaiteb ----
    # 癖 1. `if(pseid == 0)` の前に引くので、厚年以外では None が入る
    fp_a = G.fp_map.setdefault("kaitea", None)
    fp_b = G.fp_map.setdefault("kaiteb", None)
    if G.kaite == 1:
        if G.pseid == 0:
            for k in range(5, FLKE + 1):
                # 癖 9. `else` の枝（0 埋め）には届かない
                if 5 <= k <= KE:
                    vals_hh = [arv_hh[k][x] for x in range(67, 116)]
                    vals_hp = [arv_hp[k][x] for x in range(67, 116)]
                else:
                    vals_hh = [0.0] * (115 - 67 + 1)
                    vals_hp = [0.0] * (115 - 67 + 1)
                assert len(vals_hh) == 115 - 67 + 1
                assert len(vals_hp) == 115 - 67 + 1

                # 癖 2. kaiteb ← arv_hh、kaitea ← arv_hp
                fp_b.write("%d,%s\n" % (k, join(vals_hh)))
                fp_a.write("%d,%s\n" % (k, join(vals_hp)))

    # ---- prtfil ----
    fp_fil = G.fp_map["prtfil"]
    fp_fil.write("経済的要素\n")
    fp_fil.write("年度,利回り,賃金,物価,改定（比例）,改定率（加給）,"
                 "改定率（基礎）,改定率（物価）\n")
    for k in range(1, KE + 1):
        fp_fil.write("%5d,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f\n"
                     % (k, G.ri[k], G.h[k], G.ci[k], rv[k][1], rv[k][4],
                        rv[k][14], G.ci2[k][67]))


def _jitsuchin_kashobun(jh_kaite, koujor):
    """econ.cpp:554 の `jitsuchin_kashobun`。

    実質賃金上昇率の3年平均（幾何平均）と、可処分所得割合の変化率。
    `namespace seps` の外にある自由関数なので `static` ではない。
    """
    for k in range(5, KE + 1):
        h_4_3_2 = ((1.0 + G.hdum[k - 4]) * (1.0 + G.hdum[k - 3])
                   * (1.0 + G.hdum[k - 2]))
        jh_kaite[k] = math.pow(h_4_3_2, 1.0 / 3.0)

    prema = np.zeros(ECEDY + 1)
    prema[3] = 13.58e-2

    for k in range(4, KE + 1):
        prema[k] = prema[k - 1] + 0.354e-2
        if prema[k] > 18.3e-2:
            prema[k] = 18.3e-2

    for k in range(5, KE + 1):
        if k <= 6:
            koujor[k] = 1.0
        else:
            koujor[k] = ((0.910 - prema[k - 3] / 2.0)
                         / (0.910 - prema[k - 4] / 2.0))
