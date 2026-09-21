# -*- coding: utf-8 -*-
"""
rdfl.py の Python 最適版（速度の比較用）
========================================
`rdfl.py` は原本 rdfl.c を1行ずつ忠実に写したもので、そのぶん遅い。
こちらは**同じ結果を出しつつ Python らしく書いたら何秒になるか**を測るための
実装。忠実版と CRC32 で突き合わせて、結果が変わっていないことを確かめる
（`検証/移植/test_rdfl_fast.py`）。

忠実版が遅い理由は cProfile ではっきりしていた（総272秒のうち）。

    rd_drec   170 秒  1文字ずつ走査。list.append が 3.38 億回
    c_atof     47 秒  strtod の文法を正規表現で再現
    代入       16 秒  NumPy へのスカラー代入
    I/O         3 秒

やっていること
--------------
1. **行の取得をまとめる。** 1行ごとの `fgets` をやめ、ファイルを一括で
   readlines する。

2. **レコードの分解を `str.split(',')` にする。** 原本の `rd_drec()` は
   C の文字列処理をそのまま写したものなので1文字ずつ回るが、やっている
   ことは「カンマで割って atof」。`split` は C で動くので段違いに速い。

3. **`float()` を使う。** `c_atof()` は C の `atof()` の「読めない文字列でも
   0.0 を返す」「16進も読む」といった挙動まで再現しているが、実データは
   ただの10進数なので `float()` で足りる。Python の `float()` も
   `strtod` と同じ**正しい丸め**なので、値はビット単位で同じになる。

4. **`np.fromiter(map(float, ...))` で一括変換する。** 要素ごとの Python
   ループを避けて C の中で回す。

5. **代入をスライスにする。** `for s in range(4): G.Ap[ii,s,k-STTY] = ...`
   を `G.Ap[ii, 0:4, k-STTY] = ...` にまとめる。

ビット一致は崩れない
--------------------
ここでやっているのは**読み取りと代入だけ**で、浮動小数点の演算をまとめたり
順序を変えたりしていない。`float()` は正しく丸めるので、原本の `atof()` と
同じ double になる。足し込み（`D3bxtp[0] += ...`）の順序も原本どおり
ii=1→4、行の順に保っている。だから**速くしてもビット一致は保てる**。

順序を変えると危ないのは総和などの縮約で、それはこの先の shus*.c に出てくる。
"""
import numpy as np

from cnum import nround
from glva import G
from setconst import (ECEDY, ECSTY, ECXA, ENDY, FLKE, FLKS, MAX, STTY, XA, XB)


class Rd:
    """ファイルを一括で読んで行単位に歩く。原本の fgets の位置を再現する。"""

    __slots__ = ("lines", "i")

    def __init__(self, cfile):
        # cfile は途中まで読まれている（flck が header を読み飛ばしている）。
        # 残りを一括で取る。バイト透過のため latin-1。
        self.lines = cfile._f.read().decode("latin-1").splitlines(keepends=True)
        self.i = 0

    def skip(self, n=1):
        self.i += n

    def take(self, n):
        """n 行を返して位置を進める（足りなければあるだけ）。"""
        out = self.lines[self.i:self.i + n]
        self.i += n
        return out


def _cols(lines, ncols):
    """行の並びを (len(lines), ncols) の float64 配列にする。

    `float()` は正しく丸めるので、原本の `atof()` と同じ double になる。
    """
    n = len(lines)
    if n == 0:
        return np.empty((0, ncols), dtype=np.float64)
    flat = []
    ext = flat.extend
    for ln in lines:
        ext(ln.split(",", ncols)[:ncols])
    return np.fromiter(map(float, flat), dtype=np.float64,
                       count=n * ncols).reshape(n, ncols)


def rdfl():
    """rdfl.py の rdfl() と同じ結果を出す最適版。"""
    rdfl_u_sys()
    rdfl_kyos()
    rdfl_sien()
    rdfl_cut()


def rdfl_u_sys():
    is_, ie = 1, 4

    for ii in range(is_, ie + 1):
        r = Rd(G.ifp10_usys[ii])

        head = _cols(r.take(1), 2)
        if ii == is_:
            G.Ks = int(head[0, 0])
            G.Ke = int(head[0, 1])
            if G.Ks < STTY or ENDY < G.Ke:
                print("KsがSTTYより小さい、又は、KeがENDYより大きいです。")
                raise SystemExit(1)
        else:
            if G.Ks != int(head[0, 0]) or G.Ke != int(head[0, 1]):
                print("u-sysの出力ファイル間でKs,Keの整合性がありません")
                raise SystemExit(1)

        Ks, Ke = G.Ks, G.Ke
        # FLKS..FLKE の並びのうち Ks..Ke が使う範囲（連続しているのでスライス）
        lo = Ks - FLKS
        hi = Ke - FLKS + 1
        nrow = FLKE - FLKS + 1
        ks_ke = slice(Ks - STTY, Ke - STTY + 1)

        # ---- 経済前提の整合チェック ----
        r.skip(2)
        ec = _cols(r.take(Ke), 3)
        yrs = ec[:, 0].astype(np.int64)
        bad = np.nonzero(yrs != np.arange(1, Ke + 1))[0]
        if bad.size:
            print(f"年度が違います(rdfl_u_sys:経済前提), K={bad[0] + 1}")
            raise SystemExit(1)
        for k in range(Ks, Ke + 1):
            if (nround(ec[k - 1, 1], 12) != nround(float(G.Ri[k - ECSTY]), 5)
                    or nround(ec[k - 1, 2], 12) != nround(float(G.H[k - ECSTY]), 5)):
                print("u-sysファイルと設定したeconファイルの経済前提"
                      f"（賃金、利回り）が一致しません。K={k} ")
                raise SystemExit(1)

        def block(ncols):
            """ヘッダ2行を飛ばし、FLKS..FLKE の行のうち Ks..Ke 分を返す。"""
            r.skip(2)
            rows = r.take(nrow)[lo:hi]
            a = _cols(rows, ncols)
            if a.shape[0]:
                y = a[:, 0].astype(np.int64)
                want = np.arange(Ks, Ke + 1)
                if not np.array_equal(y, want):
                    j = int(np.nonzero(y != want)[0][0])
                    print(f"年度が違います, K={want[j]}")
                    raise SystemExit(1)
            return a

        a = block(8)                                   # Ap / Apdum
        G.Ap[ii, 0:4, ks_ke] = a[:, 1:5].T
        G.Apdum[ii, 1:4, ks_ke] = a[:, 5:8].T

        a = block(9)                                   # Ap65 / Ap70
        G.Ap65[ii, 0:4, ks_ke] = a[:, 1:5].T
        G.Ap70[ii, 0:4, ks_ke] = a[:, 5:9].T

        a = block(20)                                  # A / Adum / A60 / A65 / A70
        G.A[ii, 0:4, ks_ke] = a[:, 1:5].T
        G.Adum[ii, 1:4, ks_ke] = a[:, 5:8].T
        G.A60[ii, 0:4, ks_ke] = a[:, 8:12].T
        G.A65[ii, 0:4, ks_ke] = a[:, 12:16].T
        G.A70[ii, 0:4, ks_ke] = a[:, 16:20].T

        a = block(8)                                   # Aiku / Aikudum
        G.Aiku[ii, 0:4, ks_ke] = a[:, 1:5].T
        G.Aikudum[ii, 1:4, ks_ke] = a[:, 5:8].T

        a = block(5)                                   # Aal
        G.Aal[ii, 0:4, ks_ke] = a[:, 1:5].T

        # ---- 適用拡大分（第1号厚生年金だけ） ----
        if ii == 1:
            r.skip(2)
            for k in ([G.Part_Yr2, G.Part_Yr3] if G.Flg_Part >= 1
                      else [G.Part_Yr2]):
                a = _cols(r.take(1), 21)
                if int(a[0, 0]) != k:
                    print(f"年度が違いますPart, K={k} <> {int(a[0, 0])}")
                    raise SystemExit(1)
                c = G.Cbm_Pt1 / 12.0
                G.Apart[0:4, k - STTY] = a[0, 1:5] * G.Cbm_Pt1 / 12.0
                G.Aikupart[0:4, k - STTY] = a[0, 5:9] * G.Cbm_Pt1 / 12.0
                G.A60part[0:4, k - STTY] = a[0, 9:13] * G.Cbm_Pt1 / 12.0
                G.A65part[0:4, k - STTY] = a[0, 13:17] * G.Cbm_Pt1 / 12.0
                G.A70part[0:4, k - STTY] = a[0, 17:21] * G.Cbm_Pt1 / 12.0

        # ---- An / Aniku ----
        snc = G.Shunor if ii == 1 else 1.0
        G.An[ii, 0:4, ks_ke] = G.A[ii, 0:4, ks_ke] * snc
        G.Aniku[ii, 0:4, ks_ke] = G.Aiku[ii, 0:4, ks_ke] * snc
        if ii == 1:
            G.Anpart[0:4, ks_ke] = G.Apart[0:4, ks_ke] * snc
            G.Anikupart[0:4, ks_ke] = G.Aikupart[0:4, ks_ke] * snc

        # ---- T4xtp ----
        for x in range(XA - 1, XB + 1):
            for s in range(1, 4):
                a = block(8)
                v = a[:, 1:8].T                        # (7, nyear)
                G.T4xtp[ii, s, 0:7, ks_ke, x] = v
                G.T4xtp[ii, 0, 0:7, ks_ke, x] += v

        # ---- D3bxtp / Kfpbxtp / Kofbxtp / Kofte / Kofkk ----
        acc = (ii == 1)
        for x in range(XA - 1, XB + 1):
            for s in range(0, 4):
                for ui in range(0, 14):
                    a = block(11)
                    G.Kfpbxtp[ii, s, ui, 7, ks_ke, x] = a[:, 1]
                    G.D3bxtp[ii, s, ui, 1, ks_ke, x] = a[:, 2]
                    G.D3bxtp[ii, s, ui, 3:8, ks_ke, x] = a[:, 3:8].T
                    G.Kofbxtp[ii, s, ui, ks_ke, x] = a[:, 8]
                    G.Kofte[ii, s, ui, ks_ke, x] = a[:, 9]
                    G.Kofkk[ii, s, ui, ks_ke, x] = a[:, 10]
                    if acc:
                        G.Kfpbxtp[0, s, ui, 7, ks_ke, x] += a[:, 1]
                        G.D3bxtp[0, s, ui, 1, ks_ke, x] += a[:, 2]
                        G.D3bxtp[0, s, ui, 3:8, ks_ke, x] += a[:, 3:8].T
                        G.Kofbxtp[0, s, ui, ks_ke, x] += a[:, 8]
                        G.Kofte[0, s, ui, ks_ke, x] += a[:, 9]
                        G.Kofkk[0, s, ui, ks_ke, x] += a[:, 10]

        # ---- Kfpbxtp の uj=1,2 ----
        for x in range(XA - 1, XB + 1):
            for ui in range(0, 14):
                a = block(9)
                for s in range(0, 4):
                    v = a[:, s * 2 + 1:s * 2 + 3].T    # (2, nyear)
                    G.Kfpbxtp[ii, s, ui, 1:3, ks_ke, x] = v
                    if acc:
                        G.Kfpbxtp[0, s, ui, 1:3, ks_ke, x] += v

        # ---- Ap から Ap70 を引いて Ap70 をゼロに ----
        send = 4 if ii == 1 else 3
        G.Ap[ii, 0:send, ks_ke] -= G.Ap70[ii, 0:send, ks_ke]
        G.Ap70[ii, 0:send, ks_ke] = 0.


def rdfl_kyos():
    r = Rd(G.ifp_kyos)
    Ks, Ke = G.Ks, G.Ke
    ss_end = 6 if G.Touitu == 0 else 8

    nrow = FLKE - (FLKS - 5) + 1
    lo = Ks - (FLKS - 5)
    hi = Ke - (FLKS - 5) + 1
    ks_ke = slice(Ks - STTY, Ke - STTY + 1)
    ncols = 4 + (XB - (XA - 1) + 1)

    for sh in range(0, 2):
        r.skip(1)
        for ss in range(0, ss_end + 1):
            for ii in range(1, 5):
                rows = r.take(nrow)[lo:hi]
                a = _cols(rows, ncols)
                if a.shape[0]:
                    want = np.arange(Ks, Ke + 1)
                    if (not np.array_equal(a[:, 0].astype(np.int64), want)
                            or not np.all(a[:, 1].astype(np.int64) == ss)
                            or not np.all(a[:, 2].astype(np.int64) == ii)):
                        print("基礎年金拠出金の読ませ方が違います。")
                        raise SystemExit(1)
                v = a[:, 4:4 + (XB - (XA - 1) + 1)]    # (nyear, 53)
                if ii <= 2:
                    G.Kyosdx[sh, ss, ii - 1, ks_ke, XA - 1:XB + 1] = v
                else:
                    G.Kfkyosdx[sh, ss, ii - 3, ks_ke, XA - 1:XB + 1] = v

    # ---- 妻積 ----
    r = Rd(G.ifp27_tuma)
    r.skip(1)
    rows = r.take(FLKE - 15 + 1)[Ks - 15:Ke - 15 + 1]
    a = _cols(rows, 6)
    if a.shape[0] and not np.array_equal(a[:, 0].astype(np.int64),
                                        np.arange(Ks, Ke + 1)):
        print("妻積ファイルの読ませ方が違います")
        raise SystemExit(1)
    G.Tumazumi[1:5, ks_ke] = a[:, 2:6].T

    # ---- provide ----
    if G.Touitu >= 1:
        r = Rd(G.ifp_Touitu)
        lo2 = Ks - 20
        hi2 = Ke - 20 + 1
        n2 = FLKE - 20 + 1

        r.skip(1)
        a = _cols(r.take(n2)[lo2:hi2], 6)
        G.Kokusyushi[0:5, ks_ke] = a[:, 1:6].T

        r.skip(3)
        a = _cols(r.take(n2)[lo2:hi2], 5)
        G.Kokusyushi[5:9, ks_ke] = a[:, 1:5].T

        r.skip(3)
        a = _cols(r.take(n2)[lo2:hi2], 2)
        G.Kokusyushi[9, ks_ke] = a[:, 1]


def rdfl_sien():
    r = Rd(G.ifp_nofu)
    r.skip(2)
    a = _cols(r.take(55 - 22 + 1), 3)
    ks = slice(22 - STTY, 55 - STTY + 1)
    if not np.array_equal(a[:, 0].astype(np.int64), np.arange(22, 56)):
        print("納付金の読ませ方が違います。")
        raise SystemExit(1)
    G.Nofu[1, ks] = a[:, 1]
    G.Jyutaku[ks] = a[:, 2]
    G.Nofu[0, ks] = a[:, 1]


def rdfl_cut():
    """原本の各ループは必ず `for(k=5; k<=FLKE; k++)` で回り、
    `if(k<下限 || k>上限) continue;` で絞る。つまり実際に埋まる年度は
    `max(5, 下限) .. min(FLKE, 上限)` になる。FLKE=125 で ECEDY=128 なので、
    上限に ECEDY を書いてある所も 125 までしか埋まらない。
    """
    Ke = G.Ke

    def read(cfile, lo, hi, ncols):
        """5..FLKE の行を読み、lo..hi の範囲だけ返す。lo..hi はクランプ済み。"""
        r = Rd(cfile)
        rows = r.take(FLKE - 5 + 1)[lo - 5:hi - 5 + 1]
        return _cols(rows, ncols)

    n67 = XB - 67 + 1
    lo = MAX(5, ECSTY)

    # ---- 厚年比例の改定率 → Krb（上限は Ke） ----
    hi = MIN_(FLKE, Ke)
    a = read(G.ifp_kaiteb, lo, hi, 1 + n67)
    yr = slice(lo - ECSTY, hi - ECSTY + 1)
    G.Krb[yr, 67 - ECXA:XB - ECXA + 1] = a[:, 1:1 + n67]

    # ---- 厚年定額 or 国年の改定率 → Kra ----
    if G.Cutrfile1[:1] == "0":
        a = read(G.ifp_kaitea, lo, hi, 1 + n67)
    elif G.Cutrfile1[:1] == "1":
        a = read(G.ifp_kokukaite, lo, hi, 1 + n67)
    else:
        print("Cutrfile1(厚年先決めor国年先決め)がうまく設定されていません。")
        raise SystemExit(1)
    G.Kra[yr, 67 - ECXA:XB - ECXA + 1] = a[:, 1:1 + n67]

    # ---- 67歳未満は67歳の値で埋める（こちらの上限は Ke のまま） ----
    for k in range(MAX(5, ECSTY), Ke + 1):
        G.Kra[k - ECSTY, 0:67 - ECXA] = G.Kra[k - ECSTY, 67 - ECXA]
        G.Krb[k - ECSTY, 0:67 - ECXA] = G.Krb[k - ECSTY, 67 - ECXA]

    # ---- 以下は上限が ECEDY だが FLKE でクランプされる ----
    hi2 = MIN_(FLKE, ECEDY)
    ecyr = slice(lo - ECSTY, hi2 - ECSTY + 1)
    ncut = 116 - (XA - 1)
    xs = slice(XA - 1 - ECXA, 116 - ECXA)

    # ---- 毎年のスライド調整率 → Scutrk1 ----
    if G.Fpset != 9:
        a = read(G.ifp_wakum, lo, hi2, 2)
        yrs = a[:, 0].astype(np.int64)
        want = np.arange(lo, hi2 + 1) + 2000       # このファイルだけ西暦
        if not np.array_equal(yrs, want):
            j = int(np.nonzero(yrs != want)[0][0])
            print("調整率ファイルの読ませ方が違います。, "
                  f"K={lo + j} <> {int(yrs[j]) - 2000}")
            raise SystemExit(1)
        G.Scutrk1[ecyr] = a[:, 1]

    # ---- 国年のカット率 → Scutrrki ----
    if G.Fpset == 8 and G.Cutrfile1[:1] == "1":
        a = read(G.ifp_bas_cuta, lo, hi2, 1 + ncut)
        G.Scutrrki[ecyr, xs] = a[:, 1:1 + ncut]

    # ---- カット率ファイル指定 ----
    if G.Fpset == 9:
        a = read(G.ifp_asys_cutb, lo, hi2, 1 + ncut)
        G.Scutrrh[ecyr, xs] = a[:, 1:1 + ncut]
        a = read(G.ifp_asys_cuta, lo, hi2, 1 + ncut)
        G.Scutrrt[ecyr, xs] = a[:, 1:1 + ncut]


def MIN_(a, b):
    return a if a < b else b
