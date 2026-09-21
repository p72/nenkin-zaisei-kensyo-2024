# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/stat.cpp の忠実移植（年度間の平均と「計」の作成）
=====================================================================
344 行。`sepsd()` の最後に1回呼ばれ、年度**末**の値を年度**間**の
平均に直し、性別（`s = 0`）と給付の種類（`i = 0`）の「計」を作る。

    d3x [k][x][s][i][0]   年度末 → 前年度末との平均
    d3xs[…]               同（受給権者）
    kfprx[k][x][s][i][j]  基礎年金拠出金の算定対象（`j` = 0〜8）
    a / a60 / a65 / …     標準報酬総額を年度間の平均に
    ap / ap65 / …         被保険者数を同じく
    gee / geept           年度末の控えの「計」

年度間の平均の取り方が3通り
---------------------------
```c
if(pseid == 1 || pseid == 4) {
  a.AT(k, s) = (5.0*a.AT(k-1, s) + 7.0*a.AT(k, s)) / 12.0;
}
else if(pseid == 0 && (k == partyr3 || k == partyr4)) {
  a.AT(k, s) = (6.0*a.AT(k-1, s) + 6.0*adum.AT(k, s)) / 12.0;
}
else {
  a.AT(k, s) = (6.0*a.AT(k-1, s) + 6.0*a.AT(k, s)) / 12.0;
}
```

- 国家公務員共済・地方公務員共済は **5 : 7**（年度の途中で
  制度が変わった名残と読める）
- 厚生年金の適用拡大の年度（2024年10月と オプション）は
  **6 : 6 だが当年度は `adum`**（拡大前の値）を使う
- ほかは **6 : 6**（単純平均）

`6.0 * a / 12.0` は `a / 2.0` と**同じ値にならないことがある**
（`6.0 * a` が丸まる）。原本の書き方をそのまま写す。

`ap` 系は素直に `(ap[k-1] + ap[k]) / 2.0`。**`a` 系だけ 12分の
書き方**になっている。

`FOR(s, 1, 3)` がグローバルの `s` を隠す
----------------------------------------
```c
FOR(s, 1, 3) { … }     /* → for(int s = 1; s <= 3; s++) */
```

`_extension.h` の `FOR` は `for(int name = …)` と展開するので、
**グローバルの `s`（種別）を局所変数が隠す**。`stat()` を抜けたあと
グローバルの `s` は `sepsd()` が最後に入れた値のまま。

`kfprx` の列
------------
| `j` | 中身 |
|---|---|
| 0 | `d3x` の 13〜18 の合計 × `kk` |
| 1 | `d3x` の 13 × `kk` |
| 2 | 0 − 1 |
| 3〜5 | `nenbe65 == 1` のとき、`d3x` の 53〜58 で同じもの |
| 6〜8 | 同じく `kk2`（在職の65歳未満）で |

`kk` は `ee[1]`（`s != 3`）または `ee[2]`、ただし在職
（`i` が 2・4・6・8）で65歳未満なら `kk` を 0 にして `kk2` へ移す。

**`d3x` の 13〜18 には J2（地方公務員共済の 461.6518）が入っている。**
`検証/原本の不具合.md` の J2。

読み込み側の注意 — `stat` は標準ライブラリと名前がぶつかる
----------------------------------------------------------
Python には標準ライブラリの `stat` があり、`os` が起動時に読み込むので
`sys.modules["stat"]` は**必ず埋まっている**。`sys.path` の先頭に
`emp_kyufu/` を置いても、素の `import stat` は標準の方を返す。

呼ぶ側（`sepsd.py` とテストの走者）は

```python
import importlib.util as ilu
spec = ilu.spec_from_file_location("emp_kyufu_stat", ".../stat.py")
stat = ilu.module_from_spec(spec)
sys.modules["emp_kyufu_stat"] = stat
spec.loader.exec_module(stat)
```

とファイルを指して読み込む。`sys.modules` から標準の `stat` を
**外してはいけない**（`pathlib` や `tarfile` があとで
`import stat` したときにこちらを掴んでしまう）。
原本のファイル名を変えない方針を通すための回り道。
"""
from glva import G
from sepsstd import subc
from setconst import KE, KIJUN

__all__ = ["stat"]


def stat():
    """stat.cpp:5 の忠実移植。"""
    pseid = G.pseid
    nenbeex = G.nenbeex
    nenbe65 = G.nenbe65
    xa = G.xa

    d3x = G.d3x
    d3xs = G.d3xs
    kfprx = G.kfprx

    kk = [0.0] * 116
    kk2 = [0.0] * 116

    for k in range(KE, KIJUN - 1, -1):
        for s in range(1, 3 + 1):       # グローバルの s を隠す
            for i in range(1, 13 + 1):
                for x in range(115, 0 - 1, -1):
                    if x == 0:
                        d3x[k, x, s, i, 0] = d3x[k, x, s, i, 0] / 2.0
                        if nenbe65 == 1:
                            d3x[k, x, s, i, 34] = d3x[k, x, s, i, 34] / 2.0
                    else:
                        d3x[k, x, s, i, 0] = ((d3x[k - 1, x - 1, s, i, 0]
                                               + d3x[k, x, s, i, 0]) / 2.0)
                        if nenbe65 == 1:
                            d3x[k, x, s, i, 34] = (
                                (d3x[k - 1, x - 1, s, i, 34]
                                 + d3x[k, x, s, i, 34]) / 2.0)
                if nenbeex == 0:
                    for x in range(0, xa - 2 + 1):
                        d3x[k, xa - 1, s, i, 0] = (d3x[k, xa - 1, s, i, 0]
                                                   + d3x[k, x, s, i, 0])
                        d3x[k, x, s, i, 0] = 0.0

                        d3xs[k, xa - 1, s, i, 0] = (d3xs[k, xa - 1, s, i, 0]
                                                    + d3xs[k, x, s, i, 0])
                        d3xs[k, x, s, i, 0] = 0.0
                        if nenbe65 == 1:
                            d3x[k, xa - 1, s, i, 34] = (
                                d3x[k, xa - 1, s, i, 34]
                                + d3x[k, x, s, i, 34])
                            d3x[k, x, s, i, 34] = 0.0

                            d3xs[k, xa - 1, s, i, 34] = (
                                d3xs[k, xa - 1, s, i, 34]
                                + d3xs[k, x, s, i, 34])
                            d3xs[k, x, s, i, 34] = 0.0
                for j in range(0, 58 + 1):
                    if (j == 0 or j == 34
                            or (nenbe65 == 0 and j >= 35)):
                        continue
                    tmp = 0.0
                    for x in range(0, 115 + 1):
                        tmp += d3x[k, x, s, i, j]
                    if tmp < 1.0e-6:
                        for x in range(0, 115 + 1):
                            d3x[k, x, s, i, j] = 0.0
                    if nenbeex == 0:
                        for x in range(0, xa - 2 + 1):
                            d3x[k, xa - 1, s, i, j] = (
                                d3x[k, xa - 1, s, i, j] + d3x[k, x, s, i, j])
                            d3x[k, x, s, i, j] = 0.0

                            d3xs[k, xa - 1, s, i, j] = (
                                d3xs[k, xa - 1, s, i, j]
                                + d3xs[k, x, s, i, j])
                            d3xs[k, x, s, i, j] = 0.0
                for j in range(0, 58 + 1):
                    if nenbeex == 0:
                        xs = range(xa - 1, 115 + 1)
                    elif nenbeex == 1:
                        xs = range(0, 115 + 1)
                    else:
                        continue
                    for x in xs:
                        d3x[k, x, s, 0, j] = (d3x[k, x, s, 0, j]
                                              + d3x[k, x, s, i, j])
                        d3x[k, x, 0, i, j] = (d3x[k, x, 0, i, j]
                                              + d3x[k, x, s, i, j])
                        d3x[k, x, 0, 0, j] = (d3x[k, x, 0, 0, j]
                                              + d3x[k, x, s, i, j])

                        d3xs[k, x, s, 0, j] = (d3xs[k, x, s, 0, j]
                                               + d3xs[k, x, s, i, j])
                        d3xs[k, x, 0, i, j] = (d3xs[k, x, 0, i, j]
                                               + d3xs[k, x, s, i, j])
                        d3xs[k, x, 0, 0, j] = (d3xs[k, x, 0, 0, j]
                                               + d3xs[k, x, s, i, j])
                for x in range(0, 115 + 1):
                    kk[x] = 0.0
                    kk2[x] = 0.0
                for x in range(0, 115 + 1):
                    if s != 3:
                        kk[x] = G.ee[1]
                    else:
                        kk[x] = G.ee[2]
                    if ((i == 2 or i == 4 or i == 6 or i == 8)
                            and x < 65):
                        kk2[x] = kk[x]
                        kk[x] = 0.0
                    else:
                        kk2[x] = 0.0
                for x in range(0, 115 + 1):
                    kfprx[k, x, s, i, 0] = ((d3x[k, x, s, i, 13]
                                             + d3x[k, x, s, i, 14]
                                             + d3x[k, x, s, i, 15]
                                             + d3x[k, x, s, i, 16]
                                             + d3x[k, x, s, i, 17]
                                             + d3x[k, x, s, i, 18])
                                            * kk[x])
                if nenbeex == 0:
                    for x in range(0, xa - 2 + 1):
                        kfprx[k, xa - 1, s, i, 0] += kfprx[k, x, s, i, 0]
                        kfprx[k, x, s, i, 0] = 0.0
                for x in range(0, 115 + 1):
                    kfprx[k, x, s, i, 1] = d3x[k, x, s, i, 13] * kk[x]
                if nenbeex == 0:
                    for x in range(0, xa - 2 + 1):
                        kfprx[k, xa - 1, s, i, 1] += kfprx[k, x, s, i, 1]
                        kfprx[k, x, s, i, 1] = 0.0
                for x in range(0, 115 + 1):
                    kfprx[k, x, s, i, 2] = (kfprx[k, x, s, i, 0]
                                            - kfprx[k, x, s, i, 1])
                if nenbeex == 0:
                    for x in range(0, xa - 2 + 1):
                        kfprx[k, xa - 1, s, i, 2] += kfprx[k, x, s, i, 2]
                        kfprx[k, x, s, i, 2] = 0.0
                if i == 2 or i == 4 or i == 6 or i == 8:
                    for x in range(0, 64 + 1):
                        kfprx[k, x, s, i, 0] = 0.0
                        kfprx[k, x, s, i, 1] = 0.0
                        kfprx[k, x, s, i, 2] = 0.0
                if nenbe65 == 1:
                    for x in range(0, 115 + 1):
                        kfprx[k, x, s, i, 3] = ((d3x[k, x, s, i, 53]
                                                 + d3x[k, x, s, i, 54]
                                                 + d3x[k, x, s, i, 55]
                                                 + d3x[k, x, s, i, 56]
                                                 + d3x[k, x, s, i, 57]
                                                 + d3x[k, x, s, i, 58])
                                                * kk[x])
                        kfprx[k, x, s, i, 4] = d3x[k, x, s, i, 53] * kk[x]
                        kfprx[k, x, s, i, 5] = (kfprx[k, x, s, i, 3]
                                                - kfprx[k, x, s, i, 4])
                    if nenbeex == 0:
                        for x in range(0, xa - 2 + 1):
                            kfprx[k, xa - 1, s, i, 3] = (
                                kfprx[k, xa - 1, s, i, 3]
                                + kfprx[k, x, s, i, 3])
                            kfprx[k, xa - 1, s, i, 4] = (
                                kfprx[k, xa - 1, s, i, 4]
                                + kfprx[k, x, s, i, 4])
                            kfprx[k, xa - 1, s, i, 5] = (
                                kfprx[k, xa - 1, s, i, 5]
                                + kfprx[k, x, s, i, 5])
                            kfprx[k, x, s, i, 3] = 0.0
                            kfprx[k, x, s, i, 4] = 0.0
                            kfprx[k, x, s, i, 5] = 0.0
                if nenbe65 == 1:
                    for x in range(0, 115 + 1):
                        kfprx[k, x, s, i, 6] = ((d3x[k, x, s, i, 53]
                                                 + d3x[k, x, s, i, 54]
                                                 + d3x[k, x, s, i, 55]
                                                 + d3x[k, x, s, i, 56]
                                                 + d3x[k, x, s, i, 57]
                                                 + d3x[k, x, s, i, 58])
                                                * kk2[x])
                        kfprx[k, x, s, i, 7] = d3x[k, x, s, i, 53] * kk2[x]
                        kfprx[k, x, s, i, 8] = (kfprx[k, x, s, i, 6]
                                                - kfprx[k, x, s, i, 7])
                    if nenbeex == 0:
                        for x in range(0, xa - 2 + 1):
                            kfprx[k, xa - 1, s, i, 6] = (
                                kfprx[k, xa - 1, s, i, 6]
                                + kfprx[k, x, s, i, 6])
                            kfprx[k, xa - 1, s, i, 7] = (
                                kfprx[k, xa - 1, s, i, 7]
                                + kfprx[k, x, s, i, 7])
                            kfprx[k, xa - 1, s, i, 8] = (
                                kfprx[k, xa - 1, s, i, 8]
                                + kfprx[k, x, s, i, 8])
                            kfprx[k, x, s, i, 6] = 0.0
                            kfprx[k, x, s, i, 7] = 0.0
                            kfprx[k, x, s, i, 8] = 0.0
                for j in range(0, 8 + 1):
                    if nenbe65 == 0 and j >= 3:
                        continue
                    if nenbeex == 0:
                        xs = range(xa - 1, 115 + 1)
                    elif nenbeex == 1:
                        xs = range(0, 115 + 1)
                    else:
                        continue
                    for x in xs:
                        kfprx[k, x, s, 0, j] = (kfprx[k, x, s, 0, j]
                                                + kfprx[k, x, s, i, j])
                        kfprx[k, x, 0, i, j] = (kfprx[k, x, 0, i, j]
                                                + kfprx[k, x, s, i, j])
                        kfprx[k, x, 0, 0, j] = (kfprx[k, x, 0, 0, j]
                                                + kfprx[k, x, s, i, j])

    # ------------------------------------------------------------------
    # 年度末 → 年度間の平均
    # ------------------------------------------------------------------
    for s in range(1, 3 + 1):
        for k in range(KE, KIJUN + 1 - 1, -1):
            G.aal[k, s] = G.a[k, s] + G.aiku[k, s]

            if pseid == 1 or pseid == 4:
                # 共済は 5 : 7
                G.a[k, s] = (5.0 * G.a[k - 1, s] + 7.0 * G.a[k, s]) / 12.0
                G.aiku[k, s] = ((5.0 * G.aiku[k - 1, s]
                                 + 7.0 * G.aiku[k, s]) / 12.0)
                G.a60[k, s] = ((5.0 * G.a60[k - 1, s]
                                + 7.0 * G.a60[k, s]) / 12.0)
                G.a65[k, s] = ((5.0 * G.a65[k - 1, s]
                                + 7.0 * G.a65[k, s]) / 12.0)
                G.a70[k, s] = ((5.0 * G.a70[k - 1, s]
                                + 7.0 * G.a70[k, s]) / 12.0)
                G.a75[k, s] = ((5.0 * G.a75[k - 1, s]
                                + 7.0 * G.a75[k, s]) / 12.0)
                G.a85[k, s] = ((5.0 * G.a85[k - 1, s]
                                + 7.0 * G.a85[k, s]) / 12.0)
            elif pseid == 0 and (k == G.partyr3 or k == G.partyr4):
                # 適用拡大の年度は当年度に `*dum`（拡大前）を使う
                G.a[k, s] = ((6.0 * G.a[k - 1, s]
                              + 6.0 * G.adum[k, s]) / 12.0)
                G.aiku[k, s] = ((6.0 * G.aiku[k - 1, s]
                                 + 6.0 * G.aikudum[k, s]) / 12.0)
                G.a60[k, s] = ((6.0 * G.a60[k - 1, s]
                                + 6.0 * G.a60dum[k, s]) / 12.0)
                G.a65[k, s] = ((6.0 * G.a65[k - 1, s]
                                + 6.0 * G.a65dum[k, s]) / 12.0)
                G.a70[k, s] = ((6.0 * G.a70[k - 1, s]
                                + 6.0 * G.a70dum[k, s]) / 12.0)
                G.a75[k, s] = ((6.0 * G.a75[k - 1, s]
                                + 6.0 * G.a75dum[k, s]) / 12.0)
                G.a85[k, s] = ((6.0 * G.a85[k - 1, s]
                                + 6.0 * G.a85dum[k, s]) / 12.0)
                G.apart[k, s] = ((6.0 * G.apart[k - 1, s]
                                  + 6.0 * G.apart[k, s]) / 12.0)
                G.aikupart[k, s] = ((6.0 * G.aikupart[k - 1, s]
                                     + 6.0 * G.aikupart[k, s]) / 12.0)
                G.a60part[k, s] = ((6.0 * G.a60part[k - 1, s]
                                    + 6.0 * G.a60part[k, s]) / 12.0)
                G.a65part[k, s] = ((6.0 * G.a65part[k - 1, s]
                                    + 6.0 * G.a65part[k, s]) / 12.0)
                G.a70part[k, s] = ((6.0 * G.a70part[k - 1, s]
                                    + 6.0 * G.a70part[k, s]) / 12.0)
                G.a75part[k, s] = ((6.0 * G.a75part[k - 1, s]
                                    + 6.0 * G.a75part[k, s]) / 12.0)
                G.a85part[k, s] = ((6.0 * G.a85part[k - 1, s]
                                    + 6.0 * G.a85part[k, s]) / 12.0)
                G.apart[k - 1, s] = 0.0
                G.aikupart[k - 1, s] = 0.0
                G.a60part[k - 1, s] = 0.0
                G.a65part[k - 1, s] = 0.0
                G.a70part[k - 1, s] = 0.0
                G.a75part[k - 1, s] = 0.0
                G.a85part[k - 1, s] = 0.0
            else:
                G.a[k, s] = (6.0 * G.a[k - 1, s] + 6.0 * G.a[k, s]) / 12.0
                G.aiku[k, s] = ((6.0 * G.aiku[k - 1, s]
                                 + 6.0 * G.aiku[k, s]) / 12.0)
                G.a60[k, s] = ((6.0 * G.a60[k - 1, s]
                                + 6.0 * G.a60[k, s]) / 12.0)
                G.a65[k, s] = ((6.0 * G.a65[k - 1, s]
                                + 6.0 * G.a65[k, s]) / 12.0)
                G.a70[k, s] = ((6.0 * G.a70[k - 1, s]
                                + 6.0 * G.a70[k, s]) / 12.0)
                G.a75[k, s] = ((6.0 * G.a75[k - 1, s]
                                + 6.0 * G.a75[k, s]) / 12.0)
                G.a85[k, s] = ((6.0 * G.a85[k - 1, s]
                                + 6.0 * G.a85[k, s]) / 12.0)

            G.ap[k, s] = (G.ap[k - 1, s] + G.ap[k, s]) / 2.0
            G.appart[k, s] = (G.appart[k - 1, s] + G.appart[k, s]) / 2.0
            G.at[k, s] = (G.at[k - 1, s] + G.at[k, s]) / 2.0

            G.ap65[k, s] = (G.ap65[k - 1, s] + G.ap65[k, s]) / 2.0
            G.ap70[k, s] = (G.ap70[k - 1, s] + G.ap70[k, s]) / 2.0
            G.ap75[k, s] = (G.ap75[k - 1, s] + G.ap75[k, s]) / 2.0
            G.ap85[k, s] = (G.ap85[k - 1, s] + G.ap85[k, s]) / 2.0
            G.appart65[k, s] = ((G.appart65[k - 1, s]
                                 + G.appart65[k, s]) / 2.0)
            G.appart70[k, s] = ((G.appart70[k - 1, s]
                                 + G.appart70[k, s]) / 2.0)
            G.appart75[k, s] = ((G.appart75[k - 1, s]
                                 + G.appart75[k, s]) / 2.0)
            G.appart85[k, s] = ((G.appart85[k - 1, s]
                                 + G.appart85[k, s]) / 2.0)

    for s in range(0, 3 + 1):
        G.a[KIJUN, s] = 0.0
        G.ap[KIJUN, s] = 0.0
        G.appart[KIJUN, s] = 0.0
        G.at[KIJUN, s] = 0.0
        G.aiku[KIJUN, s] = 0.0
        G.a60[KIJUN, s] = 0.0
        G.a65[KIJUN, s] = 0.0
        G.a70[KIJUN, s] = 0.0
        G.a75[KIJUN, s] = 0.0
        G.a85[KIJUN, s] = 0.0
        G.ap65[KIJUN, s] = 0.0
        G.appart65[KIJUN, s] = 0.0
        G.ap70[KIJUN, s] = 0.0
        G.appart70[KIJUN, s] = 0.0
        G.ap75[KIJUN, s] = 0.0
        G.appart75[KIJUN, s] = 0.0
        G.ap85[KIJUN, s] = 0.0
        G.appart85[KIJUN, s] = 0.0

        G.gee[KIJUN, s, 15:85 + 1, 0:70 + 1] = 0.0
        G.geept[KIJUN, s, 15:85 + 1, 0:70 + 1] = 0.0

    # ------------------------------------------------------------------
    # 性別の「計」（s = 0）
    # ------------------------------------------------------------------
    for k in range(KE, KIJUN + 1 - 1, -1):
        G.a[k, 0] = G.a[k, 1] + G.a[k, 2] + G.a[k, 3]

        G.aal[k, 0] = G.aal[k, 1] + G.aal[k, 2] + G.aal[k, 3]

        G.aiku[k, 0] = G.aiku[k, 1] + G.aiku[k, 2] + G.aiku[k, 3]

        G.ap[k, 0] = G.ap[k, 1] + G.ap[k, 2] + G.ap[k, 3]
        G.appart[k, 0] = G.appart[k, 1] + G.appart[k, 2] + G.appart[k, 3]

        G.at[k, 0] = G.at[k, 1] + G.at[k, 2] + G.at[k, 3]

        G.ap65[k, 0] = G.ap65[k, 1] + G.ap65[k, 2] + G.ap65[k, 3]
        G.ap70[k, 0] = G.ap70[k, 1] + G.ap70[k, 2] + G.ap70[k, 3]
        G.ap75[k, 0] = G.ap75[k, 1] + G.ap75[k, 2] + G.ap75[k, 3]
        G.ap85[k, 0] = G.ap85[k, 1] + G.ap85[k, 2] + G.ap85[k, 3]
        G.appart65[k, 0] = (G.appart65[k, 1] + G.appart65[k, 2]
                            + G.appart65[k, 3])
        G.appart70[k, 0] = (G.appart70[k, 1] + G.appart70[k, 2]
                            + G.appart70[k, 3])
        G.appart75[k, 0] = (G.appart75[k, 1] + G.appart75[k, 2]
                            + G.appart75[k, 3])
        G.appart85[k, 0] = (G.appart85[k, 1] + G.appart85[k, 2]
                            + G.appart85[k, 3])
        G.a60[k, 0] = G.a60[k, 1] + G.a60[k, 2] + G.a60[k, 3]
        G.a65[k, 0] = G.a65[k, 1] + G.a65[k, 2] + G.a65[k, 3]
        G.a70[k, 0] = G.a70[k, 1] + G.a70[k, 2] + G.a70[k, 3]
        G.a75[k, 0] = G.a75[k, 1] + G.a75[k, 2] + G.a75[k, 3]
        G.a85[k, 0] = G.a85[k, 1] + G.a85[k, 2] + G.a85[k, 3]

        G.apart[k, 0] = G.apart[k, 1] + G.apart[k, 2] + G.apart[k, 3]
        G.aikupart[k, 0] = (G.aikupart[k, 1] + G.aikupart[k, 2]
                            + G.aikupart[k, 3])
        G.a60part[k, 0] = G.a60part[k, 1] + G.a60part[k, 2] + G.a60part[k, 3]
        G.a65part[k, 0] = G.a65part[k, 1] + G.a65part[k, 2] + G.a65part[k, 3]
        G.a70part[k, 0] = G.a70part[k, 1] + G.a70part[k, 2] + G.a70part[k, 3]
        G.a75part[k, 0] = G.a75part[k, 1] + G.a75part[k, 2] + G.a75part[k, 3]
        G.a85part[k, 0] = G.a85part[k, 1] + G.a85part[k, 2] + G.a85part[k, 3]

        G.gee[k, 0, 15:85 + 1, 0:70 + 1] = (
            G.gee[k, 1, 15:85 + 1, 0:70 + 1]
            + G.gee[k, 2, 15:85 + 1, 0:70 + 1]
            + G.gee[k, 3, 15:85 + 1, 0:70 + 1])
        G.geept[k, 0, 15:85 + 1, 0:70 + 1] = (
            G.geept[k, 1, 15:85 + 1, 0:70 + 1]
            + G.geept[k, 2, 15:85 + 1, 0:70 + 1]
            + G.geept[k, 3, 15:85 + 1, 0:70 + 1])
