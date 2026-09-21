# -*- coding: utf-8 -*-
"""
国民年金/printout.c の忠実移植（年度間への直しと参考出力5本）
=============================================================
1,180 行。`main.c` の**いちばん最後**に1回だけ呼ぶ。やることは2つ。

1. `*_Nendomatu` から積んだ**年度末**の値を、`nendokan()`
   `nendokan_64()` で**年度間**（その年度に実際に支払う額）に
   直す。`Rorei` `Rorei_Kyu` `Turo_Kyu` `Gonen` `Shogai_*`
   `Izoku_*` `Kafu` `Kafu_Kyu` `Ichijikin` を**その場で上書き**する
2. 5本の参考出力を書く

    PRINT_HIHO         被保険者数（種別ごと）
    PRINT_ROREI        新法・旧法老齢、通算老齢、5年年金、基礎年金満額
    PRINT_ROREI_SHINKI 老齢基礎の新規裁定の納付分（1行1明細）
    PRINT_SHOGAI       障害基礎（一般・20歳前・旧法）
    PRINT_IZOKU        遺族基礎（妻・夫・子）、寡婦、死亡一時金

**`stat()` のあとに走る**ので、④基礎年金が読む `KISONENKIN` は
年度末の値のまま。ここで上書きするのは③自身の参考出力だけ。

原本は 13 の節がほとんど同じ形
------------------------------
どの節も

```c
fprintf( fp , "<見出し>  種別=0\\n" );
fprintf( fp , "<列名>\\n" );
for( nendo = SHONENDO ; nendo <= SAISHUNENDO ; nendo++ ) { …[SHUBETU_SUM_NENDOKAN]… }

for( shubetu = 1 ; shubetu <= MAX_SHUBETU - 1 ; shubetu++ )
{
    fprintf( fp , "<見出し>  種別=%d\\n" , shubetu );
    fprintf( fp , "<列名>\\n" );
    for( nendo = … ) { …[shubetu]… }
}
```

という並びで、違うのは**見出し・列名・どの欄を書くか**だけ。
移植版は節を表（`_SECTIONS`）にして1つの書き手
（`_print_sections()`）で回している。満額の表3つだけは形が
違うので別（`_print_mangaku()`）。**書く順・書式・`sum` の足す順は原本のまま。**

`shubetu` は 1〜6 を回すので、**種別 1・4（存在しない番号）の節も
出る**（`PerformSiml()` が偽を返す番号。中身は全部 0）。原本の
とおりに出している。

改定率と満額の年齢の添字が `- UNDER_67` になっている
-----------------------------------------------------
```c
kaiteiritu_tannen[nendo - ECON_SHONENDO][nenrei <= UNDER_67 ? UNDER_67 - UNDER_67 : nenrei - UNDER_67]
```

`kaiteiritu_tannen` の2番目の添字は `econ.c` が

```c
for( nenrei = 0 ; nenrei <= MAX_ROREI_JUKYU ; nenrei++ )
    kaiteiritu_tannen[…][nenrei] = kaiteiritu_make( nenrei , … );
```

と**生の年齢**（0〜115）で埋めている（`kaiteiritu_make` が
`nenrei <= UNDER_67` で新規裁定と既裁定を分ける）。`siml.c` も
`kaiteiritu_tannen[…][nenrei]` と生の年齢で読む。

`printout.c` だけが `nenrei - UNDER_67` にしているので、
**68歳の人に「1歳」の改定率**（= 新規裁定の賃金スライド）を
当ててしまう。同じことが満額の表にもある。

```c
fprintf( fp , "年度,67歳以下," );  … "%d歳," , nenrei（68〜115）
… Full_Pension[nendo - SHONENDO][nenrei - UNDER_67]   /* 0〜48 を書く */
```

`検証/原本の不具合.md` **J4**。**`stat()` が先に走るので④の
入力（`KISONENKIN`）には出ない。**③の参考出力だけが動く。
移植版はそのまま写した。

`nendokan` が前年度を読むので最初の年度は配列の外
-------------------------------------------------
```c
for( nendo = SAISHUNENDO ; nendo >= SHONENDO ; nendo-- )
{
    sotai_nendo = nendo - SHONENDO;
    … nendokan( Rorei[shubetu][sotai_nendo - 1][…] , … )
```

`nendo == SHONENDO` のとき `sotai_nendo - 1` が **-1**。
C の番地計算では `Rorei[shubetu - 1][105][…]`（1つ前の種別の
最終年度）を読む。`siml.py` と同じ `_c_at()` で写した。
同 **B12**。
"""
from setconst import (ECON_SHONENDO, HIHO_NENREI_SUM, KURI_AGE_SAGE_SUM,
                      MAX_HIHO_NENREI, MAX_IZOKU_OTTO_JUKYU,
                      MAX_IZOKU_TUMA_JUKYU, MAX_ROREI_JUKYU,
                      MAX_SHOGAI_JUKYU, MAX_SHUBETU, MENJO_1_2, MENJO_1_4,
                      MENJO_3_4, MIN_ROREI_JUKYU, NENREI_SUM, SAISHUNENDO,
                      SHONENDO, SHUBETU_SUM_NENDOKAN, SUM, UNDER_64,
                      UNDER_67, ZENGAKU)
import numpy as np

from str_op import add, flat_view, nendokan, nendokan_64

__all__ = ["printout"]

# `mfile_open.h` の出力番号
_PRINT_HIHO = 0
_PRINT_ROREI = 1
_PRINT_ROREI_SHINKI = 2
_PRINT_SHOGAI = 3
_PRINT_IZOKU = 4

_HIHO_COLS = ("年度,被保険者数,納付ﾒ数,全額免除ﾒ数,3/4免除ﾒ数,"
              "半額免除ﾒ数,1/4免除ﾒ数,付加被保険者数")


def _c_at(a, *idx):
    """C の多次元配列と同じ番地計算（境界を見ない）。`siml.py` と同じ。"""
    n = 0
    for i, k in enumerate(idx):
        n = n * a.shape[i] + k
    return a.reshape(-1)[n]


def _f(v):
    """`fprintf( fp , "%f" , v )` と同じ文字列（小数6桁）。"""
    return "%f" % v


def _kt(G, nendo, nenrei):
    """原本の

    ```c
    kaiteiritu_tannen[nendo - ECON_SHONENDO][nenrei <= UNDER_67 ? 0 : nenrei - UNDER_67]
    ```

    をそのまま写したもの（**年齢の添字が 67 ずれている**。J4）。
    """
    x = 0 if nenrei <= UNDER_67 else nenrei - UNDER_67
    return G.kaiteiritu_tannen[nendo - ECON_SHONENDO, x]


def _kt0(G, nendo):
    """同じく `kaiteiritu_tannen[…][UNDER_67 - UNDER_67]`（= 添字 0）。"""
    return G.kaiteiritu_tannen[nendo - ECON_SHONENDO, 0]


def printout(G):
    """printout.c:10 の忠実移植。"""
    # 原本の `zoubun`（`= 1.0 / 100`）は**一度も読まない**ので
    # 移植版では作らない（`検証/原本の不具合.md` の F の仲間）

    fp_shinki = G.fp_out[_PRINT_ROREI_SHINKI]
    fp_shinki.write(", shubetu, nendo, nenrei, jukyu_nenrei, noufu\n")

    _nendokan_all(G, fp_shinki)
    _print_hiho(G)
    _print_sections(G)


def _nendokan_all(G, fp_shinki):
    """年度末 → 年度間の直し（`printout.c:29-276`）。

    年度を**降りながら** `sotai_nendo - 1`（前年度）を読むので、
    若い年度を先に書き換えると値が変わる。原本のとおりに降る。
    """
    K = KURI_AGE_SAGE_SUM
    S = SHUBETU_SUM_NENDOKAN

    for shubetu in range(1, MAX_SHUBETU):
        if shubetu not in (2, 3, 5, 6):
            continue

        for nendo in range(SAISHUNENDO, SHONENDO - 1, -1):
            s = nendo - SHONENDO

            # ---- 老齢（新法・旧法・通算・5年）------------------------
            # 下の足し込み先 `[shubetu, s, 0, K]` と `[S, s, 0, K]` は
            # **1つのスロットに全部足す**縮約なので、順序（受給年齢が外・
            # 年齢が内、降順）を変えられない。view をループの外に出して
            # 間接費だけ削る（`str_op.flat_view` の解説）。足し込み先の
            # `[0, K]` は `nendokan` が書く `[n, j]`（n ≥ 2、j ≤ 10）と
            # 重ならない
            _acc = []
            for name in ("Rorei", "Rorei_Kyu", "Turo_Kyu", "Gonen"):
                a = getattr(G, name)
                av = flat_view(a[shubetu, s])           # 生きた view
                _acc.append((av, av[0, K], flat_view(a[S, s])[0, K]))

            for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
                j = jukyu_nenrei - MIN_ROREI_JUKYU
                for nenrei in range(MAX_ROREI_JUKYU, UNDER_64 - 1, -1):
                    n = nenrei - NENREI_SUM
                    for name in ("Rorei", "Rorei_Kyu", "Turo_Kyu",
                                 "Gonen"):
                        a = getattr(G, name)
                        if nenrei == UNDER_64:
                            a[shubetu, s, n, j] = nendokan_64(
                                _c_at(a, shubetu, s - 1, n - 1, j),
                                a[shubetu, s, n - 1, j],
                                a[shubetu, s, n, j],
                                _kt0(G, nendo))
                        else:
                            a[shubetu, s, n, j] = nendokan(
                                _c_at(a, shubetu, s - 1, n - 1, j),
                                a[shubetu, s, n, j],
                                _kt(G, nendo, nenrei))

                    fp_shinki.write(
                        "3, %d, %d, %d, %d, %s\n"
                        % (shubetu, nendo, nenrei, jukyu_nenrei,
                           _f(G.Rorei[shubetu, s, n, j]["noufu"])))

                    # 原本は配列ごとに `[shubetu]` の計 → 配列ごとに
                    # `[S]` の計、の順だが、足し込み先が別なので配列ごとに
                    # 両方やっても各スロットの足す順は変わらない
                    for av, d_sh, d_s in _acc:
                        src = av[n, j]
                        np.add(d_sh, src, out=d_sh)
                        np.add(d_s, src, out=d_s)

            # ---- 障害（一般・20歳前・旧法）--------------------------
            for nenrei in range(MAX_SHOGAI_JUKYU, UNDER_64 - 1, -1):
                n = nenrei - NENREI_SUM
                for name in ("Shogai_Ippan", "Shogai_20mae",
                             "Shogai_Kyu"):
                    a = getattr(G, name)
                    if nenrei == UNDER_64:
                        a[shubetu, s, n] = nendokan_64(
                            _c_at(a, shubetu, s - 1, n - 1),
                            a[shubetu, s, n - 1],
                            a[shubetu, s, n],
                            _kt0(G, nendo))
                    else:
                        # 障害は改定率を2つ取る（基本と加給）
                        a[shubetu, s, n] = nendokan(
                            _c_at(a, shubetu, s - 1, n - 1),
                            a[shubetu, s, n],
                            _kt(G, nendo, nenrei), _kt0(G, nendo))

                for name in ("Shogai_Ippan", "Shogai_20mae",
                             "Shogai_Kyu"):
                    a = getattr(G, name)
                    a[shubetu, s, 0] = add(a[shubetu, s, 0],
                                           a[shubetu, s, n])
                for name in ("Shogai_Ippan", "Shogai_20mae",
                             "Shogai_Kyu"):
                    a = getattr(G, name)
                    a[S, s, 0] = add(a[S, s, 0], a[shubetu, s, n])

            # ---- 遺族（妻・夫）------------------------------------
            for name, hi in (("Izoku_Tuma", MAX_IZOKU_TUMA_JUKYU),
                             ("Izoku_Otto", MAX_IZOKU_OTTO_JUKYU)):
                a = getattr(G, name)
                for nenrei in range(hi, UNDER_64 - 1, -1):
                    n = nenrei - NENREI_SUM
                    if nenrei == UNDER_64:
                        a[shubetu, s, n] = nendokan_64(
                            _c_at(a, shubetu, s - 1, n - 1),
                            a[shubetu, s, n - 1],
                            a[shubetu, s, n],
                            _kt0(G, nendo))
                    else:
                        a[shubetu, s, n] = nendokan(
                            _c_at(a, shubetu, s - 1, n - 1),
                            a[shubetu, s, n],
                            _kt(G, nendo, nenrei), _kt0(G, nendo))

                    a[shubetu, s, 0] = add(a[shubetu, s, 0],
                                           a[shubetu, s, n])
                    a[S, s, 0] = add(a[S, s, 0], a[shubetu, s, n])

            # ---- 遺族（子。年齢で分けない）------------------------
            G.Izoku_Ko[shubetu, s] = nendokan(
                _c_at(G.Izoku_Ko, shubetu, s - 1),
                G.Izoku_Ko[shubetu, s],
                _kt0(G, nendo), _kt0(G, nendo))
            G.Izoku_Ko[S, s] = add(G.Izoku_Ko[S, s],
                                   G.Izoku_Ko[shubetu, s])

            # ---- 寡婦（新法・旧法）--------------------------------
            for name in ("Kafu", "Kafu_Kyu"):
                a = getattr(G, name)
                a[shubetu, s] = nendokan(_c_at(a, shubetu, s - 1),
                                         a[shubetu, s], _kt0(G, nendo))
            for name in ("Kafu", "Kafu_Kyu"):
                a = getattr(G, name)
                a[S, s] = add(a[S, s], a[shubetu, s])

            # ---- 死亡一時金（改定率は 1.）-------------------------
            a = G.Ichijikin
            for nenrei in range(MAX_HIHO_NENREI, UNDER_64 - 1, -1):
                n = nenrei - NENREI_SUM
                if nenrei == UNDER_64:
                    a[shubetu, s, n] = nendokan_64(
                        _c_at(a, shubetu, s - 1, n - 1),
                        a[shubetu, s, n - 1], a[shubetu, s, n], 1.)
                else:
                    a[shubetu, s, n] = nendokan(
                        _c_at(a, shubetu, s - 1, n - 1),
                        a[shubetu, s, n], 1.)

                a[shubetu, s, 0] = add(a[shubetu, s, 0], a[shubetu, s, n])
                a[S, s, 0] = add(a[S, s, 0], a[shubetu, s, n])


def _print_hiho(G):
    """被保険者数（`printout.c:278-361`）。種別 0・1・2・3・4・5・6 の7表。"""
    fp = G.fp_out[_PRINT_HIHO]
    H = HIHO_NENREI_SUM

    def row(nendo, shus):
        s = nendo - SHONENDO
        out = ["%d," % nendo]

        def tot(name, *extra):
            """原本と同じ順で左から足す（**先頭の種別から**始める。
            0. から足すと -0. のとき符号が変わる）。"""
            a = getattr(G, name)

            def one(sh):
                return a[sh, s, H] if not extra else a[sh, s, H, extra[0]]

            v = one(shus[0])
            for sh in shus[1:]:
                v = v + one(sh)
            return v

        out.append(_f(tot("Hiho_Kei")) + ",")
        out.append(_f(tot("Hiho_Noufu")) + ",")
        for dankai in (ZENGAKU, MENJO_3_4, MENJO_1_2, MENJO_1_4):
            out.append(_f(tot("Hiho_Menjo", dankai)) + ",")
        out.append(_f(tot("Fuka_Hiho")) + "\n")
        fp.write("".join(out))

    def table(title, shus):
        fp.write(title + "\n")
        fp.write(_HIHO_COLS + "\n")
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            row(nendo, shus)

    table("被保険者数  種別=0（総計）", (2, 3, 5, 6))
    table("被保険者数  種別=1（１号計）", (2, 5))
    for shubetu in (2, 3):
        table("被保険者数  種別=%d" % shubetu, (shubetu,))
    table("被保険者数  種別=4（３号計）", (3, 6))
    for shubetu in (5, 6):
        table("被保険者数  種別=%d" % shubetu, (shubetu,))


# 節の定義。`cols` は列名、`fields` は「その欄をどう出すか」。
#   "欄名"           その欄をそのまま
#   "sum"            `sum`（`total` の欄を並べた順に足したもの）
#   "avg"            `sum / ninzu`（`ninzu` が 0 以下なら 0）
#   "menjo_ss"       `menjo[SUM][SUM]`
_SECTIONS = (
    # (出力先, 見出し, 配列名, 添字の形, 列名, total, fields)
    (_PRINT_ROREI, "新法老齢年金  ", "Rorei", "rorei",
     "年度,受給ﾒ数,年金額,納付分,免除分,下支え分,平均年金額,付加年金",
     ("noufu", "menjo_ss", "rofuku_shitasasae"),
     ("ninzu", "sum", "noufu", "menjo_ss",
      "rofuku_shitasasae", "avg", "fuka")),

    (_PRINT_ROREI, "旧法老齢年金  ", "Rorei_Kyu", "rorei",
     "年度,受給ﾒ数,年金額,納付分,免除分,嵩上げ納付分,嵩上げ免除分,"
     "下支え分,平均年金額,付加年金",
     ("noufu", "menjo", "kasa_noufu", "kasa_menjo", "rofuku_shitasasae"),
     ("ninzu", "sum", "noufu", "menjo",
      "kasa_noufu", "kasa_menjo",
      "rofuku_shitasasae", "avg", "fuka")),

    (_PRINT_ROREI, "旧法通老年金  ", "Turo_Kyu", "rorei",
     "年度,受給ﾒ数,年金額,納付分,免除分,嵩上げ納付分,嵩上げ免除分,"
     "下支え分,平均年金額,付加年金",
     ("noufu", "menjo", "kasa_noufu", "kasa_menjo", "rofuku_shitasasae"),
     ("ninzu", "sum", "noufu", "menjo",
      "kasa_noufu", "kasa_menjo",
      "rofuku_shitasasae", "avg", "fuka")),

    (_PRINT_ROREI, "５年年金  ", "Gonen", "rorei",
     "年度,受給ﾒ数,年金額,平均年金額",
     ("noufu",),
     ("ninzu", "noufu", "avg")),

    (_PRINT_SHOGAI, "新法障害年金（一般）  ", "Shogai_Ippan", "nenrei",
     "年度,受給ﾒ数,年金額,基本額,加給額,平均年金額",
     ("kihon", "kakyu"),
     ("ninzu", "sum", "kihon", "kakyu",
      "avg")),

    (_PRINT_SHOGAI, "新法障害年金（２０歳前）  ", "Shogai_20mae", "nenrei",
     "年度,受給ﾒ数,年金額,基本額,加給額,平均年金額",
     ("kihon", "kakyu"),
     ("ninzu", "sum", "kihon", "kakyu",
      "avg")),

    (_PRINT_SHOGAI, "旧法障害年金 ", "Shogai_Kyu", "nenrei",
     "年度,受給ﾒ数,年金額,基本額,加給額,免除額（基本の再掲）,"
     "免除額（加給の再掲）,平均年金額",
     ("kihon", "kakyu"),
     ("ninzu", "sum", "kihon", "kakyu",
      "menjo_kihon", "menjo_kakyu", "avg")),

    (_PRINT_IZOKU, "新法遺族年金（妻）  ", "Izoku_Tuma", "nenrei",
     "年度,受給ﾒ数,年金額,基本額,加給額,平均年金額",
     ("kihon", "kakyu"),
     ("ninzu", "sum", "kihon", "kakyu",
      "avg")),

    (_PRINT_IZOKU, "新法遺族年金（夫）  ", "Izoku_Otto", "nenrei",
     "年度,受給ﾒ数,年金額,基本額,加給額,平均年金額",
     ("kihon", "kakyu"),
     ("ninzu", "sum", "kihon", "kakyu",
      "avg")),

    (_PRINT_IZOKU, "新法遺族年金（子）  ", "Izoku_Ko", "flat",
     "年度,受給ﾒ数,年金額,基本額,加給額,平均年金額",
     ("kihon", "kakyu"),
     ("ninzu", "sum", "kihon", "kakyu",
      "avg")),

    (_PRINT_IZOKU, "新法寡婦年金  ", "Kafu", "flat",
     "年度,受給ﾒ数,年金額,納付額,免除額,平均年金額",
     ("noufu", "menjo_ss"),
     ("ninzu", "sum", "noufu", "menjo_ss",
      "avg")),

    (_PRINT_IZOKU, "旧法寡婦年金  ", "Kafu_Kyu", "flat",
     "年度,受給ﾒ数,年金額,納付額,免除額,平均年金額",
     ("noufu", "menjo_ss"),
     ("ninzu", "sum", "noufu", "menjo_ss",
      "avg")),

    (_PRINT_IZOKU, " 死亡一時金  ", "Ichijikin", "nenrei",
     "年度,受給ﾒ数,年金額（計）,年金額納付分,年金額付加分,平均年金額",
     ("kyufu", "kyufu_fuka"),
     ("ninzu", "sum", "kyufu", "kyufu_fuka",
      "avg")),
)


def _get(G, name, kind, shubetu, s):
    """節ごとの添字の形（`[…][0][KURI_AGE_SAGE_SUM]` など）を当てる。"""
    a = getattr(G, name)
    if kind == "rorei":
        return a[shubetu, s, 0, KURI_AGE_SAGE_SUM]
    if kind == "nenrei":
        return a[shubetu, s, 0]
    return a[shubetu, s]           # "flat"


def _val(rec, spec):
    """`spec` は欄名か、`menjo[SUM][SUM]` を指す `"menjo_ss"`。"""
    if spec == "menjo_ss":
        return rec["menjo"][SUM, SUM]
    return rec[spec]


def _print_sections(G):
    """13 の節（`printout.c:363-1180`）。"""
    for out, title, name, kind, cols, total, fields in _SECTIONS:
        fp = G.fp_out[out]

        for shubetu in (SHUBETU_SUM_NENDOKAN,) + tuple(
                range(1, MAX_SHUBETU)):
            label = 0 if shubetu == SHUBETU_SUM_NENDOKAN else shubetu
            fp.write("%s種別=%d\n" % (title, label))
            fp.write(cols + "\n")

            for nendo in range(SHONENDO, SAISHUNENDO + 1):
                s = nendo - SHONENDO
                rec = _get(G, name, kind, shubetu, s)

                # `sum` は原本が書いてある順に足す（**先頭の欄から**
                # 始める。0. から足すと -0. のとき符号が変わる）
                v = _val(rec, total[0])
                for f in total[1:]:
                    v = v + _val(rec, f)

                if rec["ninzu"] > 0.:
                    average = v / rec["ninzu"]
                else:
                    average = 0.

                parts = ["%d," % nendo]
                for i, spec in enumerate(fields):
                    if spec == "sum":
                        x = v
                    elif spec == "avg":
                        x = average
                    else:
                        x = _val(rec, spec)
                    parts.append(_f(x)
                                 + ("\n" if i == len(fields) - 1 else ","))
                fp.write("".join(parts))

        # 5年年金の節のあとに満額の表が3つ入る
        if name == "Gonen":
            _print_mangaku(G)


def _print_mangaku(G):
    """基礎年金満額の表3つ（`printout.c:615-668`）。

    見出しは「67歳以下・68歳・…・115歳」だが、書くのは
    `Full_Pension[年度][nenrei - UNDER_67]` = **0〜48歳**のぶん。
    年齢の添字が 67 ずれている（J4）。移植版はそのまま写した。
    """
    fp = G.fp_out[_PRINT_ROREI]

    for title, name in (("基礎年金満額（基本額）", "Full_Pension"),
                        ("基礎年金満額（加給額１、２子）",
                         "Kakyu_Tanka_12shi"),
                        ("基礎年金満額（加給額３子以降）",
                         "Kakyu_Tanka_3shiiko")):
        fp.write(title + "\n")
        fp.write("年度,67歳以下,")
        for nenrei in range(68, MAX_ROREI_JUKYU):
            fp.write("%d歳," % nenrei)
        fp.write("%d歳\n" % MAX_ROREI_JUKYU)

        a = getattr(G, name)
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            s = nendo - SHONENDO
            parts = ["%d," % nendo]
            for nenrei in range(UNDER_67, MAX_ROREI_JUKYU):
                parts.append(_f(a[s, nenrei - UNDER_67]) + ",")
            parts.append(_f(a[s, MAX_ROREI_JUKYU - UNDER_67]) + "\n")
            fp.write("".join(parts))
