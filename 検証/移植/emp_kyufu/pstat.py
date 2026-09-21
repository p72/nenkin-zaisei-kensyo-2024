# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/pstat.cpp の忠実移植（年報比較用と足元の出力）
===================================================================
441 行。`KIJUN` から `KIJUN + 19` の 20 年度ぶん、4つのファイルを書く。

| ファイル | 中身 | 年度 |
|---|---|---|
| `hikaku.{試算}` | 年報データと比べる形（兆円・万人） | `k <= KIJUN + 4` |
| `ashimoto.{試算}` | 受給**者**の年齢別内訳（人・円） | 20 年度 |
| `ashimotos.{試算}` | 受給**権**者の同じもの | 20 年度 |
| `ashimotosum.{試算}` | `ashimoto` の年齢計 | 20 年度 |
| `ashimotossum.{試算}` | `ashimotos` の年齢計 | 20 年度 |

どれも確認用で、他のプログラムは読まない。

`join(...).c_str()` が解放済みの領域を指す
------------------------------------------
```cpp
const char * join2(const v2_t &v, int axis1, int exp) {
  v1_t vals;
  for(int jj = 1; jj <= 2; jj++) vals.push_back(v.AT(axis1, jj) * pow(10.0, exp));
  return csvio::join("%16.8lf", vals).c_str();      /* ← 一時オブジェクト */
}
```

`csvio::join` は `std::string` を**値で返す**。その一時オブジェクトは
`return` 文の終わりで破棄されるので、`.c_str()` が返すポインタは
**解放済みの領域を指す**。呼び出し側は

```cpp
fprintf(fp, f9102, "総給付", sum1_join2(tmq, 1,6, -12), "兆円");
```

とそのまま `fprintf` に渡す。同じ形が `hikaku_ns` の3関数と、
`ashimotosum` `ashimotossum` の

```cpp
const char *ctmw = csv::join("%16.0lf", vals).c_str();
```

にもある。**明確な未定義動作**（use-after-free）。

**無害ではない。実測した。** `join2` / `sum1_join2` は
2個 × `%16.8lf` ＝ 33文字、`join1` は 13個 × `%16.10lf` ＝ 220文字で、
どちらも libstdc++ の小文字列最適化（15文字）に収まらずヒープに
置かれる。解放したあとの区画には `malloc` の空きリストのつなぎが
書き込まれているので、`fprintf` が読むときには**もう壊れている**。

段階テスト（`検証/移植/test_kyufu_stage.py` の `out` 段階）で
原本と移植版の出力を突き合わせると、`pstat()` が書く3本だけが
食い違う。

| ファイル | 行数 | 化けた行 |
|---|---|---|
| `hikaku.*` | 216 | 130 |
| `ashimotosum.*` | 581 | 360 |
| `ashimotossum.*` | 581 | 360 |

```
総給付費,     26.40777389,     24.36361335,兆円   ← 移植版
総給付費,<cd ed d9 63 a1 55>,兆円                 ← 原本（-O2）
総給付費,<e9 a1 8c 5e 78 55>,兆円                 ← 原本（-O0）
```

見出し・単位・行数は合っていて、**数値の欄だけ**が数バイトの
ごみに化ける。`hikaku` `ashimoto*` は確認用のファイルで②のほかの
プログラムも③〜⑥も読まないので、**財政検証の結果そのものは
これに影響されない**。`検証/原本の不具合.md` の H3。

**移植版は正しい文字列を渡す。** したがってこの3本は原本と
バイト一致しない。段階テストの
`test_pstatの3本だけがB9で化けている` が「行数は同じ・化けるのは
数値の欄だけ・原本の側は数値として読めない」ことを固定する。

`tmp` が `k > KIJUN + 4` で持ち越される
---------------------------------------
```c
FOR(k, KIJUN, KIJUN + 19) {
  if((key == 11 || key == 13) && nenbeex == 0){
    { … if(k <= k_hikaku) { sst::subc1(tmp, 1,10); … tmp に入れる … } }
    if(key == 11 && nenbeex == 0){
      fp = fp_map["ashimoto"];
      …
      fprintf(fp, f9200, "被保険者数", tmp.AT(1), "人");
```

`tmp`（被保険者数・待期者数・標準報酬総額）を作るのは
**`k <= k_hikaku`（= KIJUN + 4 = 25）のときだけ**。`k` が 26〜40 の
`ashimoto` 系は **2025年度の値をそのまま書き続ける**。
同 E32。年齢別の中身（`tmt` `tmv`）は毎年度作り直すので、
「頭の数行だけが 2025年度のまま」という形。

`", 円"` の書き間違い
---------------------
```c
fprintf(fp, f9200, "標報総計", tmp.AT(8), ", 円");
```

`ashimotos` の1か所だけ単位が `", 円"`（先頭にカンマと空白）に
なっていて、`標報総計,     ...,, 円` と**欄が1つ増える**。
`ashimoto` `ashimotosum` `ashimotossum` の同じ行は `"円"`。
同 F21。
"""
from csvio import add_dbl, join, line_feed, print_int
from glva import G
from sepsstd import fmt
from setconst import KIJUN

__all__ = ["pstat"]

# 受給（権）者データの見出し
_J_NAMES_JUKYU = (
    "受給者", "総給付費", "独自支給", "独自比例", "独自定額",
    "経過的加算", "独自加給", "独自遺族加算", "独自最低保障",
    "新法基礎", "みなし基礎", "みなし基本", "みなし基本２",
    "みなし嵩上げ", "みなし加給", "みなし振替", "かさ上げ／４",
    "経過的国庫")
# 受給**権**者の側は 0 番だけ名前が違う
_J_NAMES_JKEN = ("受給権者",) + _J_NAMES_JUKYU[1:]

_AGE_HEADER = ("年齢, 総計"
               ", 新老退, 新老在, 新通退, 新通在"
               ", 旧老退, 旧老在, 旧通退, 旧通在"
               ", 新障, 旧障, 新遺, 旧遺, 旧通遺")
_SUM_HEADER = (", , , 総計"
               ", 新老退, 新老在, 新通退, 新通在"
               ", 旧老退, 旧老在, 旧通退, 旧通在"
               ", 新障, 旧障, 新遺, 旧遺, 旧通遺")


def _join2(v, axis1, exp):
    """pstat.cpp:11 の `hikaku_ns::join2`。`v[axis1][1..2]` を並べる。"""
    p = 10.0 ** exp
    return join([v[axis1][jj] * p for jj in (1, 2)], "%16.8f")


def _sum1_join2(v, a_from, a_to, exp):
    """pstat.cpp:18 の `sum1_join2`。第1軸を足してから並べる。"""
    p = 10.0 ** exp
    vals = []
    for jj in (1, 2):
        sum1 = 0.0
        for a1 in range(a_from, a_to + 1):
            sum1 += v[a1][jj]
        vals.append(sum1 * p)
    return join(vals, "%16.8f")


def _join1(v, axis2, exp):
    """pstat.cpp:29 の `join1`。`v[1..13][axis2]` を並べる。"""
    p = 10.0 ** exp
    return join([v[i][axis2] * p for i in range(1, 13 + 1)], "%16.10f")


def pstat():
    """pstat.cpp:37 の忠実移植。"""
    pseid = G.pseid
    key = G.key
    nenbeex = G.nenbeex
    d3 = G.d3
    d3x = G.d3x
    d3xs = G.d3xs

    tmp = [0.0] * 11
    tmq = [[0.0] * 3 for _ in range(59)]
    tmr = [[0.0] * 3 for _ in range(14)]
    tms = [[[0.0] * 59 for _ in range(14)] for _ in range(116)]
    tmt = [[[0.0] * 18 for _ in range(14)] for _ in range(116)]
    tmu = [[[0.0] * 59 for _ in range(14)] for _ in range(116)]
    tmv = [[[0.0] * 18 for _ in range(14)] for _ in range(116)]
    tmw = [[0.0] * 18 for _ in range(14)]
    tmx = [[0.0] * 18 for _ in range(14)]
    tmka = [[0.0] * 3 for _ in range(14)]

    k_hikaku = KIJUN + 4

    for k in range(KIJUN, KIJUN + 19 + 1):
        if not ((key == 11 or key == 13) and nenbeex == 0):
            continue

        # ---- 年報データ比較用（k <= KIJUN + 4 だけ）----
        fp = G.fp_map["hikaku"]

        if k <= k_hikaku:
            for a in range(1, 10 + 1):
                tmp[a] = 0.0
            for a in range(0, 58 + 1):
                for b in range(1, 2 + 1):
                    tmq[a][b] = 0.0
            for a in range(1, 13 + 1):
                for b in range(1, 2 + 1):
                    tmr[a][b] = 0.0
            for j in range(1, 2 + 1):
                for i in range(1, 13 + 1):
                    tmka[i][j] = 0.0

            for s in range(1, 3 + 1):   # グローバルの s を隠す
                tmp[1] += G.ap[k, s]
                tmp[2] += G.ap65[k, s]
                tmp[3] += G.ap70[k, s]
                tmp[4] += G.ap75[k, s]
                tmp[5] += G.ap85[k, s]
                tmp[6] += G.at[k, s]
                tmp[8] += G.a[k, s] + G.aiku[k, s]
                tmp[9] += G.aiku[k, s]

                for jj in range(1, 2 + 1):
                    for i in range(1, 13 + 1):
                        tmr[i][jj] += (d3[k, s, i, 1, jj] + d3[k, s, i, 2, jj]
                                       + d3[k, s, i, 3, jj]
                                       + d3[k, s, i, 4, jj]
                                       + d3[k, s, i, 5, jj]
                                       + d3[k, s, i, 6, jj])
                        for j in range(0, 58 + 1):
                            tmq[j][jj] += d3[k, s, i, j, jj]
                            if j == 10 and jj == 2:
                                tmka[i][1] += d3[k, s, i, j, jj]
                            if j == 23 and jj == 2:
                                tmka[i][2] += d3[k, s, i, j, jj]

            fp.write("pseid,%d,試算番号,%d,経済前提,%d,外枠,%d\n"
                     % (pseid, G.iname, G.iecon, G.iwname))
            fp.write("%d%s\n" % (k, "年度末状態の出力(年報データ比較用)"))
            fp.write("%s\n" % "被保険者データの出力")

            f9000 = "%s,%10.4f,%s\n"
            fp.write(f9000 % ("被保険者数", tmp[1] * 1.0e-4, "万人"))
            fp.write(f9000 % ("待期者数", tmp[6] * 1.0e-4, "万人"))
            fp.write(f9000 % ("基金加入者数", 0.0, "万人"))
            fp.write(f9000 % ("基金待期(厚年現存)", 0.0, "万人"))
            fp.write(f9000 % ("基金待期(厚年待期)", 0.0, "万人"))
            fp.write(f9000 % ("標報総計", tmp[8] * 1.0e-12, "兆円"))
            fp.write(f9000 % ("標報総計(育児再掲)", tmp[9] * 1.0e-12,
                              "兆円"))
            fp.write(f9000 % ("基金標報総計", 0.0, "兆円"))

            fp.write("%s,%s,%s,%s\n" % ("", "受給権者", "受給者", ""))
            fp.write("%s,%12.4f,%12.4f,%s\n"
                     % ("件数", tmq[0][1] * 1.0e-4, tmq[0][2] * 1.0e-4,
                        "万人"))

            f9102 = "%s,%s,%s\n"

            fp.write(f9102 % ("総給付", _sum1_join2(tmq, 1, 6, -12), "兆円"))
            for label, a1 in (("新老退", 1), ("新老在", 2), ("新通退", 3),
                              ("新通在", 4), ("旧老退", 5), ("旧老在", 6),
                              ("旧通退", 7), ("旧通在", 8), ("新障", 9),
                              ("旧障", 10), ("新遺", 11), ("旧遺１", 12),
                              ("旧遺２", 13)):
                fp.write(f9102 % ("総給付;" + label,
                                  _join2(tmr, a1, -12), "兆円"))
            fp.write(f9102 % ("独自給付", _sum1_join2(tmq, 7, 12, -12),
                              "兆円"))
            fp.write(f9102 % ("独自加給", _join2(tmq, 10, -12), "兆円"))
            fp.write(f9102 % ("受給者分のi別内訳", _join1(tmka, 1, -12),
                              "兆円"))
            fp.write(f9102 % ("新法基礎", _sum1_join2(tmq, 19, 21, -12),
                              "兆円"))
            fp.write(f9102 % ("みなし基礎", _sum1_join2(tmq, 22, 24, -12),
                              "兆円"))
            kihon1 = ((tmq[22][1] - tmq[28][1] - 3.0 * tmq[25][1])
                      * 1.0e-12)
            kihon2 = ((tmq[22][2] - tmq[28][2] - 3.0 * tmq[25][2])
                      * 1.0e-12)
            fp.write(f9102 % ("みなし基本",
                              fmt("%16.8lf,%16.8lf", kihon1, kihon2),
                              "兆円"))
            fp.write(f9102 % ("みなし基本２", _join2(tmq, 28, -12), "兆円"))
            kasa1 = (3.0 * tmq[25][1]) * 1.0e-12
            kasa2 = (3.0 * tmq[25][2]) * 1.0e-12
            fp.write(f9102 % ("みなし嵩上",
                              fmt("%16.8lf,%16.8lf", kasa1, kasa2), "兆円"))
            fp.write(f9102 % ("みなし加給", _join2(tmq, 23, -12), "兆円"))
            fp.write(f9102 % ("受給者分のi別内訳", _join1(tmka, 2, -12),
                              "兆円"))
            fp.write(f9102 % ("みなし振替", _join2(tmq, 24, -12), "兆円"))
            fp.write(f9102 % ("かさ上げ／４", _join2(tmq, 25, -12), "兆円"))
            fp.write(f9102 % ("経過的国庫", _sum1_join2(tmq, 26, 27, -12),
                              "兆円"))
            fp.write(f9102 % ("基金代行",
                              fmt("%16.8lf,%16.8lf", 0.0, 0.0), "兆円"))
            fp.write(f9102 % ("政府負担金",
                              fmt("%16.8lf,%16.8lf", 0.0, 0.0), "兆円"))
            fp.write(f9102 % ("代行相当", _join2(tmq, 31, -12), "兆円"))

        # ---- 足元のデータ（受給者）----
        if key == 11 and nenbeex == 0:
            fp = G.fp_map["ashimoto"]

            for x in range(0, 115 + 1):
                for i in range(0, 13 + 1):
                    for j in range(0, 58 + 1):
                        tms[x][i][j] = 0.0
                    for j in range(0, 17 + 1):
                        tmt[x][i][j] = 0.0

            for s in range(1, 3 + 1):
                if pseid >= 1 and s == 3:
                    continue
                for x in range(0, 115 + 1):
                    for i in range(1, 13 + 1):
                        for j in range(0, 58 + 1):
                            v = d3x[k, x, s, i, j]
                            tms[x][i][j] += v
                            tms[x][0][j] += v

            _make_tmt(tms, tmt)

            fp.write("pseid,%d,試算番号,%d,経済前提,%d,外枠,%d\n"
                     % (pseid, G.iname, G.iecon, G.iwname))
            fp.write("%d,年度末状態の出力(足下のデータ)\n" % k)
            fp.write("%s\n" % "被保険者データの出力")

            f9200 = "%s,%16.0f,%s\n"
            fp.write(f9200 % ("被保険者数", tmp[1], "人"))
            fp.write(f9200 % ("待期者数", tmp[6], "人"))
            fp.write(f9200 % ("基金加入者数", 0.0, "人"))
            fp.write(f9200 % ("基金待期(厚年現存)", 0.0, "人"))
            fp.write(f9200 % ("基金待期(厚年待期)", 0.0, "人"))
            fp.write(f9200 % ("標報総計", tmp[8], "円"))
            fp.write(f9200 % ("標報総計(育児再掲)", tmp[9], "円"))
            fp.write(f9200 % ("基金標報総計", 0.0, "円"))

            line_feed(fp)
            fp.write("%s\n" % "受給者データの出力")
            fp.write("%s\n" % "人数は「人」単位、金額は「円」単位")

            for j in range(0, 17 + 1):
                line_feed(fp)
                fp.write("j=,%d,%s\n" % (j, _J_NAMES_JUKYU[j]))
                fp.write("%s\n" % _AGE_HEADER)
                for x in range(0, 115 + 1):
                    print_int(fp, x)
                    for i in range(0, 13 + 1):
                        add_dbl(fp, "%16.0f", tmt[x][i][j])
                    line_feed(fp)

        # ---- 足元のデータ（受給権者）----
        if key == 11 and nenbeex == 0:
            fp = G.fp_map["ashimotos"]

            for x in range(0, 115 + 1):
                for i in range(0, 13 + 1):
                    for j in range(0, 58 + 1):
                        tmu[x][i][j] = 0.0
                    for j in range(0, 17 + 1):
                        tmv[x][i][j] = 0.0

            for s in range(1, 3 + 1):
                if pseid >= 1 and s == 3:
                    continue
                for x in range(0, 115 + 1):
                    for i in range(1, 13 + 1):
                        for j in range(0, 58 + 1):
                            v = d3xs[k, x, s, i, j]
                            tmu[x][i][j] += v
                            tmu[x][0][j] += v

            _make_tmt(tmu, tmv)

            fp.write("pseid,%d,試算番号,%d,経済前提,%d,外枠,%d\n"
                     % (pseid, G.iname, G.iecon, G.iwname))
            fp.write("%d,%s\n" % (k, "年度末状態の出力(足下のデータ)"))
            fp.write("%s\n" % "被保険者データの出力")

            f9200 = "%s,%16.0f,%s\n"
            fp.write(f9200 % ("被保険者数", tmp[1], "人"))
            fp.write(f9200 % ("待期者数", tmp[6], "人"))
            fp.write(f9200 % ("基金加入者数", 0.0, "人"))
            fp.write(f9200 % ("基金待期(厚年現存)", 0.0, "人"))
            fp.write(f9200 % ("基金待期(厚年待期)", 0.0, "人"))
            # ここだけ単位が `", 円"`（欄が1つ増える。F21）
            fp.write(f9200 % ("標報総計", tmp[8], ", 円"))
            fp.write(f9200 % ("標報総計(育児再掲)", tmp[9], "円"))
            fp.write(f9200 % ("基金標報総計", 0.0, "円"))

            line_feed(fp)
            fp.write("%s\n" % "受給権者データの出力")
            fp.write("%s\n" % "人数は「人」単位、金額は「円」単位")

            for j in range(0, 17 + 1):
                line_feed(fp)
                fp.write("j=,%d,%s\n" % (j, _J_NAMES_JKEN[j]))
                fp.write("%s\n" % _AGE_HEADER)
                for x in range(0, 115 + 1):
                    print_int(fp, x)
                    for i in range(0, 13 + 1):
                        add_dbl(fp, "%16.0f", tmv[x][i][j])
                    line_feed(fp)

        # ---- 年齢計 ----
        if key == 11 and nenbeex == 0:
            fp = G.fp_map["ashimotosum"]
            for i in range(0, 13 + 1):
                for j in range(0, 17 + 1):
                    tmw[i][j] = 0.0
                    tmx[i][j] = 0.0

            for i in range(0, 13 + 1):
                for j in range(0, 17 + 1):
                    for x in range(0, 115 + 1):
                        tmw[i][j] += tmt[x][i][j]
                        tmx[i][j] += tmv[x][i][j]

            _write_sum(fp, k, tmp, tmw, _J_NAMES_JKEN)

        if key == 11 and nenbeex == 0:
            fp = G.fp_map["ashimotossum"]
            _write_sum(fp, k, tmp, tmx, _J_NAMES_JKEN)


def _make_tmt(src, dst):
    """`tms` → `tmt`（`tmu` → `tmv`）の列のまとめ方。両方同じ。"""
    for x in range(0, 115 + 1):
        for i in range(0, 13 + 1):
            a = src[x][i]
            d = dst[x][i]
            d[0] = a[0]
            d[1] = a[1] + a[2] + a[3] + a[4] + a[5] + a[6]
            d[2] = a[7] + a[8] + a[9] + a[10] + a[11] + a[12]
            d[3] = a[7]
            d[4] = a[8]
            d[5] = a[9]
            d[6] = a[10]
            d[7] = a[11]
            d[8] = a[12]
            d[9] = a[19] + a[20] + a[21]
            d[10] = a[22] + a[23] + a[24]
            d[11] = a[22] - a[28] - a[25] * 3.0
            d[12] = a[28]
            d[13] = a[25] * 3.0
            d[14] = a[23]
            d[15] = a[24]
            d[16] = a[25]
            d[17] = a[26] + a[27]


def _write_sum(fp, k, tmp, tm, names):
    """`ashimotosum` / `ashimotossum` の書き出し（中身が同じ）。"""
    fp.write("pseid,%d,試算番号,%d,経済前提,%d,外枠,%d\n"
             % (G.pseid, G.iname, G.iecon, G.iwname))
    fp.write("%d,%s\n" % (k, "年度末状態の出力(足下のデータ)"))
    fp.write("%s\n" % "被保険者データの出力")

    f9200 = "%s,%16.0f,%s\n"
    fp.write(f9200 % ("被保険者数", tmp[1], "人"))
    fp.write(f9200 % ("待期者数", tmp[6], "人"))
    fp.write(f9200 % ("標報総計", tmp[8], "円"))
    fp.write(f9200 % ("標報総計(育児再掲)", tmp[9], "円"))

    line_feed(fp)
    fp.write("%s\n" % "受給権者データの出力")
    fp.write("%s\n" % "人数は「人」単位、金額は「円」単位")

    fp.write("%s\n" % _SUM_HEADER)

    for j in range(0, 17 + 1):
        vals = [tm[i][j] for i in range(0, 13 + 1)]
        ctm = join(vals, "%16.0f")
        fp.write("j=,%d,%s,%s\n" % (j, names[j], ctm))
