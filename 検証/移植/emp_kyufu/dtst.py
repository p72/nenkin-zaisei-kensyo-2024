# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/dtst.cpp の忠実移植（足元の基礎数の読み込みと整理）
========================================================================
629 行。②でいちばん長い1関数。種別（`s` = 1 男 / 2 女 / 3 男女計）
ごとに1回呼ばれ、**2021年度の実績（足元）**を読んで推計の出発点を作る。

やること
--------
1. 計算用の配列を 0 で埋める（`subc1`〜`subc5` を 20 回）
2. `hk2021-{s}.csv` から**被保険者**の基礎数を読む（`subrh2/4/5` で 77 ブロック）
   → `g` `ge` `gpt` `bb` `bbpt` `z` `ze` `w` `we`
3. 区分の付け替え（`z[…][3]` に `[4]` を足して以降を1つずつ繰り上げるなど）
4. `jk2021-{s}.csv` から**受給権者**の基礎数を読む（`subrj3/4/5` で 38 ブロック）
   → `r` `f` `f_hik` `f_min` `hn` `wn`
5. 115歳を114歳に寄せ、「計」から繰上げ繰下げの内訳を引いて残りを出す
6. 繰上げ減額・繰下げ増額・加給・有子割合で**割り戻して**、
   減額前・加算前の1人あたり年金額にする
7. `set_tmsij()` の補正率（実績に合わせる係数）を掛ける
8. 従前額保障（`f[…][10]`）を賃金・物価の実績で足元まで引き直す
9. パート（`w[…][2]` `[3]`）を按分で作る

読み込みの2つのヘルパは別ファイル（`subrh.py` `subrj.py`）。

`tamari` が 0 のまま使われる
----------------------------
```c
double tamari = 0;
...
f.AT(x, xx, i, j) = f.AT(x, xx, i, j) * hikrate * (1.0 - tamari);
```

`tamari` に代入するコードは**どこにも無い**。`(1.0 - tamari)` は
必ず 1.0 なので掛け算1回が無駄になるだけ。`econ.cpp` の
`tamari_ci`（物価下落のたまり）を持ってくるつもりだったと読める。
`検証/原本の不具合.md` の D4。

空の分岐には意味がある
----------------------
```c
if(j == 1) {
}
else if(j == 10) { … }
else { f_min.AT(x, xx, i, j) = f.AT(x, xx, i, j) * 0.80; }
```

`f_min[…][1]` は `jk` ファイルから直に読んでいる
（`subrj4(fpj, 3, f_min, 1)`）ので、`f * 0.80` で上書きしては
いけない。**空の分岐はそのための書き方**で、消すと結果が変わる。

一方、下の2つは結果を変えない（同 F15）。

```c
} else {
  z.AT(x, t, i, j) = z.AT(x, t, i, j);      /* 自分自身 */
  ze.AT(x, t, i, j) = ze.AT(x, t, i, j);
}
```

```c
pshn.AT(x, xx, i) = r.AT(x, xx, i) * tmx;
pshn.AT(x, xx, i) = r.AT(x, xx, i) * tmx;   /* 1文字違わず2回 */
```

どちらも `key == 12` の過去分試算の枝にある。移植版はコメントにした。

`f_min` だけ条件が付いていない
------------------------------
```c
FOR(kk, 5, KIJUN) {
  if(KIJUN - x >= kk - 67) {
    f.AT(x, xx, i, j) = f.AT(x, xx, i, j) * (1.0 + hh.AT(kk)) / (1.0 + ci.AT(kk));
  }
  f_min.AT(x, xx, i, j) = f_min.AT(x, xx, i, j) * (1.0 + hh.AT(kk)) / (1.0 + ci.AT(kk));
}
```

`f`（従前額保障）は「その生年が対象になる年度から」掛けるのに、
`f_min`（8割の下限）は**生年に関係なく 2005〜2021年度の17年ぶん
全部**掛ける。同 E25。

ベクトル化について
------------------
要素ごとの演算はまとめても**各要素にかかる演算の順序が変わらない**
ので、ビット一致は保てる。この関数でいちばん重い

    FOR(x, 0, 115) FOR(xx, 0, 10) FOR(i, 1, 13) FOR(j, 1, 23)

の 38 万回は、`j` で分岐するだけなので `j` ごとに
`(x, xx, i)` をまとめて処理する。**掛け算の並びは崩さない**
（`f * a * b * c / d` を `f * (a*b*c/d)` にすると別の値になる）。

「計」から内訳を引く

    FOR(i, 1, 4) FOR(xx, 1, 10) r.AT(x, 0, i) -= r.AT(x, xx, i);

は縮約（逐次の引き算）なので、`xx` のループだけは残して
`x` と `i` と `j` をまとめる。`xx` を外に出しても各セルの
引き算の順番は 1 → 10 のまま変わらない。
"""
import numpy as np

from glva import G
from sepsstd import std_max, std_min, subc
from setconst import KIJUN
from sknr import sknr
from subrh import subrh2, subrh4, subrh5
from subrj import subrj3, subrj4, subrj5

__all__ = ["dtst"]

# `f`（1人あたり年金額）の第4添字のうち、従前額保障が入るもの
J_JUZEN = 10


def dtst():
    """dtst.cpp:12 の忠実移植。"""
    wn = np.zeros((116, 11, 14, 5, 2))
    tamari = 0.0                        # 代入するコードが無い（D4）

    subc(G.g, 14, 115, 0, 100)
    subc(G.ge, 14, 115, 0, 100)
    subc(G.gpt, 14, 115, 0, 100)
    subc(G.bb, 14, 115, 0, 100)
    subc(G.bbpt, 14, 115, 0, 100)
    subc(G.z, 14, 115, 0, 100, 0, 1, 0, 9)
    subc(G.ze, 14, 115, 0, 100, 0, 1, 0, 9)
    subc(G.w, 14, 115, 0, 100, 0, 0, 0, 7, 0, 3)
    subc(G.we, 14, 115, 0, 100, 0, 0, 0, 7, 0, 3)
    subc(G.psz, 14, 115, 0, 100, 0, 1, 0, 7)
    subc(G.psze, 14, 115, 0, 100, 0, 1, 0, 7)

    subc(G.gd, 55, 65, 0, 100)
    subc(G.r, 0, 115, 0, 15, 1, 13)
    subc(G.f, 0, 115, 0, 15, 1, 13, 1, 23)
    subc(G.f_min, 0, 115, 0, 15, 1, 13, 1, 23)
    subc(G.f_hik, 0, 115, 0, 15, 1, 13, 1, 23)
    subc(G.hn, 0, 115, 0, 15, 1, 13, 1, 4)
    subc(G.pshn, 0, 115, 0, 15, 1, 13)

    subc(G.rsen, 60, 70)
    subc(G.hnsen, 60, 70, 1, 2)
    subc(G.pshnsen, 60, 70)
    subc(G.fsen, 60, 70, 1, 23)
    subc(G.fsenmin, 60, 70, 1, 23)
    subc(G.fsenhik, 60, 70, 1, 23)

    subc(G.fkouzai2, 70, 84, 0, 10, 1, 2)

    subc(wn, 0, 115, 0, 10, 1, 13, 1, 4, 0, 1)

    # ------------------------------------------------------------------
    # 被保険者の基礎数（hk ファイル）
    # ------------------------------------------------------------------
    if G.s == 1:
        fph = G.fp_map["hk-1"]
    if G.s == 2:
        fph = G.fp_map["hk-2"]
    if G.s == 3:
        assert G.pseid == 0
        fph = G.fp_map["hk-3"]

    fph.skip(3)
    subrh2(fph, 0, G.g, "g")
    subrh2(fph, 0, G.ge, "ge")
    subrh2(fph, 0, G.gpt, "gpt")
    subrh2(fph, 0, G.bb, "bb")
    subrh2(fph, 0, G.bbpt, "bbpt")

    for i in range(0, 1 + 1):
        for j in range(0, 8 + 1):
            subrh4(fph, 0, G.z, "z", i, j)

    for i in range(0, 1 + 1):
        for j in range(0, 8 + 1):
            subrh4(fph, 0, G.ze, "ze", i, j)

    for ii in range(2, 3 + 1):
        subrh5(fph, 0, G.w, "w", 0, 0, ii)
    for j in range(0, 6 + 1):
        subrh5(fph, 0, G.w, "w", 0, j, 0)
        subrh5(fph, 0, G.w, "w", 0, j, 1)
        if j == 4:
            subrh5(fph, 0, G.w, "w", 0, j, 2)
            subrh5(fph, 0, G.w, "w", 0, j, 3)

    for ii in range(2, 3 + 1):
        subrh5(fph, 0, G.we, "we", 0, 0, ii)
    for j in range(0, 6 + 1):
        subrh5(fph, 0, G.we, "we", 0, j, 0)
        subrh5(fph, 0, G.we, "we", 0, j, 1)
        if j == 4:
            subrh5(fph, 0, G.we, "we", 0, j, 2)
            subrh5(fph, 0, G.we, "we", 0, j, 3)

    # ------------------------------------------------------------------
    # 区分の付け替えと「計」の整合
    # ------------------------------------------------------------------
    for x in range(15, 74 + 1):
        for t in range(0, 50 + 1):
            for i in range(0, 1 + 1):
                for v in (G.z, G.ze):
                    v[x, t, i, 9] = v[x, t, i, 3]
                    v[x, t, i, 3] = v[x, t, i, 3] + v[x, t, i, 4]
                    v[x, t, i, 4] = v[x, t, i, 5]
                    v[x, t, i, 5] = v[x, t, i, 6]
                    v[x, t, i, 6] = v[x, t, i, 7]
                    v[x, t, i, 7] = v[x, t, i, 8]
                    v[x, t, i, 8] = 0.0

                if KIJUN - x > -54:
                    if G.z[x, t, i, 1] > 0.0:
                        G.z[x, t, i, 1] = 0.0
                    if G.ze[x, t, i, 1] > 0.0:
                        G.ze[x, t, i, 1] = 0.0

                for v in (G.z, G.ze):
                    tmp = (v[x, t, i, 1] + v[x, t, i, 2]
                           + v[x, t, i, 3] + v[x, t, i, 4])
                    if v[x, t, i, 0] < tmp:
                        v[x, t, i, 0] = tmp
                    elif v[x, t, i, 0] > tmp:
                        if tmp > 0.0:
                            tmp = v[x, t, i, 0] / tmp
                            v[x, t, i, 0] = 0.0
                            for j in range(1, 4 + 1):
                                v[x, t, i, j] = v[x, t, i, j] * tmp
                                v[x, t, i, 0] = v[x, t, i, 0] + v[x, t, i, j]
                        else:
                            v[x, t, i, 0] = 0.0

            for ii in range(0, 1 + 1):
                for v in (G.w, G.we):
                    v[x, t, 0, 7, ii] = v[x, t, 0, 3, ii]
                    v[x, t, 0, 3, ii] = v[x, t, 0, 3, ii] + v[x, t, 0, 4, ii]
                    v[x, t, 0, 4, ii] = v[x, t, 0, 5, ii]
                    v[x, t, 0, 5, ii] = 0.0
                    v[x, t, 0, 0, ii] = v[x, t, 0, 0, ii] - v[x, t, 0, 4, ii]

            # ii = 2, 3（パート）は引き算だけ
            G.we[x, t, 0, 0, 2] = G.we[x, t, 0, 0, 2] - G.we[x, t, 0, 4, 2]
            G.we[x, t, 0, 0, 3] = G.we[x, t, 0, 0, 3] - G.we[x, t, 0, 4, 3]

    print("被保険者の読み込みが終わりました")

    # ------------------------------------------------------------------
    # 受給権者の基礎数（jk ファイル）
    # ------------------------------------------------------------------
    if G.s == 1:
        fpj = G.fp_map["jk-1"]
    if G.s == 2:
        fpj = G.fp_map["jk-2"]
    if G.s == 3:
        assert G.pseid == 0
        fpj = G.fp_map["jk-3"]

    fpj.skip(4)
    subrj3(fpj, 0, G.r)

    for j in range(1, 23 + 1):
        subrj4(fpj, 3, G.f, j)
    subrj4(fpj, 3, G.f_hik, 1)
    subrj4(fpj, 3, G.f_min, 1)
    for j in range(1, 4 + 1):
        subrj4(fpj, 0, G.hn, j)
    for jj in range(1, 4 + 1):
        subrj5(fpj, 3, wn, jj, 0)
        subrj5(fpj, 3, wn, jj, 1)

    print("受給権者の読み込みが終わりました")

    # 115歳を114歳に寄せる（要素ごとなのでまとめてよい）
    G.r[114, 0:11, 1:14] += G.r[115, 0:11, 1:14]
    G.r[115, 0:11, 1:14] = 0
    G.hn[114, 0:11, 1:14, 1:5] += G.hn[115, 0:11, 1:14, 1:5]
    G.hn[115, 0:11, 1:14, 1:5] = 0
    for v in (G.f, G.f_hik, G.f_min):
        v[114, 0:11, 1:14, 1:24] += v[115, 0:11, 1:14, 1:24]
    for v in (G.f, G.f_hik, G.f_min):
        v[115, 0:11, 1:14, 1:24] = 0

    # ------------------------------------------------------------------
    # 「計」から繰上げ繰下げの内訳を引いて残りを出す
    # `xx` は逐次の引き算なのでループを残す
    # ------------------------------------------------------------------
    for xx in range(1, 10 + 1):
        G.r[0:116, 0, 1:5] -= G.r[0:116, xx, 1:5]
        for v in (G.f, G.f_hik, G.f_min):
            v[0:116, 0, 1:5, 1:24] -= v[0:116, xx, 1:5, 1:24]
        G.hn[0:116, 0, 1:5, 1:5] -= G.hn[0:116, xx, 1:5, 1:5]
        wn[0:116, 0, 1:5, 1:5, 0] -= wn[0:116, xx, 1:5, 1:5, 0]
        wn[0:116, 0, 1:5, 1:5, 1] -= wn[0:116, xx, 1:5, 1:5, 1]

    # i = 5〜13 は繰上げ繰下げが無いので内訳を捨てる
    G.r[0:116, 1:11, 5:14] = 0.0
    for v in (G.f, G.f_hik, G.f_min):
        v[0:116, 1:11, 5:14, 1:24] = 0.0
    G.hn[0:116, 1:11, 5:14, 1:5] = 0.0
    wn[0:116, 1:11, 5:14, 1:5, 0] = 0.0
    wn[0:116, 1:11, 5:14, 1:5, 1] = 0.0

    if G.konen != 1:
        G.f[0:116, 0, 9, 12] = G.f[0:116, 0, 9, 12] * G.ema[G.s]

    # 旧法（1946年度より前の生まれ）の配偶者加給を子の加給に寄せる
    for x in range(0, 115 + 1):
        if KIJUN - x > -54:
            for i in range(1, 10 + 1):
                xxsl = slice(0, 11) if i < 5 else slice(0, 1)
                a1 = G.hn[x, xxsl, i, 1]
                m = a1 > 0.0
                G.hn[x, xxsl, i, 2] = np.where(
                    m, G.hn[x, xxsl, i, 2] + a1, G.hn[x, xxsl, i, 2])
                G.hn[x, xxsl, i, 1] = np.where(m, 0.0, a1)

    # ------------------------------------------------------------------
    # 減額前・加算前の1人あたり年金額に割り戻す
    # ------------------------------------------------------------------
    if G.konen == 1:
        _warimodoshi_kounen()
    else:
        for i in range(1, 13 + 1):
            if i == 5 or i == 6 or i == 10:
                G.f[0:116, 0:11, i, 19] = 0.0
                G.f[0:116, 0:11, i, 20] = 0.0
            if i == 13:
                for x in range(19, 115 + 1):
                    G.f[x, 0:11, i, 17] = (G.f[x, 0:11, i, 17]
                                           * G.rc[G.s, KIJUN, x])

    # ------------------------------------------------------------------
    # 実績に合わせる補正率
    # ------------------------------------------------------------------
    tmsi, tmsj, tmso = _set_tmsij()

    _TMSJ_JS = (4, 5, 23, 15, 16, 17, 18, 19, 20)
    _TMSI_JS = (1, 2, 3, 7, 8, 9, 10, 11, 12)

    for i in range(1, 13 + 1):
        for xx in range(0, 10 + 1):
            if i >= 5 and xx > 0:
                continue
            if i <= 8 and G.konen != 1:
                # x < 71 + KIJUN（= 92）の 16 番を落とす
                G.f[0:92, xx, i, 16] = 0.0
            for j in sorted(_TMSJ_JS):
                if (i >= 5 and i != 9 and i != 11) and j in (4, 5, 23):
                    G.f[0:116, xx, i, j] = G.f[0:116, xx, i, j] * tmso[j]
                else:
                    G.f[0:116, xx, i, j] = G.f[0:116, xx, i, j] * tmsj[j]

            if G.pseid != 2 and G.pseid != 3:
                for j in _TMSI_JS:
                    G.f[0:116, xx, i, j] = G.f[0:116, xx, i, j] * tmsi[i]
                G.f_min[0:116, xx, i, 1] = (G.f_min[0:116, xx, i, 1]
                                            * tmsi[i])
                G.f_hik[0:116, xx, i, 1] = (G.f_hik[0:116, xx, i, 1]
                                            * tmsi[i])

    # ------------------------------------------------------------------
    # 従前額保障を賃金・物価の実績で足元まで引き直す
    # `j` ごとに (x, xx, i) をまとめる。掛け算の並びは崩さない
    # ------------------------------------------------------------------
    XX = slice(0, 11)
    II = slice(1, 14)

    for j in range(1, 23 + 1):
        if j == 1:
            # 原本は空の分岐（F15）
            continue
        if j != J_JUZEN:
            G.f_min[0:116, XX, II, j] = G.f[0:116, XX, II, j] * 0.80
            continue

        # j == 10（従前額保障）
        for x in range(0, 115 + 1):
            G.f_hik[x, XX, II, j] = G.f[x, XX, II, j]

            v = G.f[x, XX, II, j] * G.hikrate * (1.0 - tamari)

            d = KIJUN - x
            if d == -70:
                v = v * 1.019
                v = v * 0.998
                v = v * 1.024
                v = v / 1.031
            elif d == -69:
                v = v * 1.042
                v = v * 0.996
                v = v * 1.025
                v = v / 1.031
            elif -68 <= d <= -66:
                v = v * 1.080
                v = v * 0.990
                v = v / 1.031
            elif d == -65:
                v = v * 1.080
                v = v * 0.990
                v = v * 1.004
                v = v / 1.031
            elif d == -64:
                v = v * 1.080
                v = v * 0.990
                v = v * 1.004
                v = v * 1.007
                v = v / 1.031
            elif d >= -63:
                v = v * 1.080
                v = v * 0.990
                v = v * 1.004
                v = v * 1.007
                v = v * 1.008
                v = v / 1.031

            vmin = G.f_hik[x, XX, II, j] * G.hikrate
            vmin = vmin * (1.0 - tamari)
            vmin = vmin * 1.080
            vmin = vmin * 0.990
            vmin = vmin * 1.004
            vmin = vmin * 1.007
            vmin = vmin * 1.008
            vmin = vmin / 1.031
            vmin = vmin * 0.80

            for kk in range(5, KIJUN + 1):
                # 原本は `f * (1.0 + hh[kk]) / (1.0 + ci[kk])`。
                # **先に `(1+hh)/(1+ci)` を括ると別の値になる**ので、
                # 掛けてから割る順を守る
                hk = 1.0 + G.hh[kk]
                ck = 1.0 + G.ci[kk]
                if d >= kk - 67:
                    v = v * hk
                    v = v / ck
                # f_min は生年に関係なく毎年掛ける（E25）
                vmin = vmin * hk
                vmin = vmin / ck

            G.f[x, XX, II, j] = v
            G.f_min[x, XX, II, j] = vmin

    # ------------------------------------------------------------------
    # パート（ii = 2, 3）を「計」の比で按分する
    # ------------------------------------------------------------------
    for v in (G.w, G.we):
        tot = v[14:116, 0:101, 0, 0, 0]
        m = tot > 1.0e-6
        for j in (0, 1, 2, 3, 7):
            base = v[14:116, 0:101, 0, j, 0]
            for ii in (2, 3):
                num = base * v[14:116, 0:101, 0, 0, ii]
                # ゼロ割りを避けるため、分母が小さいところは 0 にする
                with np.errstate(divide="ignore", invalid="ignore"):
                    r = num / tot
                v[14:116, 0:101, 0, j, ii] = np.where(m, r, 0.0)

    # ------------------------------------------------------------------
    # key = 12 の過去分試算（psly = -3）だけの処理
    # ------------------------------------------------------------------
    if G.key == 12 and G.psly == -3:
        _kako_bun(wn)

    # ------------------------------------------------------------------
    # hn の 3, 4 を 2 にまとめる
    # ------------------------------------------------------------------
    G.hn[0:116, 0:11, 1:14, 2] = (G.hn[0:116, 0:11, 1:14, 2]
                                  + G.hn[0:116, 0:11, 1:14, 3]
                                  + G.hn[0:116, 0:11, 1:14, 4])
    G.hn[0:116, 0:11, 1:14, 3] = 0.0
    G.hn[0:116, 0:11, 1:14, 4] = 0.0


def _warimodoshi_kounen():
    """dtst.cpp:285-338。`konen == 1`（厚生年金）の割り戻し。"""
    for i in range(1, 13 + 1):
        if i <= 2:
            ii = 1
        if 3 <= i <= 4:
            ii = 6
        if 5 <= i <= 8:
            ii = 2
        if i == 9:
            ii = 3
        if i == 10:
            ii = 4
        if 11 <= i <= 13:
            ii = 5

        for x in range(0, 115 + 1):
            sknr(G.k, x)
            G.xxr = max(60, G.xxr)
            G.xrb = max(60, G.xrb)
            xxr = G.xxr
            xrb = G.xrb

            for xx in range(0, 10 + 1):
                if i >= 5 and xx > 0:
                    continue
                if ii == 1 or ii == 6:
                    if xx <= 5:
                        if (x >= 60 and xrb > 60 and (65 - xx) >= 60
                                and (65 - xx) < xrb):
                            rbe = G.rigbe[G.s2, 65 - xx, xrb, 0]
                            G.f[x, xx, i, 1] = G.f[x, xx, i, 1] / rbe
                            G.f_hik[x, xx, i, 1] = G.f_hik[x, xx, i, 1] / rbe
                            G.f_min[x, xx, i, 1] = G.f_min[x, xx, i, 1] / rbe
                            # 報酬比例は xrb ではなく xxr で引く
                            G.f[x, xx, i, 3] = (G.f[x, xx, i, 3]
                                                / G.rigk[G.s2, 65 - xx,
                                                         xxr, 0])
                        if ((65 - xx) < xxr and x >= 65 - xx and x < 65
                                and xxr < 65):
                            G.f[x, xx, i, 2] = (G.f[x, xx, i, 2]
                                                / G.rigd[G.s2, 65 - xx,
                                                         xxr, 0])
                    else:
                        # 繰下げ（xx = 6〜10）は月 0.7% の増額を割り戻す
                        tmgbe = 1.0 + 0.007 * (xx - 5) * 12.0
                        G.f[x, xx, i, 1] = G.f[x, xx, i, 1] / tmgbe
                        G.f_hik[x, xx, i, 1] = G.f_hik[x, xx, i, 1] / tmgbe
                        G.f_min[x, xx, i, 1] = G.f_min[x, xx, i, 1] / tmgbe
                        G.f[x, xx, i, 3] = G.f[x, xx, i, 3] / tmgbe

                if G.kd[KIJUN, ii, 1, x] >= 1.0e-6:
                    kd1 = G.kd[KIJUN, ii, 1, x]
                    if 5 <= i <= 13:
                        G.f[x, xx, i, 4] = G.f[x, xx, i, 4] / kd1
                        G.f[x, xx, i, 23] = G.f[x, xx, i, 23] / kd1
                    G.f[x, xx, i, 19] = G.f[x, xx, i, 19] / kd1

                adt_ratio_3_2 = G.adt[3] / G.adt[2]
                kd_sum = (G.kd[KIJUN, ii, 2, x]
                          + G.kd[KIJUN, ii, 3, x] * adt_ratio_3_2)
                if kd_sum >= 1.0e-6:
                    if 5 <= i <= 13:
                        G.f[x, xx, i, 5] = G.f[x, xx, i, 5] / kd_sum
                    G.f[x, xx, i, 20] = G.f[x, xx, i, 20] / kd_sum
                    G.f[x, xx, i, 21] = G.f[x, xx, i, 21] / kd_sum

                if (i == 11 or i == 12) and x >= 19:
                    rc_kijun = G.rc[G.s, KIJUN, x]
                    if rc_kijun >= 1.0e-6:
                        G.f[x, xx, i, 14] = G.f[x, xx, i, 14] / rc_kijun
                        G.f[x, xx, i, 17] = G.f[x, xx, i, 17] / rc_kijun
                    if 1.0 - rc_kijun >= 1.0e-6:
                        G.f[x, xx, i, 18] = (G.f[x, xx, i, 18]
                                             / (1.0 - rc_kijun))


def _kako_bun(wn):
    """dtst.cpp:456-533。`key == 12 && psly == -3`（過去分試算）だけ。

    通常試算（`key == 11`）では走らない。
    """
    for x in range(15, G.xend + 1):
        for t in range(0, 50 + 1):
            for i in range(0, 1 + 1):
                for j in range(0, 6 + 1):
                    G.psz[x, t, i, j] = G.z[x, t, i, j]
                    G.psze[x, t, i, j] = G.ze[x, t, i, j]
                    if j == 0:
                        G.z[x, t, i, j] = (G.z[x, t, i, 1] + G.z[x, t, i, 2]
                                           + G.z[x, t, i, 9])
                        G.ze[x, t, i, j] = (G.ze[x, t, i, 1]
                                            + G.ze[x, t, i, 2]
                                            + G.ze[x, t, i, 9])
                    elif j == 3:
                        G.z[x, t, i, j] = G.z[x, t, i, 9]
                        G.ze[x, t, i, j] = G.ze[x, t, i, 9]
                    elif j == 4:
                        G.z[x, t, i, j] = 0.0
                        G.ze[x, t, i, j] = 0.0
                    # else は自分自身への代入（F15）なので書かない

            for j in range(0, 4 + 1):
                for ii in range(0, 3 + 1):
                    if j == 0:
                        G.w[x, t, 0, j, ii] = (G.w[x, t, 0, 1, ii]
                                               + G.w[x, t, 0, 2, ii]
                                               + G.w[x, t, 0, 7, ii])
                        G.we[x, t, 0, j, ii] = (G.we[x, t, 0, 1, ii]
                                                + G.we[x, t, 0, 2, ii]
                                                + G.we[x, t, 0, 7, ii])
                    elif j == 3:
                        G.w[x, t, 0, j, ii] = G.w[x, t, 0, 7, ii]
                        G.we[x, t, 0, j, ii] = G.we[x, t, 0, 7, ii]
                    elif j == 4:
                        G.w[x, t, 0, j, ii] = 0.0
                        G.we[x, t, 0, j, ii] = 0.0
                    # else は自分自身への代入（F15）

    for x in range(0, 115 + 1):
        for xx in range(0, 10 + 1):
            for i in range(1, 13 + 1):
                hn_sum = (G.hn[x, xx, i, 1] + G.hn[x, xx, i, 2]
                          + G.hn[x, xx, i, 3] + G.hn[x, xx, i, 4])
                if hn_sum > 1.0e-6:
                    tmx = (G.hn[x, xx, i, 1] + G.hn[x, xx, i, 2]) / hn_sum
                else:
                    tmx = 0.0
                tmx = std_max(0.0, std_min(1.0, tmx))

                wn_sum = (wn[x, xx, i, 1, 0] + wn[x, xx, i, 2, 0]
                          + wn[x, xx, i, 3, 0] + wn[x, xx, i, 4, 0])
                if wn_sum > 1.0e-6:
                    tmy = (wn[x, xx, i, 1, 0] + wn[x, xx, i, 2, 0]) / wn_sum
                else:
                    tmy = 0.0
                tmy = std_max(0.0, std_min(1.0, tmy))

                # 原本は同じ代入が2回並んでいる（F15）
                G.pshn[x, xx, i] = G.r[x, xx, i] * tmx

                for j in range(1, 23 + 1):
                    if j == 1 or j == 10:
                        G.f[x, xx, i, j] = G.f[x, xx, i, j] * tmy
                        G.f_min[x, xx, i, j] = G.f_min[x, xx, i, j] * tmy
                        G.f_hik[x, xx, i, j] = G.f_hik[x, xx, i, j] * tmy
                    else:
                        G.f[x, xx, i, j] = G.f[x, xx, i, j] * tmx
                        G.f_min[x, xx, i, j] = G.f_min[x, xx, i, j] * tmx


def _set_tmsij():
    """dtst.cpp:540-629 の `static void set_tmsij`。

    2021年度の実績に合わせる補正率。`i` は給付の種類（13通り）、
    `j` は年金額の内訳（23通り）。`tmso` は「老齢以外の `j = 4, 5, 23`」用。

    `flg_hantei != 0` だと全部 1.0 のまま（補正しない）。
    """
    # 原本は `VEC(double, 13)` で作って 1〜13（1〜23）だけ 1.0 にする。
    # **添字 0 は 0.0 のまま**（読まれないが、そろえておく）
    tmsi = np.ones(14)
    tmsj = np.ones(24)
    tmso = np.ones(24)
    tmsi[0] = 0.0
    tmsj[0] = 0.0
    tmso[0] = 0.0

    if G.flg_hantei != 0:
        return tmsi, tmsj, tmso

    if G.pseid == 0:
        tmsj[15] = 1.1711
        tmsj[16] = 0.9560
        tmsj[4] = 1.0021
        tmso[4] = 1.1608
    elif G.pseid == 1:
        tmsj[15] = 1.1199
        tmsj[16] = 0.1679
        tmsj[4] = 1.0000
        tmso[4] = 1.0005
    elif G.pseid == 4:
        tmsj[15] = 1.1212
        tmsj[16] = 0.2987
        tmsj[4] = 1.0000
        tmso[4] = 1.0003
    elif G.pseid == 5:
        tmsj[15] = 1.1199
        tmsj[16] = 0.2366
        tmsj[4] = 1.0000
        tmso[4] = 1.0001

    tmsj[5] = tmsj[4]
    tmsj[23] = tmsj[4]
    tmso[5] = tmso[4]
    tmso[23] = tmso[4]
    tmsj[17] = tmsj[15]
    tmsj[18] = tmsj[15]
    tmsj[19] = tmsj[15]
    tmsj[20] = tmsj[15]

    if G.pseid == 0:
        tmsi[1] = 1.0005
        tmsi[2] = 1.0030
        tmsi[3] = 1.0051
        tmsi[4] = 1.0089
        tmsi[5] = 0.9807
        tmsi[6] = 0.9853
        tmsi[7] = 1.0006
        tmsi[8] = 1.0001
        tmsi[9] = 0.9997
        tmsi[10] = 1.0129
        tmsi[11] = 1.0001
        tmsi[12] = 1.0000
        tmsi[13] = 1.0003
    elif G.pseid == 1:
        tmsi[1] = 0.9910
        tmsi[2] = 1.0198
        tmsi[3] = 0.9735
        tmsi[4] = 1.0195
        tmsi[9] = 1.0095
        tmsi[11] = 0.9624
    elif G.pseid == 4:
        tmsi[1] = 1.0004
        tmsi[2] = 1.0384
        tmsi[3] = 0.9859
        tmsi[4] = 0.9808
        tmsi[9] = 1.0539
        tmsi[11] = 1.0407
    elif G.pseid == 5:
        tmsi[1] = 1.0011
        tmsi[2] = 0.9920
        tmsi[3] = 0.9743
        tmsi[4] = 0.9767
        tmsi[9] = 1.0557
        tmsi[11] = 0.8044

    return tmsi, tmsj, tmso
