# -*- coding: utf-8 -*-
"""
被保険者推計/mcntl.h と mfile_open.h の忠実移植
================================================
原本はグローバル変数の塊。`mcntl.h` が定義、`cntl.h` が `extern` 宣言で、
中身は1行ずつ同じ（`diff cntl.h mcntl.h` が `extern` の有無だけ）。
`mfile_open.h` と `file_open.h` も同じ関係。⑤の `glvam.h` / `glva.h` と
同じ作りになっている。

移植では1個の `G` オブジェクトに全部ぶら下げる。名前は原本と1文字も
変えていない。大きな配列は⑤と同じく NumPy の `float64`（C の double
配列と同じメモリ配置）で、初回アクセス時に確保する。

いちばん大きい2つ
-----------------
    partnin[131][5][121][8][4][4]   10,144,640 要素   81MB
    p_wari [131][5][121][8][4][4]   10,144,640 要素   81MB

この2つで 162MB。原本は静的領域に置いている。Python のネストした list に
すると1要素あたり40Bで 800MB になるので、NumPy でないと厳しい。

添字の意味（読み解いた範囲）
----------------------------
    年度   `nendo - STARTY`（0〜130。STARTY = 2020）
    性別   0〜4。**0 が男女計**、1 が男、2 が女
           3, 4 は有配偶・無配偶の区分（`readdata.c:72-75` が
           `jinko_wari[3]`/`[4]` に女の値を入れている）
    年齢   0〜120
    seido  厚年・共済の制度区分。`kounen[0]` が合計、`[1]` が厚年＋
           国共済、`[2]`〜`[6]` が個別（`readdata.c:476-486` の
           足し合わせから読める）
    pkubun パートの区分 0〜7。1, 2, 7 だけに値が入る
           （`readdata.c:352-369`）
    tkubun 時間の区分 0〜3。1, 2, 3 に値が入る
    ykubun 適用拡大の段階 0〜3。1 が現行、2 が1段階、3 が2段階
           （`readdata.c:352/383/415` が順に `[1]`/`[2]`/`[3]` に入れる）

原本の癖をそのまま残しているところ
----------------------------------
1. **`zero()` が全部を 0 にするが、C では最初から 0 になっている**
   （`zero.c`）。静的領域は規格でゼロ初期化されるので、`zero()` は
   何も変えない。しかも 131×5×121 の三重ループの中で
   `sojinko_c[年度][性]`（年齢に依らない）や `xend[年度]`、
   `kbetu_partkiso[性][…]`（年度に依らない）まで代入しているので、
   同じ場所に何万回も 0 を書いている。
   移植版は `G` を作った時点でゼロなので `zero()` は**何もしない**
   関数として置いてある（原本との対応を残すため）。
   （`検証/原本の不具合.md`）

2. **`TEMP` が読み込みの作業領域として使い回される**
   （`readdata.c:104-233`）。`roud_r` / `syugyo_r` / `koyou_r` /
   `seiki_hiseiki_r[1..3]` を読むたびに 0 で埋めて `read_roud` に渡し、
   そのあと本体へ写す。`cntl.h` では他の配列と同じ並びで宣言されている。
"""
import numpy as np

from setconst import CNENDO, ENDY, NAGE, NSEI, NY

__all__ = ["Glva", "G"]

# ---------------------------------------------------------------------------
# **0 で割っても落ちないようにする。**
#
# ①には分母のゼロを確かめていない割り算がいくつもあり、実データでも
# 配列の端（`ENDY` の年度など）で 0/0 が起きる。C は IEEE 754 どおり
# nan / ±inf を返して進むので、移植版も同じでなければならない。
#
# そこで**配列の値は `np.float64` のまま扱う**（`float()` に落とさない）。
# `np.float64` の四則演算は IEEE 754 倍精度そのもので Python の float と
# 同じ結果になるが、0 除算だけは C と同じく nan / ±inf を返す
# （Python の float は `ZeroDivisionError` を投げる）。
# 警告は出さない設定にする。
#
# nan が出るのは出力しない年度（`KF` = 2125 より後）なので、
# `waku*.csv` に nan が現れることはない。
# ---------------------------------------------------------------------------
np.seterr(divide="ignore", invalid="ignore", over="ignore", under="ignore")

# --------------------------------------------------------------------------
# 配列の寸法表。原本 mcntl.h の宣言をそのまま並べたもの。
# --------------------------------------------------------------------------
_ARRAYS = {
    # double jinko_c[ENDY-STARTY+1][5][121];
    "jinko_c": (NY, NSEI, NAGE),
    "jinko_m": (NY, NSEI, NAGE),
    # double sojinko_c[ENDY-STARTY+1][5];
    "sojinko_c": (NY, NSEI),
    # double jinko_wari[5][121];
    "jinko_wari": (NSEI, NAGE),
    # double yuhaig_r[ENDY-STARTY+1][121];
    "yuhaig_r": (NY, NAGE),

    "roud_r": (NY, NSEI, NAGE),
    "roud_j_c": (NY, NSEI, NAGE),
    "roud_j_m": (NY, NSEI, NAGE),
    "syugyo_r": (NY, NSEI, NAGE),
    "syugyo_j_c": (NY, NSEI, NAGE),
    "syugyo_j_m": (NY, NSEI, NAGE),

    # double koyou_j_c[11][ENDY-STARTY+1][5][121];
    "koyou_j_c": (11, NY, NSEI, NAGE),
    "koyou_j_m": (11, NY, NSEI, NAGE),
    "koyou_r": (NY, NSEI, NAGE),
    # double seiki_hiseiki_r[4][ENDY-STARTY+1][5][121];
    "seiki_hiseiki_r": (4, NY, NSEI, NAGE),
    # double hiseiki_jikan_r[5][ENDY-STARTY+1];
    "hiseiki_jikan_r": (NSEI, NY),
    # double hiseiki_tan_r_all[ENDY-STARTY+1];
    "hiseiki_tan_r_all": (NY,),

    "jieigyo_j_c": (NY, NSEI, NAGE),
    "jieigyo_j_m": (NY, NSEI, NAGE),
    # double soroudh_c[10][ENDY-STARTY+1][5][121];
    "soroudh_c": (10, NY, NSEI, NAGE),
    "soroudh_m": (10, NY, NSEI, NAGE),
    # double heikinh_c[11][ENDY-STARTY+1];
    "heikinh_c": (11, NY),
    "heikinh_m": (11, NY),
    # double kounenteki_c[10][ENDY-STARTY+1];
    "kounenteki_c": (10, NY),
    "kounenteki_m": (10, NY),

    # double nigou[ENDY-STARTY+1][5][121];
    "nigou": (NY, NSEI, NAGE),
    # double kounen[7][ENDY-STARTY+1][5][121];
    "kounen": (7, NY, NSEI, NAGE),
    "sangou": (7, NY, NSEI, NAGE),
    # double ichigou[3][ENDY-STARTY+1][5][121];
    "ichigou": (3, NY, NSEI, NAGE),
    "mika_soto": (NY, NSEI, NAGE),
    # double ichiyuhaigr[121];
    "ichiyuhaigr": (NAGE,),

    # double partnin[ENDY-STARTY+1][5][121][8][4][4];   81MB
    "partnin": (NY, NSEI, NAGE, 8, 4, 4),
    # double kbetu_partnin[ENDY-STARTY+1][5][17][8][4][4];
    "kbetu_partnin": (NY, NSEI, 17, 8, 4, 4),
    # double kbetu_partkiso[5][17][8][4][4];
    "kbetu_partkiso": (NSEI, 17, 8, 4, 4),
    # double p_wari[ENDY-STARTY+1][5][121][8][4][4];    81MB
    "p_wari": (NY, NSEI, NAGE, 8, 4, 4),
    # double cutritu[ENDY-CNENDO+1];
    "cutritu": (ENDY - CNENDO + 1,),
    # double TEMP[ENDY-STARTY+1][5][121];  読み込みの作業領域（癖 2.）
    "TEMP": (NY, NSEI, NAGE),
}

# int xend[ENDY-STARTY+1];  こちらだけ int
_INT_ARRAYS = {
    "xend": (NY,),
}

# ループ変数として使われるグローバル（mcntl.h:1-5）。
# 原本は関数をまたいで使い回している
_LOOPVARS = ("nendo", "nenrei", "sei", "seido", "kubun")

# cntl() が標準入力から決める設定（mcntl.h:7-17）
_SETTINGS = ("BANGO", "JIN", "QX", "NC", "SJINKOY", "FJINKOY", "YUHAIGY",
             "ROUDR", "ROUDYR", "MODE", "MODE45",
             "PART", "PARTYR1", "PARTYR2", "PARTKYR")

# mfile_open.h の FILE * と作業領域
_FILES = ("fp_jinko", "fp_jinkow", "fp_jinkoy", "fp_roudritu", "fp_map",
          "fp_ichiyu", "fp_jogen", "fp_setakyo", "fp_wakuout", "fp_cutout",
          "fp_err", "fp_part", "fp_cut")


class Glva:
    """原本のグローバル変数一式。

    大きな配列は初回アクセス時に確保する（`__getattr__`）。C の静的領域と
    同じくゼロ初期化で、寸法は `_ARRAYS` の表そのまま。
    """

    def __init__(self):
        for n in _LOOPVARS:
            object.__setattr__(self, n, 0)
        for n in _SETTINGS:
            object.__setattr__(self, n, 0)
        for n in _FILES:
            object.__setattr__(self, n, None)
        # char filename[250] / double buffer[DATA_MAX] / int data_number /
        # double previous_buffer0（mfile_open.h:33-36）
        object.__setattr__(self, "filename", "")
        object.__setattr__(self, "data_number", 0)
        object.__setattr__(self, "previous_buffer0", 0.0)

    def __getattr__(self, name):
        shape = _ARRAYS.get(name)
        if shape is not None:
            a = np.zeros(shape, dtype=np.float64)
            object.__setattr__(self, name, a)
            return a
        shape = _INT_ARRAYS.get(name)
        if shape is not None:
            a = np.zeros(shape, dtype=np.int32)
            object.__setattr__(self, name, a)
            return a
        raise AttributeError(
            f"mcntl.h に {name} という変数はない（移植漏れの可能性）")

    # ---- 確保済みの配列を調べる（デバッグ用） ----
    def allocated(self):
        out = {}
        for n in list(_ARRAYS) + list(_INT_ARRAYS):
            v = self.__dict__.get(n)
            if v is not None:
                out[n] = v.nbytes
        return out

    def allocated_mb(self):
        return sum(self.allocated().values()) / 1e6


# 原本のグローバルは1組しかないので、モジュール単位で1個持つ。
G = Glva()


def zero():
    """zero.c の忠実移植。**何もしない。**

    原本は全配列を 0 で埋めるが、C の静的領域は規格でゼロ初期化される
    ので、`zero()` を呼んでも呼ばなくても結果は同じ（上の癖 1.）。
    移植版は `G` を作った時点でゼロなので、対応を残すためだけに置く。
    """
    return
