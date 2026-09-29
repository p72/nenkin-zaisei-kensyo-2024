# -*- coding: utf-8 -*-
"""①被保険者推計の設定と入力（移植版 `cntl.c` `readdata.c` `simlkyos.c` の読み込み部）
======================================================================================
設定（港の標準入力 7 項目のうち試算番号を除く 6 つ）と、`wakuc/data/` の 17 本の CSV を
読んで状態 `Hiho` に置く。計算はしない。

年度の軸
--------
①は西暦そのままで 2020〜2150 年度（`hihokensha.years.starty/endy`）を持つ。パッケージの
`YEARS`（2000〜2125）とは別の軸 `Settings.hy` を使い、出力を `Waku` に置くときだけ
`YEARS` に写す。性の軸は 0 男女計 / 1 男 / 2 女 / 3 女有配偶 / 4 女無配偶（`contracts.SEXES`）。

港の読み手との違い
------------------
- 港は `atof` で読む（読めない欄は 0）。ここも同じ（`_f`）
- 港の「年度が減ったら読み止める」は人口・有配偶率で同じにする。ファイルの並びが
  年齢順・年度順なので結果は同じ
- 共済（`simlkyos.c` の読み込み）もここで読む。`KIJUNMAP` より後の年度だけ取り込む

港: hihokensha/readdata.py:readdata, read_roud, read_map
港: hihokensha/cntl.py:cntl
仕様: §2、§11 ①
"""
from dataclasses import dataclass, field
import os

import numpy as np

from ...axis import Axis, AGES
from ...options import options_of

__all__ = ["NSEX", "NAGE", "Settings", "settings", "Hiho", "new_state", "read_inputs", "HihoInputs"]

NSEX = 5
NAGE = AGES.n


# ---------------------------------------------------------------- 設定

@dataclass(frozen=True)
class Settings:
    """港の `cntl()` が決める設定と `set.h` の定数。年度は西暦。"""
    jin: int                 # 出生 1 中位 / 2 高位 / 3 低位
    qx: int                  # 死亡 1 中位 / 2 高位 / 3 低位
    nc: int                  # 入国超過 0 16万 / 1 6.9万 / 2 25万
    roudr: int               # 労働力率 1〜9
    mode: int                # 適用拡大 0〜5
    mode45: int              # 基礎45年化 0 / 1
    part: int                # 適用拡大の段階数（0 / 2）
    partyr1: int
    partyr2: int
    partkyr: int
    starty: int
    endy: int
    sjinkoy: int
    fjinkoy: int
    yuhaigy: int
    roudyr: int
    kijun: int
    kijunmap: int
    ks: int
    kf: int
    cnendo: int
    cut_jy: int
    part_start: int
    hy: Axis                 # ①の年度の軸（starty〜endy）
    cy: Axis                 # 調整率の年度の軸（cnendo〜endy）
    pol: object = None       # policy（各段が yaml の葉を引く）


def settings(pol, jin=1, qx=1, nc=0, roudr=1, mode=0, mode45=0):
    """港: hihokensha/cntl.py:cntl。MODE ≥ 1 は 5 通りとも同じ 2 段階（yaml `hihokensha.part.mode_ge1`）。"""
    Y = pol.get("hihokensha.years")
    P = pol.get("hihokensha.part")
    if not (1 <= jin <= 3 and 1 <= qx <= 3 and 0 <= nc <= 2 and 1 <= roudr <= 9 and 0 <= mode <= 5
            and mode45 in (0, 1)):
        raise ValueError("設定が範囲外: jin=%r qx=%r nc=%r roudr=%r mode=%r mode45=%r"
                         % (jin, qx, nc, roudr, mode, mode45))
    starty, endy = int(Y["starty"]), int(Y["endy"])
    if starty != int(Y["sjinkoy"]):
        raise ValueError("推計初年度 (starty) が人口のスタート年度 (sjinkoy) と一致していない")
    part, yr1, yr2 = 0, endy + 1, endy + 1
    if mode >= 1:
        M = P["mode_ge1"]
        part, yr1, yr2 = int(M["part"]), int(M["partyr1"]), int(M["partyr2"])
    return Settings(jin, qx, nc, roudr, mode, mode45, part, yr1, yr2, int(P["partkyr"]),
                    starty, endy, int(Y["sjinkoy"]), int(Y["fjinkoy"]), int(Y["yuhaigy"]), int(Y["roudyr"]),
                    int(Y["kijun"]), int(Y["kijunmap"]), int(Y["ks"]), int(Y["kf"]),
                    int(Y["cnendo"]), int(Y["cut_jy"]), int(Y["part_start"]),
                    Axis("①の年度", starty, endy), Axis("調整率の年度", int(Y["cnendo"]), endy), pol)


# ---------------------------------------------------------------- 状態

@dataclass
class Hiho:
    """①の配列（名前は港の `mcntl.h` のまま）。年度の添字は `Settings.hy`。

    `_c` は年央（10 月 1 日）、`_m` は年度末。`koyou_j_*[ii]` の ii は 0 計 / 1 正規 /
    2 非正規フル / 3〜6 非正規の時間別 / 7 被用者計 / 8 正規被用者 / 9 非正規フル被用者 /
    10 非正規フル以外被用者。`kounen[seido]` は 0 計 / 1 厚年 / 2 旧厚12種 / 3 旧厚3種 /
    4 国共済 / 5 地共済 / 6 私学。`sangou` は 0 計 / 1 旧厚 / 2 旧厚12種 / 3 旧厚3種 / 4〜6 共済。
    `ichigou` は 0 計 / 1 一般 / 2 任意。`partnin[pkubun, tkubun, ykubun, y, s, x]`（港は
    (y, s, x, p, t, yk)。年度・性・年齢の面を連続にするため前に出した。ykubun の軸は
    段階数 + 1）。`kbetu_partkiso[pkubun, tkubun, ykubun, s, kubun]`。
    """
    jinko_c: np.ndarray
    jinko_m: np.ndarray
    sojinko_c: np.ndarray
    jinko_wari: np.ndarray
    yuhaig_r: np.ndarray
    roud_r: np.ndarray
    roud_j_c: np.ndarray
    roud_j_m: np.ndarray
    syugyo_r: np.ndarray
    syugyo_j_c: np.ndarray
    syugyo_j_m: np.ndarray
    koyou_j_c: np.ndarray
    koyou_j_m: np.ndarray
    koyou_r: np.ndarray
    seiki_hiseiki_r: np.ndarray
    hiseiki_jikan_r: np.ndarray
    hiseiki_tan_r_all: np.ndarray
    jieigyo_j_c: np.ndarray
    jieigyo_j_m: np.ndarray
    soroudh_c: np.ndarray
    soroudh_m: np.ndarray
    heikinh_c: np.ndarray
    heikinh_m: np.ndarray
    kounenteki_c: np.ndarray
    kounenteki_m: np.ndarray
    nigou: np.ndarray
    kounen: np.ndarray
    sangou: np.ndarray
    ichigou: np.ndarray
    mika_soto: np.ndarray
    ichiyuhaigr: np.ndarray
    partnin: np.ndarray
    kbetu_partkiso: np.ndarray
    cutritu: np.ndarray          # 調整率（cy の軸。実績を読み、cutritu.py が先を埋める）
    xend: np.ndarray             # int。1・3号の上限年齢（年度ごと）
    notes: list = field(default_factory=list)   # 港が printf / fp_err に出す注意（件数と文言）


def new_state(S):
    ny, nc = S.hy.n, S.cy.n
    nyk = S.part + 2                                     # ykubun 0 累積 ＋ 段階 1〜part+1
    z = lambda *shape: np.zeros(shape, dtype=np.float64)       # noqa: E731
    return Hiho(
        jinko_c=z(ny, NSEX, NAGE), jinko_m=z(ny, NSEX, NAGE), sojinko_c=z(ny, NSEX),
        jinko_wari=z(NSEX, NAGE), yuhaig_r=z(ny, NAGE),
        roud_r=z(ny, NSEX, NAGE), roud_j_c=z(ny, NSEX, NAGE), roud_j_m=z(ny, NSEX, NAGE),
        syugyo_r=z(ny, NSEX, NAGE), syugyo_j_c=z(ny, NSEX, NAGE), syugyo_j_m=z(ny, NSEX, NAGE),
        koyou_j_c=z(11, ny, NSEX, NAGE), koyou_j_m=z(11, ny, NSEX, NAGE), koyou_r=z(ny, NSEX, NAGE),
        seiki_hiseiki_r=z(4, ny, NSEX, NAGE), hiseiki_jikan_r=z(NSEX, ny), hiseiki_tan_r_all=z(ny),
        jieigyo_j_c=z(ny, NSEX, NAGE), jieigyo_j_m=z(ny, NSEX, NAGE),
        soroudh_c=z(10, ny, NSEX, NAGE), soroudh_m=z(10, ny, NSEX, NAGE),
        heikinh_c=z(11, ny), heikinh_m=z(11, ny), kounenteki_c=z(10, ny), kounenteki_m=z(10, ny),
        nigou=z(ny, NSEX, NAGE), kounen=z(7, ny, NSEX, NAGE), sangou=z(7, ny, NSEX, NAGE),
        ichigou=z(3, ny, NSEX, NAGE), mika_soto=z(ny, NSEX, NAGE), ichiyuhaigr=z(NAGE),
        partnin=z(8, 4, nyk, ny, NSEX, NAGE), kbetu_partkiso=z(8, 4, nyk, NSEX, 17), cutritu=z(nc),
        xend=np.zeros(ny, dtype=np.int64))


# ---------------------------------------------------------------- 読み手

def _f(s):
    """C の `atof`。読めなければ 0。"""
    try:
        return float(s)
    except ValueError:
        return 0.0


def _rows(path):
    """全行を数値の list に（空欄は 0）。行の位置で読むので空行も残す。

    港と同じく `\\n` だけを行の切れ目にする（見出しの日本語のバイト列に `str.splitlines` が
    行の切れ目と見なす制御文字が混じるため。数値は ASCII なので latin-1 で読めば足りる）。
    """
    raw = open(path, "rb").read().decode("latin-1")
    L = raw.split("\n")
    if L and L[-1] == "":
        L.pop()
    return [[_f(x) for x in l.rstrip("\r").split(",")] for l in L]


def _paths(data_dir, S):
    """港 fopn.py の `sprintf` をそのまま。`data_dir` は `wakuc/data`。"""
    d = lambda *p: os.path.join(data_dir, *p)          # noqa: E731
    tag = "%d%d%d" % (S.jin, S.qx, S.nc)
    return dict(
        pop={sei: d("sinj", "pop%d-%s.csv" % (sei, tag)) for sei in (1, 2)},
        wari=d("sinj", "wari-2020.csv"), yuhaigr=d("sinj", "yuhaigr_suikei-2020.csv"),
        roudou=d("roud2024", "roudou2024-%d.csv" % S.roudr), syugyor=d("roud2024", "syugyor2024-%d.csv" % S.roudr),
        koyour=d("roud2024", "koyour2022.csv"), seikir=d("roud2024", "seikir2022.csv"),
        hiseikifurur=d("roud2024", "hiseikifurur2022.csv"), hiseikitanr=d("roud2024", "hiseikitanr2022.csv"),
        syosettei=d("roud2024", "syosettei2022-%d.csv" % S.roudr),
        map_={y: d("map", "%dmap.csv" % y) for y in range(S.starty, S.kijunmap)}
        | {S.kijunmap: d("map", "%dmap%s.csv" % (S.kijunmap, "-45" if S.mode45 == 1 else ""))},
        ichiyuhaigr=d("prev", "ichiyuhaigr2022.csv"), ichisanxend=d("prev", "ichisanxend2022.csv"),
        cut_jisseki=d("map", "cut_jisseki.csv"),
        part=[d("part", "partnin2020-2024.csv"), d("part", "partnin2020-2027-%d.csv" % S.mode),
              d("part", "partnin2020-2029-%d.csv" % S.mode)],
        kyos={4: d("kyos", "kok2022-%s.csv" % tag), 5: d("kyos", "ren2022-%s.csv" % tag),
              6: d("kyos", "sig2022-%s.csv" % tag)})


def _read_pop(path, sei, S, H):
    """readdata.c:31-57。年度, 性, 総数, 0〜120 歳。年度が増えている間だけ読む。"""
    prev = -1000.
    for r in _rows(path)[1:]:
        if not r or not (r[0] > prev):
            break
        y, jj = int(r[0]), int(r[1])
        if not S.hy.contains(y):
            raise ValueError("%s: 年度 %d は範囲外" % (path, y))
        if jj != sei:
            raise ValueError("%s: 性 %d が %d でない" % (path, jj, sei))
        H.sojinko_c[S.hy.i(y), jj] = r[2]
        v = r[3:3 + NAGE]                                  # 同梱データは 105 歳まで。無い年齢は 0（港も 0）
        H.jinko_c[S.hy.i(y), jj, :len(v)] = v
        prev = r[0]


def _read_wari(path, H):
    """readdata.c:59-77。年齢, 男, 女。女の値を 2・3・4 に入れる。"""
    for r in _rows(path)[1:]:
        if not r:
            continue
        x = int(r[0])
        H.jinko_wari[1, x] = r[1]
        H.jinko_wari[2:5, x] = r[2]


def _read_yuhaigr(path, S, H):
    """readdata.c:79-102。年度, 2, (空), 15〜105 歳。"""
    lo, hi = 15, 105
    prev = -1000.
    for r in _rows(path)[1:]:
        if not r or not (r[0] > prev):
            break
        y = int(r[0])
        if int(r[1]) != 2:
            raise ValueError("%s: 性が 2 でない" % path)
        H.yuhaig_r[S.hy.i(y), lo:hi + 1] = r[3:3 + hi - lo + 1]
        prev = r[0]


def _read_roud(path, yend, S, dst):
    """readdata.c:439。先頭 1 行、そのあと（2 行 ＋ 年度ぶん）× 3 ブロック。列は 年度, 性, (計), 15〜105 歳。
    港: hihokensha/readdata.py:read_roud"""
    lo, hi = 15, 105
    rows = _rows(path)
    n = yend - S.starty + 1
    pos = 1
    for _ in range(3):
        pos += 2
        for r in rows[pos:pos + n]:
            y, s = int(r[0]), int(r[1])
            dst[S.hy.i(y), s, lo:hi + 1] = r[3:3 + hi - lo + 1]
        pos += n


def _read_syosettei(path, S, H):
    """readdata.c:235-271。年度, ケース, 非正規短時間の全体割合, 平均労働時間 9 区分, 時間帯 4 区分（12+13, 14, 15, 16）,
    厚年適用率 6 区分。"""
    rows = _rows(path)[2:]
    for r in rows[:S.roudyr - S.starty + 1]:
        y, kk = int(r[0]), int(r[1])
        if kk != S.roudr:
            raise ValueError("%s: ケース %d が労働力率の設定 %d と一致しない" % (path, kk, S.roudr))
        i = S.hy.i(y)
        H.hiseiki_tan_r_all[i] = r[2]
        H.heikinh_c[1:10, i] = r[3:12]
        H.hiseiki_jikan_r[1, i] = r[12] + r[13]
        H.hiseiki_jikan_r[2:5, i] = r[14:17]
        H.kounenteki_c[1:7, i] = r[17:23]


def _read_map(path, y, S, H):
    """readdata.c:462。先頭 1 行、性ごとに（2 行 ＋ 15〜89 歳の 75 行）。列は
    年齢, 厚年12種, 厚年3種, 国共2号, 地共2号, 私学2号, パート, 旧厚3号, 国共3号, 地共3号, 私学3号, 1号一般, 1号任意。
    港: hihokensha/readdata.py:read_map"""
    lo, hi = 15, 89
    rows = _rows(path)
    i = S.hy.i(y)
    K, Sg, I, P = H.kounen, H.sangou, H.ichigou, H.partnin
    pos = 1
    for jj in (1, 2):
        pos += 2
        for r in rows[pos:pos + hi - lo + 1]:
            x = int(r[0])
            K[2:7, i, jj, x] = r[1:6]
            P[0, 0, 0, i, jj, x] = r[6]
            Sg[1, i, jj, x] = r[7]
            Sg[4:7, i, jj, x] = r[8:11]
            I[1, i, jj, x] = r[11]
            I[2, i, jj, x] = r[12]
        pos += hi - lo + 1
    K[1, i, 1:3] = K[2, i, 1:3] + K[3, i, 1:3]
    K[0, i, 1:3] = K[1, i, 1:3] + K[4, i, 1:3] + K[5, i, 1:3] + K[6, i, 1:3]
    Sg[0, i, 1:3] = Sg[1, i, 1:3] + Sg[4, i, 1:3] + Sg[5, i, 1:3] + Sg[6, i, 1:3]
    I[0, i, 1:3] = I[1, i, 1:3] + I[2, i, 1:3]
    K[:, i, 0] = K[:, i, 1] + K[:, i, 2]
    Sg[:, i, 0] = Sg[:, i, 1] + Sg[:, i, 2]
    I[:, i, 0] = I[:, i, 1] + I[:, i, 2]
    P[0, 0, 0, i, 0] = P[0, 0, 0, i, 1] + P[0, 0, 0, i, 2]


def _read_part(path, ykubun, H):
    """readdata.c:343-370。年齢区分 1〜11、18 個の並びは 時間区分(1,2,3) × 性(1,2) × 元制度(1,2,7)。"""
    for r in _rows(path)[1:12]:
        ii = int(r[0])
        k = 1
        for t in (1, 2, 3):
            for s in (1, 2):
                for p in (1, 2, 7):
                    H.kbetu_partkiso[p, t, ykubun, s, ii] = r[k]
                    k += 1


def _read_kyos(path, seido, S, H):
    """simlkyos.c:23-58。性ごとに sjinkoy〜fjinkoy の行。列は seido−3, 性, 年度, 計, 15〜100 歳。
    `kijunmap` より後の年度だけ取り込む（実績は map から）。"""
    lo, hi = 15, 100
    rows = _rows(path)[1:]
    n = S.fjinkoy - S.sjinkoy + 1
    for k, r in enumerate(rows[:2 * n]):
        if r[0] + 3 != seido:
            raise ValueError("%s: seido 番号 %r が %d と合わない" % (path, r[0], seido))
        s, y = int(r[1]), int(r[2])
        if y > S.kijunmap:
            H.kounen[seido, S.hy.i(y), s, lo:hi + 1] = r[4:4 + hi - lo + 1]


@dataclass
class HihoInputs:
    pol: object
    S: Settings
    H: Hiho
    data_dir: str


def read_inputs(pol, data_dir, jin=1, qx=1, nc=0, roudr=1, mode=None, mode45=None):
    """`data_dir` は `work/suuri/rev2024/wakuc/data`。`mode`（適用拡大）・`mode45`（45年化）を省略すると
    policy の `options.kakudai` / `options.sigo`。港: hihokensha/readdata.py:readdata"""
    opt = options_of(pol)
    S = settings(pol, jin, qx, nc, roudr, opt.kakudai if mode is None else mode,
                 opt.sigo if mode45 is None else mode45)
    H = new_state(S)
    P = _paths(data_dir, S)
    hy = S.hy
    for sei in (1, 2):
        _read_pop(P["pop"][sei], sei, S, H)
    _read_wari(P["wari"], H)
    _read_yuhaigr(P["yuhaigr"], S, H)
    _read_roud(P["roudou"], S.roudyr, S, H.roud_r)
    _read_roud(P["syugyor"], S.roudyr, S, H.syugyo_r)
    _read_roud(P["koyour"], S.endy, S, H.koyou_r)
    _read_roud(P["seikir"], S.roudyr, S, H.seiki_hiseiki_r[1])
    _read_roud(P["hiseikifurur"], S.roudyr, S, H.seiki_hiseiki_r[2])
    _read_roud(P["hiseikitanr"], S.roudyr, S, H.seiki_hiseiki_r[3])
    _read_syosettei(P["syosettei"], S, H)
    for y, path in P["map_"].items():
        _read_map(path, y, S, H)
    A = pol.get("hihokensha.ages")
    lo, hi = A["ichiyuhaigr"]
    for r in _rows(P["ichiyuhaigr"])[1:1 + hi - lo + 1]:
        H.ichiyuhaigr[int(r[0])] = r[1]
    if S.mode45 == 1:
        last = int(pol.get("hihokensha.years.xend_file_last"))
        for r in _rows(P["ichisanxend"])[1:1 + last - S.starty + 1]:
            H.xend[hy.i(int(r[0]))] = int(r[1])
        H.xend[hy.i(last) + 1:] = H.xend[hy.i(last)]
    else:
        H.xend[:] = int(A["xend_default"])
    for r in _rows(P["cut_jisseki"])[:S.cut_jy - S.cnendo + 1]:
        H.cutritu[S.cy.i(int(r[0]))] = r[1]
    _read_part(P["part"][0], 1, H)
    if S.part >= 1:
        _read_part(P["part"][1], 2, H)
    if S.part == 2:
        _read_part(P["part"][2], 3, H)
    for seido in (4, 5, 6):
        _read_kyos(P["kyos"][seido], seido, S, H)
    return HihoInputs(pol, S, H, data_dir)
