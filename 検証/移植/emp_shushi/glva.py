# -*- coding: utf-8 -*-
"""
プログラム/厚生年金/収支計算/glvam.h の忠実移植
================================================
原本はグローバル変数の塊（glvam.h が定義、glva.h が extern 宣言。makefile の
`header_maker2 glvam.h glva.h` で後者を生成している）。移植では 1 個の
`G` オブジェクトに全部ぶら下げる。名前は原本と1文字も変えていない。

なぜ NumPy を使うのか
---------------------
原本の配列は BSS に置かれた素の double 配列で、合計 628MB ある。

    D3bxtp[5][4][14][8][117][116]   30,401,280 要素   243MB
    Kfpbxtp[5][4][14][8][117][116]  30,401,280 要素   243MB
    Kofbxtp / Kofte / Kofkk          3,800,160 要素    30MB ×3
    ...

これを Python のネストした list で持つと、1 要素あたり参照8B＋float
オブジェクト32B で **3.1GB** になって現実的でない。NumPy の float64 配列は
C の double 配列と**同じメモリ配置**（8B/要素、ゼロ初期化）なので、
628MB のまま収まる。

ビット一致は崩れない。ここで NumPy は「C と同じメモリ配置」としてだけ
使い、**演算はスカラーのまま**にしている。要素の読み書きは IEEE 754 倍精度の
厳密な転送で、丸めが入る余地が無い。総和などのベクトル化は演算順序を
変えてしまうので入れない（速くするのは全部通してから）。

`np.float64` の四則演算も IEEE 754 倍精度そのものなので Python の float と
同じ結果になる。むしろゼロ除算が C と同じく inf/nan になる（Python の
float は ZeroDivisionError を投げる）ぶん、原本の挙動に近い。

割り当ては遅延（初回アクセス時）。使わない配列の 243MB を確保しないため。
"""
import numpy as np

from setconst import ECEDY, ECSTY, ECXA, ENDY, STTY, NE, NX, NXE, NY

# --------------------------------------------------------------------------
# 配列の寸法表。原本 glvam.h の宣言をそのまま並べたもの。
# コメントは原本の宣言そのまま。
# --------------------------------------------------------------------------
_ARRAYS = {
    # double Prema[6][ENDY-STTY+1];
    "Prema": (6, NY),
    "Premb": (6, NY),

    # double Ci[ECEDY-ECSTY+1], H[ECEDY-ECSTY+1];
    "Ci": (NE,),
    "H": (NE,),
    "Ri": (NE,),
    "Ri2": (NE,),
    "HCdum": (NE,),
    "Id_Hhd": (NE,),

    # double Kra[ECEDY-ECSTY+1][116-ECXA], Krb[...];
    "Kra": (NE, NXE),
    "Krb": (NE, NXE),

    "Id_Cid": (NE,),
    "Id_Cid_2": (NE,),

    # double Ap[5][4][ENDY-STTY+1];
    "Ap": (5, 4, NY),
    "Apdum": (5, 4, NY),
    "Ap65": (5, 4, NY),
    "Ap70": (5, 4, NY),
    "Ap75": (5, 4, NY),

    "A": (5, 4, NY),
    "Adum": (5, 4, NY),
    "A60": (5, 4, NY),
    "A65": (5, 4, NY),
    "A70": (5, 4, NY),

    "Aiku": (5, 4, NY),
    "Aikudum": (5, 4, NY),
    "Aal": (5, 4, NY),

    # double Apart[4][ENDY-STTY+1];
    "Apart": (4, NY),
    "Aikupart": (4, NY),
    "A60part": (4, NY),
    "A65part": (4, NY),
    "A70part": (4, NY),

    "An": (5, 4, NY),
    "Aniku": (5, 4, NY),
    "Anpart": (4, NY),
    "Anikupart": (4, NY),

    # double Keikagen[ENDY-STTY+1][116];
    "Keikagen": (NY, NX),

    # ここから下が大物。合計 600MB 超。
    "T4xtp": (5, 4, 7, NY, NX),                 #  15MB
    "D3bxtp": (5, 4, 14, 8, NY, NX),            # 243MB
    "Kfpbxtp": (5, 4, 14, 8, NY, NX),           # 243MB
    "Kofbxtp": (5, 4, 14, NY, NX),              #  30MB
    "Kofte": (5, 4, 14, NY, NX),                #  30MB
    "Kofkk": (5, 4, 14, NY, NX),                #  30MB
    "Daikbxtp": (5, 4, 9, NY, NX),              #  20MB
    "Kyosdx": (2, 9, 2, NY, NX),                #   4MB
    "Kfkyosdx": (2, 9, 2, NY, NX),              #   4MB

    # double Sien[2][5][ENDY-STTY+1];
    "Sien": (2, 5, NY),
    "Nofu": (5, NY),
    "Jyutaku": (NY,),

    "Kokusyushi": (10, NY),

    "Scutrk1": (NE,),
    "Scutrk2": (NE,),
    "Scutrrh": (NE, NXE),
    "Scutrrt": (NE, NXE),
    "Scutrrki": (NE, NXE),

    # double Cc[5][31][ENDY-STTY+1];
    "Cc": (5, 31, NY),
    "Dc": (5, 31),

    "Ukyu": (2, 5, 4, NY),

    "Siwake": (5,),
    "Jisout": (5,),
    "Tumazumi": (5, NY),

    # double E3dxb[5][14][ENDY-STTY+1][116];
    "E3dxb": (5, 14, NY, NX),                   #   8MB

    "Escutrrh": (NE, NXE),
    "Escutrrt": (NE, NXE),

    "Tokutyo": (NE, NXE),

    # double W[ENDY-STTY+1][5], Kw[ENDY-STTY+1][5];
    "W": (NY, 5),
    "Kw": (NY, 5),
    "Mkiso": (NY,),
    "Mhirei": (NY, 5),

    "Np": (24, NY),
}

# int のスカラー（原本 glvam.h の宣言順）。C のグローバルはゼロ初期化。
_INTS = (
    "Cntlset", "Seidn", "Pseid", "Useid", "Kijun", "Saimu", "Fpset",
    "Kyoskijun", "Ks", "Ke",
    "Kozai", "Flg_Kaisho", "Flg_Jimu", "Flg_Dmakuro", "Dmakuro_Yr",
    "Flg_Kmakuro", "Kmakuro_Yr", "Kmakuro_Yr2", "Kkuci", "Sienset",
    "Nenbeex", "Nenbeex2",
    "Flg_Rima", "Rima_Yr_Str", "Rima_Yr_End",
    "Flg_Part", "Part_Yr1", "Part_Yr2", "Part_Yr3",
    "Flg_Sigo",
    "Flg_Houjou", "Houjou_Yr",
    "Psly", "Pslsi", "Pslsi2", "Kzn", "Kzny", "Seitaikey", "Gaisan",
    "zaichou", "hiho74", "Touitu", "Touitu_mode",
    "zan_jimu", "zan_nof", "zan_ave", "zan_fund", "zan_model",
    "Flg_hanei", "zan_tobashi",
    "kakusa", "Flg_shunor", "Flg_nendo", "Flg_matsu",
)

# double のスカラー
_DBLS = (
    "Shunor", "Ca", "nendohosei",
    "Kmakuro_Min", "Drima",
    "Cbm_Pt1", "Cbm_Pt2",
    "Houjou_R1", "Houjou_R2",
    "Misyu", "Tumawake",
)

# char 配列（C 文字列）。移植では str。原本の寸法はコメントに残す。
_STRS = (
    "Nfile",        # char Nfile[5]
    "Nfile2",       # char Nfile2[5]
    "Nfile3",       # char Nfile3[5]
    "Nkfile",       # char Nkfile[5]
    "Ecfile",       # char Ecfile[5]
    "Wcfile",       # char Wcfile[5]
    "Wcfile2",      # char Wcfile2[5]
    "Sifile",       # char Sifile[4]
    "Cutrfile1",    # char Cutrfile1[2]
    "Cutrfile2",    # char Cutrfile2[2]
    "Cutrfile3",    # char Cutrfile3[3]
    "Cutrfile4",    # char Cutrfile4[4]
    "Cutrfile5",    # char Cutrfile5[4]
    "Tumafile",     # char Tumafile[3]
    "Saimushu",     # char Saimushu[3]
    "Saimuski",     # char Saimuski[3]
    "Siencha",      # char Siencha[13]
)

# FILE* （原本 glvam.h:163-196）。配列のものは list で持つ。
_FILES = (
    "ifp_econ", "ifp_kyos", "ifp27_tuma", "ifp_sien", "ifp_nofu",
    "ifp_kaiteb", "ifp_kaitea", "ifp_kokukaite",
    "ifp_wakum", "ifp_bas_cuta", "ifp_asys_cuta", "ifp_asys_cutb",
    "ofp03_summary",
    "ofp_cuta", "ofp_cutb", "ofp_cuta2", "ofp_cutb2",
    "ofp_siwake", "ofp_Tokutyo",
    "ofp_NPBPkekka", "ofp_EPsummary",
    "ofp_test", "ifp_Touitu",
)
_FILE_ARRAYS = {
    "ifp10_usys": 5,     # FILE *ifp10_usys[5]
    "ofp01_shushi": 5,   # FILE *ofp01_shushi[5]
    "ofp90_nenbe": 5,    # FILE *ofp90_nenbe[5]
}


class Glva:
    """原本のグローバル変数一式。

    大きな配列は初回アクセス時に確保する（`__getattr__`）。C の BSS と同じく
    ゼロ初期化で、寸法は `_ARRAYS` の表そのまま。
    """

    def __init__(self):
        for n in _INTS:
            object.__setattr__(self, n, 0)
        for n in _DBLS:
            object.__setattr__(self, n, 0.0)
        for n in _STRS:
            object.__setattr__(self, n, "")
        for n in _FILES:
            object.__setattr__(self, n, None)
        for n, size in _FILE_ARRAYS.items():
            object.__setattr__(self, n, [None] * size)

    def __getattr__(self, name):
        # __init__ で設定済みのものはここに来ない。配列だけが来る。
        shape = _ARRAYS.get(name)
        if shape is None:
            raise AttributeError(
                f"glvam.h に {name} という変数はない（移植漏れの可能性）")
        a = np.zeros(shape, dtype=np.float64)
        object.__setattr__(self, name, a)
        return a

    # ---- 確保済みの配列を調べる（デバッグ用） ----
    def allocated(self):
        """今までに確保した配列の名前と総バイト数。"""
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


def init_gval():
    """main.c:55 init_gval() の忠実移植。

    Kra / Krb / Scutrrh / Scutrrt / Scutrrki / Escutrrh / Escutrrt / Tokutyo を
    年齢 60〜115 の範囲だけ 1.0 で埋める。ゼロのままの所（x < ECXA に当たる
    要素は存在しない）と、k=0 の行はそのまま。
    """
    for k in range(ECSTY, ECEDY + 1):
        for x in range(ECXA, 116):      # 原本 main.c:60 for(x=ECXA; x<116; x++)
            G.Kra[k - ECSTY, x - ECXA] = 1.0
            G.Krb[k - ECSTY, x - ECXA] = 1.0

            G.Scutrrh[k - ECSTY, x - ECXA] = 1.0
            G.Scutrrt[k - ECSTY, x - ECXA] = 1.0
            G.Scutrrki[k - ECSTY, x - ECXA] = 1.0
            G.Escutrrh[k - ECSTY, x - ECXA] = 1.0
            G.Escutrrt[k - ECSTY, x - ECXA] = 1.0
            G.Tokutyo[k - ECSTY, x - ECXA] = 1.0
