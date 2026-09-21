# -*- coding: utf-8 -*-
"""
国民年金/str_op.c の忠実移植（`struct` を値で受け渡す演算）
============================================================
832 行。③の特徴は **8つの `struct` を値で受け渡す**こと。
`scalar` `add` `multiply` `nendokan` `nendokan_64` `adjustbenefit`
`average_by_ninzu` `scalar_2` が**型ごとに多重定義**されている。

| 演算 | hihokensha | rorei | rorei_kyu | gonen | shogai | izoku | kafu | ichijikin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `scalar` | ○ | ○ | ○ | ○ | ○ | ○ | ○ | — |
| `scalar_2` | ○ | — | — | — | — | — | — | — |
| `add` | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| `multiply` | — | ○ | ○ | — | ○ | ○ | ○ | — |
| `nendokan` | — | ○ | ○ | ○ | ○※ | ○※ | ○ | ○ |
| `nendokan_64` | — | ○ | ○ | ○ | ○ | ○ | — | ○ |
| `adjustbenefit` | — | ○ | ○ | ○ | ○ | ○ | ○ | — |
| `average_by_ninzu` | ○ | — | — | — | — | — | — | — |

※ `shogai` と `izoku` の `nendokan` は**改定率を2つ**取る
（`kaiteiritu1` を基本、`kaiteiritu2` を加給に当てる）。

Python には多重定義が無いので、`dtype` で振り分ける
-----------------------------------------------------
呼ぶ側は原本と同じ見た目で書ける。

```python
Rorei_Nendomatu[i][j][k] = str_op.scalar(0.5, Rorei_Zero)
```

`nendokan` の重み — 支払遅れ2か月
---------------------------------
```c
#define SHIHARAIOKURE 2

OutputStruct.noufu
 = ( InputStruct1.noufu * ( SHIHARAIOKURE + 6. * kaiteiritu )
     + InputStruct2.noufu * ( 6. - SHIHARAIOKURE ) ) / 12.;
```

`InputStruct1` が前年度末、`InputStruct2` が当年度末。年金は
**2か月遅れで支払う**ので、年度の 12 か月を

- 前年度末の額 × （2 か月ぶん ＋ 6 か月ぶん × 改定率）
- 当年度末の額 × （6 − 2 = 4 か月ぶん）

に割る。2 + 6 + 4 = 12。改定率は4月分から効くので、前年度末の額の
6 か月ぶんだけに掛かる。

**人数は別の式。**

```c
OutputStruct.ninzu = ( InputStruct1.ninzu + InputStruct2.ninzu ) / 2.;
```

単純平均。`(a * 6. + b * 6.) / 12.` に**書き換えてはいけない**
（丸めが変わる）。移植版は原本の式のまま書く。

**付加年金は改定率を掛けない。**

```c
OutputStruct.fuka
 = ( InputStruct1.fuka * ( SHIHARAIOKURE + 6. ) + InputStruct2.fuka * ( 6. - SHIHARAIOKURE ) ) / 12.;
```

`6. * kaiteiritu` ではなく `6.`。付加年金（`Full_Pension_Fuka` =
2,400円）は物価にも賃金にもスライドしないので、改定率を掛けない。
`ichijikin` の `kyufu_fuka` も同じ。

`nendokan_64` は「64歳の年」の3項版
-----------------------------------
```c
OutputStruct.ninzu = ( InputStruct1.ninzu + InputStruct2.ninzu + InputStruct3.ninzu ) / 2.;
```

**3つ足して2で割る。** 平均ではない。繰上げ・繰下げで受給が
始まる年は、年度の途中で2つの区分にまたがるので、
`InputStruct2` と `InputStruct3` が「当年度末の2つの区分」。
人数は両方を足したものを前年度末と平均する形になっていて、
**2で割るのが正しい**（`(a + (b + c)) / 2` で b + c が当年度末の計）。
ただし足す順が `a + b + c` なので、`a + (b + c)` とは
**丸めが変わりうる**。原本のまま左から足す。

`adjustbenefit` はマクロ経済スライドを年金額だけに掛ける
-------------------------------------------------------
```c
OutputStruct.ninzu = InputStruct.ninzu;          /* 人数は変えない */
OutputStruct.noufu = scalar * InputStruct.noufu;
…
OutputStruct.fuka = InputStruct.fuka;            /* 付加年金は変えない */
```

`rorei` と `rorei_kyu` は `ninzu` と `fuka` を素通しし、ほかを掛ける。
`gonen` `shogai` `izoku` `kafu` は `ninzu` だけ素通し
（`fuka` の欄が無いので）。

`scalar_2` の「特定期間」
------------------------
```c
if( nendo <= TOKUTEI_NENDO ) { kokko1 = 1; kokko2 = 2; }
else                        { kokko1 = 2; kokko2 = 1; }
…
if( nendo == TOKUTEI_NENDO ) {
  OutputStruct.menjo[dankai][kokko1] = scalar * InputStruct.menjo[dankai][kokko1] * ( TOKUTEI_TUKI - 4 ) / 12.;
  OutputStruct.menjo[dankai][kokko2] = scalar * InputStruct.menjo[dankai][kokko2] * ( 16 - TOKUTEI_TUKI ) / 12.;
}
else {
  OutputStruct.menjo[dankai][kokko1] = scalar * InputStruct.menjo[dankai][kokko1];
  OutputStruct.menjo[dankai][kokko2] = 0.;
}
OutputStruct.menjo[dankai][SUM] = OutputStruct.menjo[dankai][kokko1] + OutputStruct.menjo[dankai][kokko2];
```

国庫負担が3分の1から2分の1に変わったのは **2009年度（`TOKUTEI_NENDO`）
の4月（`TOKUTEI_TUKI` = 4）**。変わった年度は、その年度のうち
何か月が旧・何か月が新かで按分する。

`TOKUTEI_TUKI` が 4 なので

    ( TOKUTEI_TUKI - 4 ) / 12. = 0 / 12  = 0     旧（3分の1）は 0 か月
    ( 16 - TOKUTEI_TUKI ) / 12. = 12 / 12 = 1    新（2分の1）が 12 か月

で、**2009年度は丸ごと2分の1**になる。一見「片方を必ず 0 にする
死んだ式」に見えるが、`TOKUTEI_TUKI` を 7（7月）にすれば
3 / 12 と 9 / 12 になる**書き換えられる形**。意図どおり。
`検証/原本の不具合.md` の E の仲間。

`menjo[dankai][SUM]`（`SUM` = 0）は**その段階の計**。
`seid.c` が `Kokko_Wariai[0]` に何も入れない（0 のまま）のは、
この計の欄に国庫負担の割合を掛けても 0 になるようにするため。

`average_by_ninzu` は 0 割りを避ける
-----------------------------------
```c
OutputStruct.kikan = (InputStruct.ninzu > 0.) ? InputStruct.kikan / InputStruct.ninzu : 0.;
```

`ninzu > 0.` を**欄ごとに毎回見る**（21回）。`ninzu` が 0 なら
全部 0。負の `ninzu` も 0 になる（`>= 0.` ではなく `> 0.`）。

移植の書き方
------------
`menjo[MENJO_DANKAI][KOKKO_HIKIAGE]` は NumPy の (5, 3) の
部分配列なので、**そのまま要素ごとに演算**できる（`out["menjo"] =
s * x["menjo"]`）。要素ごとの掛け算・足し算は順番に依らないので
**ビット一致する**。原本の二重ループを1行にまとめた形。
"""
import numpy as np

from glva import (GONEN, HIHOKENSHA, ICHIJIKIN, IZOKU, KAFU, ROREI,
                  ROREI_KYU, SHOGAI)
from setconst import SUM, TOKUTEI_NENDO, TOKUTEI_TUKI

__all__ = ["SHIHARAIOKURE", "zero", "scalar", "scalar_2", "add", "multiply",
           "nendokan", "nendokan_64", "adjustbenefit", "average_by_ninzu"]

# str_op.c:7
SHIHARAIOKURE = 2

# 型ごとの「ふつうに扱う欄」（`ninzu` と、改定率を掛けない欄を除く）
#   ninzu  … `nendokan` では単純平均、`adjustbenefit` では素通し
#   fuka / kyufu_fuka … `nendokan` で改定率を掛けない、
#                       `adjustbenefit` で素通し（`rorei` 系のみ）
_FIELDS = {
    HIHOKENSHA: ("kikan", "noufu", "menjo", "gakusei", "wakamono", "fuka"),
    ROREI: ("noufu", "menjo", "rofuku_shitasasae", "fuka"),
    ROREI_KYU: ("noufu", "menjo", "kasa_noufu", "kasa_menjo",
                "rofuku_shitasasae", "fuka"),
    GONEN: ("noufu",),
    SHOGAI: ("kihon", "kakyu", "menjo_kihon", "menjo_kakyu"),
    IZOKU: ("kihon", "kakyu"),
    KAFU: ("noufu", "menjo"),
    ICHIJIKIN: ("kyufu", "kyufu_fuka"),
}

# `nendokan` で `6. * kaiteiritu` ではなく `6.` を使う欄（付加年金）
_NO_KAITEI = {
    ROREI: ("fuka",),
    ROREI_KYU: ("fuka",),
    ICHIJIKIN: ("kyufu_fuka",),
}

# `adjustbenefit` で素通しする欄（`ninzu` は常に素通し）
_KEEP = {
    ROREI: ("fuka",),
    ROREI_KYU: ("fuka",),
}

# `shogai` `izoku` の `nendokan` で `kaiteiritu2` を当てる欄（加給）
_KAITEI2 = {
    SHOGAI: ("kakyu", "menjo_kakyu"),
    IZOKU: ("kakyu",),
}


def zero(dt):
    """全部 0 の1個（原本の `*_Zero` と同じ姿）。"""
    return np.zeros((), dtype=dt)


def scalar(s, x):
    """`scalar( double , struct )` の忠実移植。**全部の欄に掛ける。**"""
    dt = x.dtype
    out = np.zeros((), dtype=dt)
    out["ninzu"] = s * x["ninzu"]
    for f in _FIELDS[dt]:
        out[f] = s * x[f]
    return out


def scalar_2(s, x, nendo):
    """str_op.c:34 の忠実移植（`hihokensha` だけ）。特定期間で按分する。"""
    assert x.dtype == HIHOKENSHA, "scalar_2 は hihokensha だけ"
    out = np.zeros((), dtype=HIHOKENSHA)

    if nendo <= TOKUTEI_NENDO:
        kokko1 = 1
        kokko2 = 2
    else:
        kokko1 = 2
        kokko2 = 1

    out["ninzu"] = s * x["ninzu"]
    out["kikan"] = s * x["kikan"]
    out["noufu"] = s * x["noufu"]

    om = out["menjo"]
    xm = x["menjo"]
    if nendo == TOKUTEI_NENDO:
        # `TOKUTEI_TUKI` は 4 なので、前者は必ず 0・後者は 12/12
        om[:, kokko1] = s * xm[:, kokko1] * (TOKUTEI_TUKI - 4) / 12.
        om[:, kokko2] = s * xm[:, kokko2] * (16 - TOKUTEI_TUKI) / 12.
    else:
        om[:, kokko1] = s * xm[:, kokko1]
        om[:, kokko2] = 0.
    om[:, SUM] = om[:, kokko1] + om[:, kokko2]

    out["gakusei"] = s * x["gakusei"]
    out["wakamono"] = s * x["wakamono"]
    out["fuka"] = s * x["fuka"]
    return out


def add(a, b):
    """`add( struct , struct )` の忠実移植。**全部の欄を足す。**"""
    dt = a.dtype
    assert b.dtype == dt, "add: 型が違う（%s と %s）" % (dt, b.dtype)
    out = np.zeros((), dtype=dt)
    out["ninzu"] = a["ninzu"] + b["ninzu"]
    for f in _FIELDS[dt]:
        out[f] = a[f] + b[f]
    return out


def multiply(a, b):
    """`multiply( struct , struct )` の忠実移植。**欄ごとに掛ける。**

    `hihokensha` `gonen` `ichijikin` には無い（原本に定義が無い）。
    """
    dt = a.dtype
    if dt not in (ROREI, ROREI_KYU, SHOGAI, IZOKU, KAFU):
        raise TypeError("multiply はこの型に無い（原本に定義が無い）")
    assert b.dtype == dt, "multiply: 型が違う"
    out = np.zeros((), dtype=dt)
    out["ninzu"] = a["ninzu"] * b["ninzu"]
    for f in _FIELDS[dt]:
        out[f] = a[f] * b[f]
    return out


def nendokan(a, b, kaiteiritu, kaiteiritu2=None):
    """`nendokan( struct , struct , double [, double] )` の忠実移植。

    `a` が前年度末、`b` が当年度末。支払遅れ2か月ぶんを織り込んで
    年度間の額にする。`shogai` と `izoku` は改定率を2つ取る
    （`kaiteiritu` が基本、`kaiteiritu2` が加給）。
    """
    dt = a.dtype
    if dt == HIHOKENSHA:
        raise TypeError("nendokan は hihokensha に無い（原本に定義が無い）")
    assert b.dtype == dt, "nendokan: 型が違う"
    if dt in _KAITEI2:
        assert kaiteiritu2 is not None, (
            "%s の nendokan は改定率を2つ取る" % dt)
    else:
        assert kaiteiritu2 is None, (
            "%s の nendokan は改定率を1つしか取らない" % dt)

    out = np.zeros((), dtype=dt)
    # 人数は単純平均（重み付けの式に直してはいけない）
    out["ninzu"] = (a["ninzu"] + b["ninzu"]) / 2.

    w2 = 6. - SHIHARAIOKURE
    w1 = SHIHARAIOKURE + 6. * kaiteiritu
    w1b = (SHIHARAIOKURE + 6. * kaiteiritu2) if kaiteiritu2 is not None \
        else None
    no_kaitei = _NO_KAITEI.get(dt, ())
    kaitei2 = _KAITEI2.get(dt, ())

    for f in _FIELDS[dt]:
        if f in no_kaitei:
            # 付加年金は改定率を掛けない（`6. * kaiteiritu` ではなく `6.`）
            out[f] = (a[f] * (SHIHARAIOKURE + 6.) + b[f] * w2) / 12.
        elif f in kaitei2:
            out[f] = (a[f] * w1b + b[f] * w2) / 12.
        else:
            out[f] = (a[f] * w1 + b[f] * w2) / 12.
    return out


def nendokan_64(a, b, c, kaiteiritu):
    """`nendokan_64( struct , struct , struct , double )` の忠実移植。

    当年度末が2つの区分（`b` と `c`）にまたがる年。**人数は3つ足して
    2で割る**（`( a + b + c ) / 2.`。足す順も原本のまま）。
    `kafu` には無い（原本に定義が無い）。
    """
    dt = a.dtype
    if dt in (HIHOKENSHA, KAFU):
        raise TypeError("nendokan_64 はこの型に無い（原本に定義が無い）")
    assert b.dtype == dt and c.dtype == dt, "nendokan_64: 型が違う"

    out = np.zeros((), dtype=dt)
    out["ninzu"] = (a["ninzu"] + b["ninzu"] + c["ninzu"]) / 2.

    w1 = SHIHARAIOKURE + 6. * kaiteiritu
    w2 = 6. - SHIHARAIOKURE
    no_kaitei = _NO_KAITEI.get(dt, ())

    for f in _FIELDS[dt]:
        if f in no_kaitei:
            out[f] = (a[f] * (SHIHARAIOKURE + 6.)
                      + (b[f] + c[f]) * w2) / 12.
        else:
            out[f] = (a[f] * w1 + (b[f] + c[f]) * w2) / 12.
    return out


def adjustbenefit(s, x):
    """`adjustbenefit( double , struct )` の忠実移植。

    マクロ経済スライドの調整率を**年金額の欄だけ**に掛ける。
    人数（`ninzu`）と付加年金（`fuka`）は素通し。
    `hihokensha` と `ichijikin` には無い（原本に定義が無い）。
    """
    dt = x.dtype
    if dt in (HIHOKENSHA, ICHIJIKIN):
        raise TypeError("adjustbenefit はこの型に無い（原本に定義が無い）")
    out = np.zeros((), dtype=dt)
    out["ninzu"] = x["ninzu"]           # 人数は掛けない
    keep = _KEEP.get(dt, ())
    for f in _FIELDS[dt]:
        if f in keep:
            out[f] = x[f]               # 付加年金は掛けない
        else:
            out[f] = s * x[f]
    return out


def average_by_ninzu(x):
    """str_op.c:105 の忠実移植（`hihokensha` だけ）。1人あたりに直す。

    `ninzu > 0.` を**欄ごとに毎回**見る（原本のとおり）。
    `ninzu` が 0 以下なら全部 0。`ninzu` の欄そのものは素通し。
    """
    assert x.dtype == HIHOKENSHA, "average_by_ninzu は hihokensha だけ"
    out = np.zeros((), dtype=HIHOKENSHA)
    n = x["ninzu"]
    out["ninzu"] = n
    pos = (n > 0.)
    for f in _FIELDS[HIHOKENSHA]:
        out[f] = (x[f] / n) if pos else 0.
    return out
