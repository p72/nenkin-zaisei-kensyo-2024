# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/common/_variables.h と zero.cpp（グローバル変数一式）
==========================================================================
②は 222 本の多次元配列と 100 個あまりのスカラーをグローバルに持つ。
宣言は `common/_variables.h`、**寸法は `zero.cpp` にしか書いていない**。

```c
/* _variables.h */    EXTERN v5_t d3x, d3xs ;          /* 次元の数だけ */
/* zero.cpp     */    d3x = VEC(double, ENDY, 115, 6, 13, 58) ;   /* 寸法 */
```

`VEC(double, a1, a2, …)` は `ext/_vecarray.h` のマクロで、
`std::vector` を入れ子にして各次元を **`1 + a`** 個で作る
（添字 `0`〜`a` を使えるように）。`.AT(i, j, …)` は
`at(i).at(j)…` の連鎖なので、**NumPy の多次元配列にそのまま対応する**。

    VEC(double, ENDY, 115, 6, 13, 58)  →  shape (126, 116, 7, 14, 59)

いちばん大きい配列
------------------
    d3x  / d3xs   (126, 116, 7, 14, 59)   各 676MB
    kfprx         (126, 116, 7, 14,  9)       103MB
    gee 系 18本   (126,   4, 116, 101)    各  47MB（計 851MB）

全 222 本で **2,566MB**。原本は `std::vector` の入れ子なので、
1本の `double` あたり
「内側 vector のヘッダ 24B ＋ malloc の管理領域」が上乗せされる。
`d3x` は最内側の vector が 126×116×7×14 = 143万本あるので、
データ 676MB に対して 1GB 近くを使う。**移植版の方が軽い。**

`zero_init` と `zero_sepsd`
---------------------------
`main.cpp` が最初に1回 `zero_init()` を呼び、制度（`pseid` = 0, 1, 4, 5）
ごとに `zero_sepsd()` を呼ぶ。どちらも `VEC(...)` で**作り直す**ので、
中身は 0 に戻る。移植版は同じ場所で 0 埋めする（配列を作り直さない）。

`kfprx` だけ両方に出てくる（`zero.cpp:24` と `:280`）。制度をまたいで
残す意図だったとしても `zero_sepsd` が消すので、実際には毎回 0 に戻る。

宣言だけで1回も使われない配列が9本
----------------------------------
`kakor` `kakorsn` `kakorsnn` `kakorn` `vmini` `gnn2` `gnntal`
`d3xdmy` `kfprxdmy` は `_variables.h` に宣言があるだけで、
`zero.cpp` に寸法が無く、34本の .cpp のどこからも触られない
（`grep` で確認）。寸法が分からないので移植版でも作らない。
（`検証/原本の不具合.md`）

年度の添字
----------
`k`（西暦 − 2000）が基本。1900年代は負になるので、経済前提など
1946年度から持つ配列は `C19(k) = k + 100` で下駄をはかせる
（`setconst.py` の解説）。
"""
import numpy as np

from setconst import C19, ECEDY, ENDY

__all__ = ["Glva", "G"]

# ---------------------------------------------------------------------------
# **0 で割っても落ちないようにする。**①④⑥と同じ理由。
# 配列の値は `np.float64` のまま扱い、`float()` に落とさない。
# ---------------------------------------------------------------------------
np.seterr(divide="ignore", invalid="ignore", over="ignore", under="ignore")

# --------------------------------------------------------------------------
# main.cpp が最初に1回だけ呼ぶ zero_init() の配列（zero.cpp:4-35）
# --------------------------------------------------------------------------
_INIT_ARRAYS = {
    "partbbn": (1, 1, 10, 2),
    "partbbn2": (1, 1, 10, 2),
    "kflcan": (ENDY, C19(ENDY)),
    "tz": (4,),
    "kfprx": (ENDY, 115, 6, 13, 8),
    "apdmy": (ENDY, 11),
    "ap65dmy": (ENDY, 6),
    "ap70dmy": (ENDY, 6),
    "ap75dmy": (ENDY, 6),
    "ap85dmy": (ENDY, 6),
    "atdmy": (ENDY, 17),
    "admy": (ENDY, 11),
    "aikudmy": (ENDY, 6),
    "aaldmy": (ENDY, 6),
}

# --------------------------------------------------------------------------
# 制度ごとに呼ぶ zero_sepsd() の配列（zero.cpp:38-282）
# --------------------------------------------------------------------------
_SEPSD_ARRAYS = {
    "chwd": (115, 100, 3),
    "pop": (ENDY, 2, 115),
    "l": (ENDY, 3, 115),
    "lpt": (ENDY, 3, 115),
    "lpt1": (ENDY, 3, 115),
    "lpt2": (ENDY, 3, 115),
    "lpt2i": (ENDY, 3, 115),
    "lpt2p": (ENDY, 3, 115),
    "lpt3": (ENDY, 3, 115),
    "lpt4": (ENDY, 3, 115),
    "ri": (ECEDY,),
    "h": (ECEDY,),
    "ci0": (ECEDY,),
    "dir": (ECEDY,),
    "jz_shk": (ECEDY,),
    "hh": (ECEDY,),
    "ci": (ECEDY,),
    "hdum": (ECEDY,),
    "ci2": (ECEDY, 115),
    "hp2": (ECEDY, 115),
    "ad": (ENDY,),
    "ad2": (ENDY,),
    "bd": (ENDY, 23),
    "pre": (C19(-54),),
    "pres": (C19(-54),),
    "flt": (C19(ENDY),),
    "adt": (3,),
    "sadt": (C19(ENDY),),
    "cadt": (C19(ENDY),),
    "wife": (C19(ENDY),),
    "can": (C19(ENDY),),
    "can2": (C19(ENDY),),
    "ha": (3,),
    "hb": (3,),
    "ema": (3,),
    "emb": (3,),
    "emc": (3,),
    "ee": (2,),
    "rs": (3, ENDY, 115, 4),
    "sik": (ENDY, 115, 2, 19, 2),
    "sikr": (69, 2, 17, 2),
    "routsu": (2, 4, 3),
    "nos": (ENDY, 69, 2, 17, 2),
    "qp": (100, 130, 2),
    "riss": (ENDY, 70, 65, 3, 1),
    "nos2": (ENDY, 69, 2, 4, 2),
    "rigd": (3, 70, 70, 1),
    "rigk": (3, 70, 70, 1),
    "rigbe": (3, 70, 70, 1),
    "rkrsg": (70, 3, 2),
    "rig2": (70, 3, 4),
    "jiiku": (ENDY, 115),
    "ikucoe": (ENDY, 115),
    "q2": (ENDY, 115),
    "ns": (ENDY, 115),
    "rt": (ENDY, 115),
    "cl": (ENDY, 3),
    "cl2": (ENDY, 3),
    "u": (ENDY, 115, 3),
    "rc": (3, ENDY, 115),
    "q": (ENDY, 115, 3),
    "yx": (ENDY, 115, 1),
    "br": (ENDY, 115, 3),
    "bn": (ENDY, 115, 3),
    "bnpt": (ENDY, 115, 2),
    "dmpt2": (ENDY, 115, 2),
    "kd": (ENDY, 6, 4, 115),
    "g": (115, 100),
    "ge": (115, 100),
    "gpt": (115, 100),
    "bb": (115, 100),
    "bbpt": (115, 100),
    "gd": (65, 100),
    "r": (115, 15, 13),
    "pshn": (115, 15, 13),
    "hn": (115, 15, 13, 4),
    "z": (115, 100, 1, 9),
    "ze": (115, 100, 1, 9),
    "psz": (115, 100, 1, 7),
    "psze": (115, 100, 1, 7),
    "f": (115, 15, 13, 23),
    "f_hik": (115, 15, 13, 23),
    "f_min": (115, 15, 13, 23),
    "w": (115, 100, 0, 7, 3),
    "we": (115, 100, 0, 7, 3),
    "rsen": (70,),
    "hnsen": (70, 2),
    "pshnsen": (70,),
    "fsen": (70, 23),
    "fsenhik": (70, 23),
    "fsenmin": (70, 23),
    "fkouzai2": (84, 15, 2),
    "t4k": (115, 15, 13),
    "hn2k": (115, 15, 13, 2),
    "t6k": (115, 15, 13, 23),
    "t4": (115, 15, 13),
    "hn2": (115, 15, 13, 2),
    "t6": (115, 15, 13, 23),
    "rhantei": (115, 15, 4),
    "rhantei0": (115, 15, 4),
    "fhantei": (115, 15, 4, 23),
    "gee": (ENDY, 3, 115, 100),
    "geept": (ENDY, 3, 115, 100),
    "g2": (ENDY, 3, 115, 100),
    "ge2": (ENDY, 3, 115, 100),
    "gz2": (ENDY, 3, 115, 100),
    "gn2": (ENDY, 3, 115, 100),
    "gez2": (ENDY, 3, 115, 100),
    "bb2": (ENDY, 3, 115, 100),
    "z2": (ENDY, 3, 115, 100),
    "ze2": (ENDY, 3, 115, 100),
    "w2": (ENDY, 3, 115, 100),
    "we2": (ENDY, 3, 115, 100),
    "g3": (ENDY, 3, 115, 100),
    "gnp3": (ENDY, 3, 115, 100),
    "gpt3": (ENDY, 3, 115, 100),
    "bb3": (ENDY, 3, 115, 100),
    "bbnp3": (ENDY, 3, 115, 100),
    "bbpt3": (ENDY, 3, 115, 100),
    "kfpr": (ENDY, 6, 13, 8),
    "at": (ENDY, 3),
    "ap": (ENDY, 3),
    "ap65": (ENDY, 3),
    "ap70": (ENDY, 3),
    "ap75": (ENDY, 3),
    "ap85": (ENDY, 3),
    "appart": (ENDY, 3),
    "appart65": (ENDY, 3),
    "appart70": (ENDY, 3),
    "appart75": (ENDY, 3),
    "appart85": (ENDY, 3),
    "a": (ENDY, 3),
    "aiku": (ENDY, 3),
    "aal": (ENDY, 3),
    "a60": (ENDY, 3),
    "a65": (ENDY, 3),
    "a70": (ENDY, 3),
    "a75": (ENDY, 3),
    "a85": (ENDY, 3),
    "apdum": (ENDY, 3),
    "ap65dum": (ENDY, 3),
    "ap70dum": (ENDY, 3),
    "ap75dum": (ENDY, 3),
    "ap85dum": (ENDY, 3),
    "appartdum": (ENDY, 3),
    "appart65dum": (ENDY, 3),
    "appart70dum": (ENDY, 3),
    "appart75dum": (ENDY, 3),
    "appart85dum": (ENDY, 3),
    "adum": (ENDY, 3),
    "aikudum": (ENDY, 3),
    "a60dum": (ENDY, 3),
    "a65dum": (ENDY, 3),
    "a70dum": (ENDY, 3),
    "a75dum": (ENDY, 3),
    "a85dum": (ENDY, 3),
    "ax": (ENDY, 75, 3),
    "gx": (ENDY, 75, 3),
    "gtal": (ENDY, 75, 3),
    "gztal": (ENDY, 75, 3),
    "gntal": (ENDY, 75, 3),
    "getal": (ENDY, 75, 3),
    "apart": (ENDY, 3),
    "aikupart": (ENDY, 3),
    "a60part": (ENDY, 3),
    "a65part": (ENDY, 3),
    "a70part": (ENDY, 3),
    "a75part": (ENDY, 3),
    "a85part": (ENDY, 3),
    "fpart": (70, 15, 2),
    "fpart2": (70, 15, 2),
    "fpart3": (70, 15, 2),
    "j": (30, 3, 4, 15),
    "j2": (30, 3, 70, 15, 4),
    "j3": (30, 3, 70, 15, 4),
    "parrater": (2,),
    "parratet": (2,),
    "d3": (ENDY, 6, 13, 58, 2),
    "d3x": (ENDY, 115, 6, 13, 58),
    "d3xs": (ENDY, 115, 6, 13, 58),
    "okisor": (ENDY, 2, 13, 4),
    "okiso2x": (ENDY, 115, 2, 3, 6),
    "dk3x": (ENDY, 115, 2, 6, 10),
    "y": (115, 100, 3),
    "ypt": (115, 100, 3),
    "rn": (115, 100, 13),
    "pshnn": (115, 15, 13),
    "bbnp": (115, 100),
    "gzpt": (115, 100),
    "gnpt": (115, 100),
    "fsenn": (70, 23),
    "fsennhik": (70, 23),
    "fsennmin": (70, 23),
    "hnsenn": (70, 2),
    "gnnpt": (115,),
    "rsenn": (70,),
    "pshnsenn": (70,),
    "fn": (115, 15, 13, 23),
    "fnhik": (115, 15, 13, 23),
    "fnmin": (115, 15, 13, 23),
    "hnn": (115, 15, 13, 2),
    "gn": (115, 100),
    "gnn": (115,),
    "gz": (115, 100),
    "gez": (115, 100),
    "ye": (115, 100),
    "seiz": (115, 100, 20),
    "kuri": (ENDY, 2, 10, 70, 15),
    "kfprx": (ENDY, 115, 6, 13, 8),
}

_ARRAYS = dict(_INIT_ARRAYS)
_ARRAYS.update(_SEPSD_ARRAYS)


def _shape(spec):
    """`VEC(double, a1, a2, …)` の寸法。**各次元は `1 + a`。**

    上の表は `zero.cpp` の引数をそのまま写してあるので、ここで 1 を足す。
    `VEC(double, ENDY, 115, 6, 13, 58)` → `(126, 116, 7, 14, 59)`。
    """
    return tuple(d + 1 for d in spec)

# cntl() が決める設定（_variables.h:15-45）。すべて int
_SETTINGS_INT = (
    "key", "iname", "iecon", "iwname", "konen", "seidn", "seidver",
    "kver", "oldflg",
    "psly", "pslsi", "pslsi2", "seitaikey", "kzn", "kzny",
    "seimei", "seiy", "kaite", "zairo", "chinsura",
    "nenbeex", "nenbe65", "xb", "xa", "daik14",
    "cht_flg", "furikae_flg", "kkuci",
    "zaiteiyr", "koza70", "kozaiex2", "kozaexyr",
    "hiho70yr", "flg_hiho70", "flg_hiho",
    "izokyuyr", "jiiku2yr", "flg_kaisho", "flg_sankyu", "sankyuyr",
    "flg_fusiizo", "fusiizoyr", "flg_part", "partyr1", "partyr2",
    "partyr3", "partyr4",
    "pahosei1", "houjou", "houjouyr", "flg_hsr", "hsr_endy", "canyr",
    "flg_sigo", "atamauchi", "flg_kozax", "kozaxyr", "kozax",
    "flg_kozabase", "kozabaseyr",
    "flg_teizabase", "teizabaseyr", "flg_zaikai", "zaikaiyr",
    "flg_krgnr", "krgnyr", "flg_jshahosei",
    "flg_saikanyu", "flg_gtest", "flg_bzwtest", "flg_tuuroutest",
    "flg_siktuika", "flg_changekiso", "flg_toukei", "flg_hantei",
    "flg_izoku", "flg_shougai", "flg_115", "flg_kyuuzai",
    "flg_zantei1", "flg_zantei2", "flg_kurisage", "flg_tests",
    "flg_okure", "flg_taiki75", "flg_inout",
    "xend", "tend",
    # ループ変数（_variables.h:60, 55-56）
    "pseid", "k", "s", "s2", "xr", "xxr", "xrb", "it",
)

# double のスカラー（_variables.h:47-48, 56-58, 94-99, 183-185）
_SETTINGS_DBL = (
    "hikrate", "houjour1", "houjour2", "vvm", "hsr_r", "saikanyu",
    "tn", "ta", "pro", "pros", "pslr",
    "pra", "prb", "pras", "prbs", "fl1", "fl", "minb", "cad", "wif",
    "senll", "srv",
    "hh2_1999", "hh2_2000", "hh2_2001",
)


class Glva:
    """②のグローバル変数一式。

    配列は初回アクセス時に確保する（`__getattr__`）。C++ の
    `std::vector` の入れ子と同じくゼロ初期化で、寸法は上の表そのまま。
    """

    def __init__(self):
        for n in _SETTINGS_INT:
            object.__setattr__(self, n, 0)
        for n in _SETTINGS_DBL:
            object.__setattr__(self, n, 0.0)
        # map<string, FILE*> fp_map / map<string, string> readpath_map
        object.__setattr__(self, "fp_map", {})
        object.__setattr__(self, "readpath_map", {})
        object.__setattr__(self, "pstat_written", False)
        # string cseid[8]（fileio.cpp:33-36 が入れる）
        object.__setattr__(self, "cseid", [""] * 8)

    def __getattr__(self, name):
        spec = _ARRAYS.get(name)
        if spec is not None:
            a = np.zeros(_shape(spec), dtype=np.float64)
            object.__setattr__(self, name, a)
            return a
        raise AttributeError(
            f"②のヘッダに {name} という配列はない（移植漏れ、"
            "または zero.cpp に寸法が無い9本のどれか）")

    # ---- 確保済みの配列を調べる（デバッグ用） ----
    def allocated(self):
        out = {}
        for n in _ARRAYS:
            v = self.__dict__.get(n)
            if v is not None:
                out[n] = v.nbytes
        return out

    def allocated_mb(self):
        return sum(self.allocated().values()) / 1e6


# 原本のグローバルは1組しかないので、モジュール単位で1個持つ。
G = Glva()


def _zero(names):
    """`VEC(...)` で作り直すのと同じ（中身を 0 に戻す）。"""
    for n in names:
        v = G.__dict__.get(n)
        if v is None:
            getattr(G, n)          # 未確保なら確保（ゼロ初期化）
        else:
            v[...] = 0.0


def zero_init():
    """zero.cpp:4 の `zero_init()`。main が最初に1回だけ呼ぶ。"""
    _zero(_INIT_ARRAYS)
    G.pstat_written = False
    G.xr = 0
    G.xxr = 0
    G.xrb = 0
    G.it = 0
    G.tn = 0.0
    G.ta = 0.0
    G.pro = 0.0
    G.pros = 0.0
    G.pslr = 0.0


def zero_sepsd():
    """zero.cpp:38 の `zero_sepsd()`。制度ごとに呼ぶ。

    原本はスカラーも一緒に 0 に戻す（`pra = prb = pras = prbs = 0.0` など）。
    """
    _zero(_SEPSD_ARRAYS)
    G.pra = G.prb = G.pras = G.prbs = 0.0
    G.fl1 = G.fl = G.minb = 0.0
    G.cad = G.wif = 0.0
    G.senll = 0.0
    G.srv = 0.0
