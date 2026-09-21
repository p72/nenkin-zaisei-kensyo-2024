# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/waku.cpp の忠実移植（①被保険者推計の外枠を読む）
======================================================================
①が出した `waku{外枠}-NN.csv` を読んで、人口と被保険者数（外枠）を
入れる。制度ごとに読むファイルが違う。

    waku-population   -20  総人口              → pop[k][s][x]
    waku              -05  厚年の被保険者数    → l[k][s][x]
                      -08  国共 / -09 地共 / -10 私学
    waku-s3           -06  3号被保険者（厚年だけ）→ l[k][s+2][x]
    waku-part-all     -07  パート全体（厚年だけ）→ lpt[k][s][x]
    waku-part202410   -22  2024年10月の適用拡大  → lpt1[k][s][x]
    waku-part30-op    -30  オプション（`flg_part >= 1`）→ lpt2
    waku-part20-30-op -31  同                      → lpt3
    waku-part10-20-op -32  同（`flg_part == 4` のみ）→ lpt4

ファイルの形
------------
見出し2行のあと、**性別（0 計 / 1 男 / 2 女）× 年度（2021〜2125）**の
順で 315 行。列は `分類,性別,年度,?,15歳,16歳,…,120歳` で、
`vals[4 + (x - 15)]` が `x` 歳。15〜100歳ぶんを取る（101歳以上は捨てる）。

読んだ行の `性別` と `年度` を `assert` で確かめるので、並びが違えば
そこで落ちる。

`waku-s3` の読み方が変わっている
--------------------------------
```c
for(s = 0; s <= 2; s++) {
  for(k = WKKS; k <= WKKE; k++) {
    fgets(buf, BUF_SIZE, fp);
    if(k < STTY || ENDY < k) continue;
    if (s == 0) continue;          /* 男女計は捨てる */
    if (s == 2) break;             /* 女は1行読んで抜ける */
    ...
    l.AT(kk, ss+2, xx) = ...       /* s=1 を l[.][3][.] に入れる */
```

- `s == 0`（男女計）は105行ぜんぶ読んで捨てる
- `s == 1`（男）は `l[k][3][x]` に入れる
- `s == 2`（女）は **1行だけ読んで `break`**。`break` は `k` の
  ループを抜けるだけなので、そのあと `s = 3` で外側も終わる

つまり **3号被保険者の女のぶんは1行も入らない**（`l[k][4][x]` が
0 のまま）。`l` の第2添字は `VEC(double, ENDY, 3, 115)` で 0〜3 なので
**`ss + 2` が 4 になる s=2 は書けない**（`vector::at` が例外を投げる）。
`break` はそれを避けるためと読める。

`l[k][3][x]` が「男の3号」で、女の3号は別に持たない作り。
（`検証/原本の不具合.md`）

原本の癖をそのまま残しているところ
----------------------------------
1. **同じ読み込みループが8回ほぼ丸ごと重複している**（215行のうち
   実質25行）。違うのは開くキーと入れる配列だけ。
   移植版は表と関数にまとめた。

2. **`fgets` の戻り値を見ていない。**行が足りなければ前の行を
   もう一度読んだのと同じになり、`assert` で落ちる。

3. **`s` と `k` がグローバルのループ変数。**`waku()` を抜けたあとも
   値が残る（`s = 3`。`k` は普通に終われば `WKKE + 1`、`waku-s3` の
   `break` で抜けたときは `WKKS`）。`sepsd()` が次に使う前に入れ直すので
   影響しないが、移植版も残る値まで合わせてある。

4. **`char buf[BUF_SIZE]`（10,000 バイト）が局所変数。**`waku*.csv` の
   1行は 2,000 バイトほどなので収まる。

5. **`double err;` を宣言して使わない。**
"""


from csvio import getnums
from glva import G
from setconst import ENDY, STTY, WKKE, WKKS

__all__ = ["waku"]


def _read_block(fp, dest, sofs=0, skip_sum=False, break_on_s2=False):
    """外枠ファイル1本を読む（原本の重複した8つのループ。癖 1.）。

    `dest` は `(k, s + sofs, x)` に入れる配列。
    `skip_sum` は `s == 0` を捨てる（`waku-s3` だけ）。
    `break_on_s2` は `s == 2` で `k` のループを抜ける（同）。
    """
    fp.fgets()                       # 見出し2行
    fp.fgets()

    # `s` と `k` は**グローバルのループ変数**（癖 3.）。`break` したときに
    # 残る値まで合わせるため、`while` で書いてある
    for s in range(0, 3):
        G.s = s
        G.k = WKKS
        while G.k <= WKKE:
            fp.fgets()               # `fgets(buf, BUF_SIZE, fp)`
            if G.k < STTY or ENDY < G.k:
                G.k += 1
                continue
            if skip_sum and s == 0:
                G.k += 1
                continue
            if break_on_s2 and s == 2:
                break                # `k` のループだけを抜ける

            vals = getnums(fp.line)

            ss = int(vals[1])
            kk = int(vals[2]) - 2000
            assert s == ss, "waku: s = %d, ss = %d" % (s, ss)
            assert G.k == kk, "waku: k = %d, kk = %d" % (G.k, kk)

            for xx in range(15, 101):
                dest[kk][ss + sofs][xx] = vals[4 + (xx - 15)]
            G.k += 1
    G.s = 3


def waku():
    """waku.cpp:8 の忠実移植。"""
    print("外枠ファイル読み込み開始")

    _read_block(G.fp_map["waku-population"], G.pop)
    _read_block(G.fp_map["waku"], G.l)

    if G.pseid == 0:
        # 3号被保険者。`s == 0` は捨て、`s == 2` は1行で抜ける
        _read_block(G.fp_map["waku-s3"], G.l, sofs=2,
                    skip_sum=True, break_on_s2=True)

    if G.pseid == 0:
        _read_block(G.fp_map["waku-part-all"], G.lpt)
        _read_block(G.fp_map["waku-part202410"], G.lpt1)

        if G.flg_part >= 1:
            _read_block(G.fp_map["waku-part30-op"], G.lpt2)
            _read_block(G.fp_map["waku-part20-30-op"], G.lpt3)

            if G.flg_part == 4:
                _read_block(G.fp_map["waku-part10-20-op"], G.lpt4)
