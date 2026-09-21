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
           "nendokan", "nendokan_64", "adjustbenefit", "average_by_ninzu",
           # 軸をまとめて処理する版（原本には無い。速度のため）
           "scalar_arr", "adjustbenefit_arr", "multiply_arr", "add_arr",
           "scalar_2_arr", "average_by_ninzu_arr",
           # 縮約の間接費を削るための平べったい view
           "flat_view"]

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


# ---- 平べったい float64 として扱う仕掛け（速度のため） --------------
#
# `add` `scalar` `multiply` は**全部の欄に同じ演算を当てる**。欄ごとに
# 代入していくと、構造体1個につき 5.25us かかる（実測）。ほぼ全部が
# NumPy の欄アクセスの間接費。
#
# 構造体は「欄数 × 8 バイト、詰め物なし」（`test_structの寸法に詰め物が
# 無い` が原本と突き合わせて保証している）ので、**float64 が n 個の
# subarray として view** すれば1回のベクトル演算で済む。itemsize が
# 変わらないので 0-d のままでも `numpy.void`（構造体配列をフル添字した
# 戻り）でも view できる。実測 2.26us（2.33倍）。
#
# **ビット一致は自動的に保たれる。** 各欄の出力は double 1〜2個の1回の
# 演算で、総和を取っていない（縮約ではない）ので、書き方を変えても
# 演算の順序が変わらない。全8型・1,964通り（NaN・±Inf・±0・極端な指数を
# 含む）で欄ごと版と CRC32 が一致することを確認してある。
#
# ただし **小さい構造体では欄ごとに回すほうが速い。** view と ufunc の
# 呼び出しに1回あたり 2.1us ほどの床があるので、スロット数が少ないと
# 元が取れない。実測（1回あたり、欄ごと版 → 平べったい版）:
#
#     add   HIHOKENSHA(21) 5.21 → 2.41us  2.16倍
#           ROREI     (19) 3.98 → 2.27us  1.75倍
#           ROREI_KYU  (7) 4.77 → 2.37us  2.01倍
#           SHOGAI     (5) 3.45 → 2.19us  1.58倍
#           IZOKU      (3) 2.32 → 2.42us  0.96倍 ← 遅くなる
#           GONEN      (2) 1.67 → 1.78us  0.94倍 ← 遅くなる
#
# 境目は5スロット。**両方の実装を残して型ごとに速いほうを選ぶ。**
# どちらの経路もビット一致するので、この閾値は速度だけの問題で、
# 結果には影響しない。
FLAT_MIN = 5

_FLAT = {}


def _flat(dt):
    """平べったく扱うための dtype。**小さすぎる型には `None` を返す。**

    「速いほうを選ぶ」判断と dtype の取得を1回の辞書引きに畳んでいる。
    呼ぶ側は `f = _flat(dt)` して `f is None` なら欄ごとに回す。
    """
    try:
        return _FLAT[dt]
    except KeyError:
        n = dt.itemsize // 8
        f = np.dtype((np.float64, n)) if n >= FLAT_MIN else None
        _FLAT[dt] = f
        return f


def _check_covered():
    """`ninzu` ＋ `_FIELDS[dt]` が**全スロットを覆っている**ことを確かめる。

    覆っていない欄があると、平べったく扱う版は欄ごと版と違う結果を出す
    （欄ごと版はその欄を 0 のまま残す）。欄を足したときに黙って壊れない
    ように、読み込み時に落とす。
    """
    for dt, names in _FIELDS.items():
        n = 0
        for f in ("ninzu",) + names:
            sub = dt.fields[f][0]
            n += int(np.prod(sub.shape)) if sub.shape else 1
        if n != dt.itemsize // 8:
            raise AssertionError(
                "str_op: %s の欄が `ninzu` + _FIELDS で覆えていない"
                "（%d スロットのうち %d）。平べったく扱う版が使えない"
                % (dt.names, dt.itemsize // 8, n))


_check_covered()


def _slots(dt, names):
    """欄の名前から、平べったく見たときのスロット番号の配列を作る。

    `menjo` のように `(5, 3)` の欄は15スロットを占める。実測で確認した
    とおり `ninzu` は全型でスロット0、欄は宣言順に連続している。
    """
    out = []
    for f in names:
        sub, off = dt.fields[f][0], dt.fields[f][1]
        n = int(np.prod(sub.shape)) if sub.shape else 1
        out.extend(range(off // 8, off // 8 + n))
    return np.array(out, dtype=np.intp)


# `adjustbenefit` で素通しするスロット（`ninzu` ＋ 付加年金）
_KEEP_SLOTS = {
    dt: _slots(dt, ("ninzu",) + _KEEP.get(dt, ()))
    for dt in _FIELDS if dt not in (HIHOKENSHA, ICHIJIKIN)
}

# `nendokan` の重みの当て方。スロットごとに3種類に分かれる
#   normal     … `SHIHARAIOKURE + 6. * kaiteiritu`
#   no_kaitei  … `SHIHARAIOKURE + 6.`（付加年金は改定率を掛けない）
#   kaitei2    … `SHIHARAIOKURE + 6. * kaiteiritu2`（加給）
_NDK_SLOTS = {}
for _dt in _FIELDS:
    if _dt is HIHOKENSHA:
        continue
    _nk = _NO_KAITEI.get(_dt, ())
    _k2 = _KAITEI2.get(_dt, ())
    _nm = tuple(f for f in _FIELDS[_dt] if f not in _nk and f not in _k2)
    _NDK_SLOTS[_dt] = (_slots(_dt, _nm), _slots(_dt, _nk), _slots(_dt, _k2))
del _dt, _nk, _k2, _nm

# `nendokan` の重みベクトルの控え。改定率は年度ごとにしか変わらないので、
# 同じ (型, 改定率, 加給の改定率) が何万回も来る。毎回組むと小さい型では
# 欄ごと版より遅くなったので控えておく（キーの純粋な関数なので安全）。
_NDK_W1 = {}
_NDK_W1_MAX = 4096


def _ndk_w1(dt, kaiteiritu, kaiteiritu2):
    """`nendokan` のスロットごとの重み。`ninzu` の分は 0（別に入れる）。"""
    key = (dt, kaiteiritu, kaiteiritu2)
    w = _NDK_W1.get(key)
    if w is None:
        normal, no_kaitei, kaitei2 = _NDK_SLOTS[dt]
        w = np.empty(dt.itemsize // 8, dtype=np.float64)
        w[normal] = SHIHARAIOKURE + 6. * kaiteiritu
        if len(no_kaitei):
            # 付加年金は改定率を掛けない（`6. * kaiteiritu` ではなく `6.`）
            w[no_kaitei] = SHIHARAIOKURE + 6.
        if len(kaitei2):
            w[kaitei2] = SHIHARAIOKURE + 6. * kaiteiritu2
        w[0] = 0.
        w.flags.writeable = False       # 控えを壊さない
        if len(_NDK_W1) >= _NDK_W1_MAX:
            _NDK_W1.clear()             # 際限なく増えないように
        _NDK_W1[key] = w
    return w


def scalar(s, x):
    """`scalar( double , struct )` の忠実移植。**全部の欄に掛ける。**"""
    dt = x.dtype
    f = _flat(dt)
    if f is not None:
        out = np.empty((), dtype=dt)
        np.multiply(s, x.view(f), out=out.view(f))
        return out
    out = np.zeros((), dtype=dt)
    out["ninzu"] = s * x["ninzu"]
    for f in _FIELDS[dt]:
        out[f] = s * x[f]
    return out


# `menjo` の列ごとのスロット番号。`hihokensha` の `menjo` は (5, 3) で
# スロット3から始まるので、列 k は [3 + d*3 + k for d in 0..4]。
_M_COL = tuple(
    np.array([(HIHOKENSHA.fields["menjo"][1] // 8) + d * 3 + k
              for d in range(5)], dtype=np.intp)
    for k in range(3))


def scalar_2(s, x, nendo):
    """str_op.c:34 の忠実移植（`hihokensha` だけ）。特定期間で按分する。

    平べったく扱うが、**`s * x * c / 12.` の演算順は崩さない**。
    `x * (s * c / 12.)` に畳むと丸めが変わる。いったん全スロットに
    `s` を掛けてから、`menjo` の列だけを原本と同じ順で加工する。
    """
    assert x.dtype == HIHOKENSHA, "scalar_2 は hihokensha だけ"
    f = _flat(HIHOKENSHA)
    out = np.empty((), dtype=HIHOKENSHA)
    xv, ov = x.view(f), out.view(f)

    # まず全スロット `s * x`。`ninzu` `kikan` `noufu` `gakusei`
    # `wakamono` `fuka` と `menjo[:, kokko1]` はこれで確定する
    np.multiply(s, xv, out=ov)

    if nendo <= TOKUTEI_NENDO:
        i1, i2 = _M_COL[1], _M_COL[2]
    else:
        i1, i2 = _M_COL[2], _M_COL[1]

    if nendo == TOKUTEI_NENDO:
        # `TOKUTEI_TUKI` は 4 なので、前者は必ず 0・後者は 12/12。
        # `(s * x) * c / 12.` の形を保つ
        ov[i1] = ov[i1] * (TOKUTEI_TUKI - 4) / 12.
        ov[i2] = ov[i2] * (16 - TOKUTEI_TUKI) / 12.
    else:
        ov[i2] = 0.

    # `menjo[dankai][SUM]` はその段階の計。足す順も原本のまま
    ov[_M_COL[SUM]] = ov[i1] + ov[i2]
    return out


def add(a, b):
    """`add( struct , struct )` の忠実移植。**全部の欄を足す。**"""
    dt = a.dtype
    assert b.dtype == dt, "add: 型が違う（%s と %s）" % (dt, b.dtype)
    f = _flat(dt)
    if f is not None:
        out = np.empty((), dtype=dt)
        np.add(a.view(f), b.view(f), out=out.view(f))
        return out
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
    f = _flat(dt)
    if f is not None:
        out = np.empty((), dtype=dt)
        np.multiply(a.view(f), b.view(f), out=out.view(f))
        return out
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

    w2 = 6. - SHIHARAIOKURE
    fl = _flat(dt)
    if fl is not None:
        out = np.empty((), dtype=dt)
        av, bv, ov = a.view(fl), b.view(fl), out.view(fl)
        # スロットごとの重みを当てて `(a * w1 + b * w2) / 12.` を一度に。
        # 演算の順序（掛け・掛け・足し・割り）は原本のまま。要素ごとなので
        # ビット一致する
        np.divide(av * _ndk_w1(dt, kaiteiritu, kaiteiritu2) + bv * w2,
                  12., out=ov)
        # 人数は単純平均（重み付けの式に直してはいけない）
        ov[0] = (av[0] + bv[0]) / 2.
        return out

    out = np.zeros((), dtype=dt)
    out["ninzu"] = (a["ninzu"] + b["ninzu"]) / 2.
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

    w2 = 6. - SHIHARAIOKURE
    fl = _flat(dt)
    if fl is not None:
        out = np.empty((), dtype=dt)
        av, bv, cv = a.view(fl), b.view(fl), c.view(fl)
        ov = out.view(fl)
        # 改定率を1つしか取らないので、加給の欄もふつうの重みで扱う
        # （原本が `no_kaitei` 以外を一様に扱っている）。`_ndk_w1` に
        # 同じ改定率を2つ渡すとその形になる
        # `( b + c ) * w2` の順も原本のまま
        np.divide(av * _ndk_w1(dt, kaiteiritu, kaiteiritu)
                  + (bv + cv) * w2, 12., out=ov)
        # **人数は3つ足して2で割る**（足す順も原本のまま）
        ov[0] = (av[0] + bv[0] + cv[0]) / 2.
        return out

    out = np.zeros((), dtype=dt)
    out["ninzu"] = (a["ninzu"] + b["ninzu"] + c["ninzu"]) / 2.
    w1 = SHIHARAIOKURE + 6. * kaiteiritu
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
    f = _flat(dt)
    if f is not None:
        out = np.empty((), dtype=dt)
        xv, ov = x.view(f), out.view(f)
        # いったん全部に掛けてから、素通しの欄（人数・付加年金）を写し戻す。
        # 写し戻しは掛け算ではなく複写なので、原本の `out[f] = x[f]` と
        # 1ビットも変わらない（1.0 を掛けて済ませると NaN の中身が
        # 変わりうる）
        np.multiply(s, xv, out=ov)
        k = _KEEP_SLOTS[dt]
        ov[k] = xv[k]
        return out

    out = np.zeros((), dtype=dt)
    out["ninzu"] = x["ninzu"]           # 人数は掛けない
    keep = _KEEP.get(dt, ())
    for f in _FIELDS[dt]:
        if f in keep:
            out[f] = x[f]               # 付加年金は掛けない
        else:
            out[f] = s * x[f]
    return out


# ---- 軸をまとめて処理する版（呼ぶ回数を減らすため） ----------------
#
# `scalar` `adjustbenefit` を構造体1個ずつ呼ぶと、1回 2.1us の床が
# そのまま回数ぶん効く。**軸が独立なら、まとめて1回で済む。**
#
#     nenrei 軸51本を1本ずつ足す      335.24 us
#     まとめて1回のベクトル加算          2.82 us   119倍（CRC32 一致）
#
# **ビット一致は保たれる。** 要素ごとの演算をまとめても、各要素にかかる
# 演算の順序は変わらない（`検証/移植/README.md`「ベクトル化はビット一致を
# 壊さない」）。**縮約（総和・総乗）だけは順序を変えてはいけない**ので、
# ここには置かない。
#
# 呼ぶ側の責任
# ------------
# まとめてよいのは「**出力のスロットごとに、当たる演算の列が
# 変わらない**」ときだけ。たとえば前年度を読んで当年度に書くなら、
# 読む先と書く先が別なので年齢軸をまとめられる。逆に同じスロットへ
# 何本も足し込む（年齢を潰して集計するなど）場合は、足す順が変わるので
# **まとめてはいけない**。


def scalar_arr(s, x, out):
    """`scalar` の軸まとめ版。`out` に書き込んで返す。

    `x` は構造体の配列、`s` はスカラーか `x` の形に放送できる配列
    （`x` の形に `(1,)` を足した形。年齢ごとに違う係数を当てるときは
    `s[:, None, None]` のようにして渡す）。`out` は `x` と同じ形・
    同じ型で、**`x` と重なっていてはいけない**。
    """
    dt = x.dtype
    f = _flat(dt)
    if f is None:                       # 小さい型でも軸がまとまるなら得
        f = np.dtype((np.float64, dt.itemsize // 8))
    np.multiply(s, x.view(f), out=out.view(f))
    return out


def adjustbenefit_arr(s, x, out):
    """`adjustbenefit` の軸まとめ版。`out` に書き込んで返す。

    引数の約束は `scalar_arr` と同じ。素通しする欄（人数・付加年金）は
    掛けずに写すので、`s` の形は最後に軸を1つ足した形にする。
    """
    dt = x.dtype
    if dt in (HIHOKENSHA, ICHIJIKIN):
        raise TypeError("adjustbenefit はこの型に無い（原本に定義が無い）")
    f = _flat(dt)
    if f is None:
        f = np.dtype((np.float64, dt.itemsize // 8))
    xv, ov = x.view(f), out.view(f)
    np.multiply(s, xv, out=ov)
    # 素通しの欄を写し戻す（掛け算ではなく複写。`adjustbenefit` と同じ）
    k = _KEEP_SLOTS[dt]
    ov[..., k] = xv[..., k]
    return out


def multiply_arr(a, b, out):
    """`multiply` の軸まとめ版。`out` に書き込んで返す。

    `a` と `b` は同じ型の構造体の配列（放送可）。
    """
    dt = a.dtype
    if dt not in (ROREI, ROREI_KYU, SHOGAI, IZOKU, KAFU):
        raise TypeError("multiply はこの型に無い（原本に定義が無い）")
    assert b.dtype == dt, "multiply_arr: 型が違う"
    f = _flat(dt)
    if f is None:
        f = np.dtype((np.float64, dt.itemsize // 8))
    np.multiply(a.view(f), b.view(f), out=out.view(f))
    return out


def add_arr(a, b, out):
    """`add` の軸まとめ版。`out` に書き込んで返す。

    **同じスロットへ何本も足し込むのには使えない**（足す順が変わる）。
    軸が独立していることを呼ぶ側が保証すること。
    """
    dt = a.dtype
    assert b.dtype == dt, "add_arr: 型が違う"
    f = _flat(dt)
    if f is None:
        f = np.dtype((np.float64, dt.itemsize // 8))
    np.add(a.view(f), b.view(f), out=out.view(f))
    return out


_FLAT_ANY = {}


def flat_view(a):
    """構造体の配列を float64 の平べったい view にする（**縮約のため**）。

    軸をまとめられない縮約（同じスロットへ何本も足し込む）でも、
    **呼び出しの間接費は削れる。** `T[i] = add(T[i], X)` は1回ごとに
    view 3回・`np.empty`・`np.add`・構造体の書き戻しをやるが、

        dv = flat_view(T)[i]          # ループの外で1回
        np.add(dv, flat_view(X), out=dv)

    にすれば1回の ufunc で済む。**足す順は1ビットも変えない**（同じ
    スロットに同じ順で同じ加算をするだけ）。

    型の大きさを問わず平べったくする（`_flat()` と違い `None` を返さ
    ない）。縮約では view をループの外に出すので、小さい型でも
    元が取れる。戻り値は元を指す view で、書き込みは元に伝わる。
    最後の軸が欄（スロット）。0-d でも `numpy.void` でもよい。
    """
    dt = a.dtype
    f = _FLAT_ANY.get(dt)
    if f is None:
        f = _FLAT_ANY[dt] = np.dtype((np.float64, dt.itemsize // 8))
    return a.view(f)


def scalar_2_arr(s, x, nendo, out):
    """`scalar_2` の軸まとめ版（`hihokensha` だけ）。`out` に書き込む。

    `x` は放送できる形でよい。`siml` は「納付状況は年齢だけで決まるが
    係数は年齢×期間で違う」ので、`x` を `(51, 1)`、`s` を `(51, 51, 1)`
    にして渡す（`out` は `(51, 51)`）。

    `s * x * c / 12.` の順は `scalar_2` と同じに保つ。
    """
    assert x.dtype == HIHOKENSHA, "scalar_2_arr は hihokensha だけ"
    f = _flat(HIHOKENSHA)
    xv, ov = x.view(f), out.view(f)

    np.multiply(s, xv, out=ov)

    if nendo <= TOKUTEI_NENDO:
        i1, i2 = _M_COL[1], _M_COL[2]
    else:
        i1, i2 = _M_COL[2], _M_COL[1]

    if nendo == TOKUTEI_NENDO:
        ov[..., i1] = ov[..., i1] * (TOKUTEI_TUKI - 4) / 12.
        ov[..., i2] = ov[..., i2] * (16 - TOKUTEI_TUKI) / 12.
    else:
        ov[..., i2] = 0.

    ov[..., _M_COL[SUM]] = ov[..., i1] + ov[..., i2]
    return out


def average_by_ninzu_arr(x, out):
    """`average_by_ninzu` の軸まとめ版（`hihokensha` だけ）。

    `ninzu <= 0.` のスロットは全部 0（原本は `> 0.` を欄ごとに毎回見る
    ので、負の `ninzu` も 0 になる）。`ninzu` の欄そのものは素通し。

    `x` と `out` は同じ配列でもよい。そのために `ninzu` を先に控えて、
    0 を敷くのは割り算の**あと**にする（先に敷くと `x` が同じ配列の
    ときに割られる前の値を潰してしまう）。
    """
    assert x.dtype == HIHOKENSHA, "average_by_ninzu_arr は hihokensha だけ"
    f = _flat(HIHOKENSHA)
    xv, ov = x.view(f), out.view(f)
    n = xv[..., 0:1].copy()             # `ninzu` は全型でスロット0
    pos = n > 0.
    # `pos` が偽のところは `np.divide` が触らないので、そのあとに 0 を入れる
    np.divide(xv, n, out=ov, where=pos)
    ov[...] = np.where(pos, ov, 0.)
    ov[..., 0] = n[..., 0]              # `ninzu` の欄そのものは素通し
    return out


def average_by_ninzu(x):
    """str_op.c:105 の忠実移植（`hihokensha` だけ）。1人あたりに直す。

    `ninzu > 0.` を**欄ごとに毎回**見る（原本のとおり）。
    `ninzu` が 0 以下なら全部 0。`ninzu` の欄そのものは素通し。
    """
    assert x.dtype == HIHOKENSHA, "average_by_ninzu は hihokensha だけ"
    f = _flat(HIHOKENSHA)   # 21 slot なので必ず None ではない
    out = np.empty((), dtype=HIHOKENSHA)
    xv, ov = x.view(f), out.view(f)
    n = xv[0]                           # `ninzu` は全型でスロット0
    if n > 0.:
        np.divide(xv, n, out=ov)        # スロット0も割るが下で上書きする
    else:
        ov[:] = 0.
    ov[0] = n                           # `ninzu` の欄そのものは素通し
    return out
