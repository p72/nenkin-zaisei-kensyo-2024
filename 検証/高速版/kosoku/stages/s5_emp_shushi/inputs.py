# -*- coding: utf-8 -*-
"""⑤厚生年金収支計算の入力（移植版 `rdfl.c` `fopn.c` 相当）
==================================================================
⑤が読むのは 4 系統の受け渡しファイル。

    ② `shus.{N}-{E}-{W}_{kou,kok,ren,sig}`  制度ごとの被保険者数・報酬総額・
                                             年齢別の給付費（独自給付と経過的国庫）
    ④ `KYOSHUTUKIN…`  年齢別の基礎年金拠出金と国庫負担（年度末値・翌年度分）
    ④ `TUMATUMI…`     妻積の分配、`cuta…` 国年の累積調整率
    ③ `KOKUKAITE…`    定額系の改定率、② `kaiteb…` 比例部分の改定率
    ① `waku…-m`       毎年のスライド調整率、`nof2024.csv` 納付金・住宅融資

読み手の約束: **位置で切らず、ブロックの表題行と見出し行で置く**（`計画.md`
「軸の統一」）。`shus.*` は 44 万行あるが、⑤が使うのは制度計・受給者計
（s=0, ui=0）の年齢別ブロックだけなので、表題で選んで読む。

年齢の軸は `AGES`（0〜120）。② ④ の年齢別の値は 63〜115 歳にだけ入る。
⑤の港は 67 歳未満を 66 歳に寄せて集約する（`shus.c:77`）。これは
`collapse_below_67` で明示する。

港: emp_shushi/rdfl_fast.py:rdfl_u_sys, rdfl_kyos, rdfl_sien, rdfl_cut
仕様: §12.4（中間ファイル）、§14（データフロー）
"""
from dataclasses import dataclass, field

import numpy as np

from ...axis import YEARS, AGES
from ...io_port import lines_of, read_year_rows, read_year_age_table, read_waku_m

__all__ = ["kokusyushi_from_kiso", "SYSTEMS", "NSYS", "AGE_LO", "AGE_HI", "KOFU", "ShusIn", "read_shus",
           "Kyos", "read_kyoshutukin", "kyos_from_kiso", "read_tumatumi",
           "read_nofu", "read_kaite", "fill_under_67", "collapse_below_67",
           "read_cuta_kiso", "read_scutrk1"]

SYSTEMS = ("kou", "kok", "ren", "sig")       # 第1号厚年・国共済・地共済・私学
NSYS = len(SYSTEMS)
AGE_LO, AGE_HI = 63, 115                     # 受け渡しの年齢の範囲
KOFU = "kofu"                                # 第3種被保険者（坑内員・船員）の保険料率の名前

# ④の KYOSHUTUKIN の制度番号（`s4_kiso_nenkin/output.py:write_kyoshutukin`）→ ⑤の制度
_KYOS_SEIDO = {0: 0, 1: 1, 4: 2, 5: 3}
# ④の NS（0 国年, 1 厚年, 2 国共, 3 地共, 4 私学）→ ⑤の制度
KISO_NS_OF = (1, 2, 3, 4)


def _port_years(labels):
    """港の年度ラベル（西暦 − 2000）の配列 → 軸の添字（範囲外は落とす）。"""
    return YEARS.i(np.asarray(labels, dtype=np.int64) + YEARS.first)


# ---------------------------------------------------------------- ② shus.*

@dataclass
class ShusIn:
    """②が制度ごとに渡す系列。年度は `YEARS`、年齢は `AGES`。

    `ap[s, y]`: 被保険者数（s = 0 計, 1 男, 2 女, 3 第3種）。港どおり 70 歳以上
    （`Ap70`）を引いてある。`a` 総報酬総額、`aiku` 育児等の報酬、`a60/a65/a70`
    年齢区分の報酬。`part[y]`: 適用拡大の年度だけ足す分（`PARTHOU`）。
    `t4[s, i, y]`: 被保険者・受給者数の年齢計（i = 0 計, 1 老齢, 2 老在, 3 通老,
    4 通在, 5 障害, 6 遺族）。年齢別の給付費（63〜115 歳）:
    `hirei` 比例、`teigaku` 定額系、`kakyu` 加給、`kokko_hirei/teigaku/kasaage`
    経過的国庫負担（比例・定額・かさ上げ）。
    """
    ks: int
    ke: int
    ap: np.ndarray
    ap65: np.ndarray
    a: np.ndarray
    a60: np.ndarray
    a65: np.ndarray
    a70: np.ndarray
    aiku: np.ndarray
    t4: np.ndarray
    hirei: np.ndarray
    teigaku: np.ndarray
    kakyu: np.ndarray
    kokko_hirei: np.ndarray
    kokko_teigaku: np.ndarray
    kokko_kasaage: np.ndarray
    part: dict = field(default_factory=dict)
    econ_check: dict = field(default_factory=dict)   # {年度: (Ri, H)} ②が使った経済前提


def _is_data(line):
    return line[:1].isdigit()


def _rows(lines, start):
    """`start` から続く数値行を (n, ncol) の float 配列に。行の先頭列は年度ラベル。"""
    j = start
    n = len(lines)
    while j < n and _is_data(lines[j]):
        j += 1
    rows = lines[start:j]
    if not rows:
        return np.empty((0, 1)), j
    width = min(len([x for x in r.split(b",") if x.strip() != b""]) for r in rows)
    vals = [[float(x) for x in r.split(b",")[:width]] for r in rows]
    return np.array(vals, dtype=np.float64), j


def _blocks(lines, start):
    """`start` 以降の「表題行・見出し行・数値行…」を順に返す。"""
    j = start
    n = len(lines)
    while j < n:
        if _is_data(lines[j]) or lines[j].strip() == b"":
            j += 1
            continue
        title = lines[j].decode("latin-1").strip()
        if j + 1 >= n:
            return
        header = [x.strip() for x in lines[j + 1].decode("latin-1").split(",")]
        k = j + 2
        if k < n and _is_data(lines[k]):
            yield title, header, k
            # 数値行の終わりまで飛ばす
            while k < n and _is_data(lines[k]):
                k += 1
            j = k
        else:
            j += 1


def _groups(title, header):
    """表題行 `,AP,,,,APDUM` と見出し `K,S=0,…` から {名前: 先頭列} を作る。"""
    names = [x.strip() for x in title.split(",")]
    out = {}
    for i, nm in enumerate(names):
        if nm:
            out[nm] = i
    if not out:
        out[title.strip()] = 1
    return out


def read_shus(path, part_years=()):
    """`shus.*` を読む。`part_years`: 適用拡大の年度（`PARTHOU` の行を持つ年度）。"""
    raw = open(path, "rb").read().split(b"\n")
    try:
        start = raw.index(b"#99-0000-0000") + 1
    except ValueError:
        start = next(i for i, l in enumerate(raw) if l.startswith(b"#99"))  + 1
    ks, ke = (YEARS.first + int(x) for x in raw[start].split(b",")[:2])     # 港のラベル → 西暦
    Y, X = YEARS.n, AGES.n
    ap = np.zeros((4, Y)); ap65 = np.zeros((4, Y)); ap70 = np.zeros((4, Y))
    a = np.zeros((4, Y)); a60 = np.zeros((4, Y)); a65 = np.zeros((4, Y)); a70 = np.zeros((4, Y))
    aiku = np.zeros((4, Y))
    t4 = np.zeros((4, 7, Y))
    ben = {k: np.zeros((Y, X)) for k in ("hirei", "teigaku", "kakyu", "kokko_hirei",
                                         "kokko_teigaku", "kokko_kasaage")}
    part = {}
    econ_check = {}
    first = True
    for title, header, k in _blocks(raw, start + 1):
        head = title.split(",")[0]
        if first:                                     # 経済前提の整合表（年度, Ri, H）
            first = False
            arr, _ = _rows(raw, k)
            for r in arr:
                econ_check[int(r[0]) + YEARS.first] = (float(r[1]), float(r[2]))
            continue
        if head == "" and "AP" in title.split(","):
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            g = _groups(title, header)
            ap[:, ys] = arr[:, g["AP"]:g["AP"] + 4].T
            continue
        if head == "" and "AP65" in title.split(","):
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            g = _groups(title, header)
            ap65[:, ys] = arr[:, g["AP65"]:g["AP65"] + 4].T
            ap70[:, ys] = arr[:, g["AP70"]:g["AP70"] + 4].T
            continue
        if head == "" and "A" in title.split(","):
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            g = _groups(title, header)
            a[:, ys] = arr[:, g["A"]:g["A"] + 4].T
            a60[:, ys] = arr[:, g["A60"]:g["A60"] + 4].T
            a65[:, ys] = arr[:, g["A65"]:g["A65"] + 4].T
            a70[:, ys] = arr[:, g["A70"]:g["A70"] + 4].T
            continue
        if head == "AIKU":
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            aiku[:, ys] = arr[:, 1:5].T
            continue
        if head == "AAL":
            continue
        if head == "PARTHOU":
            arr, _ = _rows(raw, k)
            for r in arr:
                y = int(r[0]) + YEARS.first
                part[y] = dict(a=r[1:5].copy(), aiku=r[5:9].copy(), a60=r[9:13].copy(),
                               a65=r[13:17].copy(), a70=r[17:21].copy())
            continue
        if head == "D3X(k;s;i;0)":                     # 被保険者・受給者数（年齢 x・性 s）
            _, x, s = title.split(",")
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            v = arr[:, 1:8].T                          # (7, n)
            t4[int(s), :, ys] += v.T
            t4[0, :, ys] += v.T
            continue
        if head == "D3X":                              # 年齢別の給付費（x, s, ui）
            _, x, s, ui = title.split(",")
            if int(s) != 0 or int(ui) != 0:
                continue
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            xi = AGES.i(int(x))
            col = {nm: i for i, nm in enumerate(header)}
            ben["kokko_kasaage"][ys, xi] = arr[:, col["J=25"]]
            ben["hirei"][ys, xi] = arr[:, col["J=7"]]
            ben["teigaku"][ys, xi] = (arr[:, col["J=8"]] + arr[:, col["J=9"]]
                                      + arr[:, col["J=11"]] + arr[:, col["J=12"]])
            ben["kakyu"][ys, xi] = arr[:, col["J=10"]]
            continue
        if head == "KFPRX":                            # 経過的国庫負担（x, ui）
            _, x, ui = title.split(",")
            if int(ui) != 0:
                continue
            arr, _ = _rows(raw, k)
            ys = _port_years(arr[:, 0])
            xi = AGES.i(int(x))
            col = {nm: i for i, nm in enumerate(header)}
            ben["kokko_hirei"][ys, xi] = arr[:, col["(S-J)=0-1"]]
            ben["kokko_teigaku"][ys, xi] = arr[:, col["0-2"]]
            continue
    ap = ap - ap70                                     # 港: Ap から Ap70 を引く（rdfl.c）
    return ShusIn(ks, ke, ap, ap65, a, a60, a65, a70, aiku, t4,
                  ben["hirei"], ben["teigaku"], ben["kakyu"],
                  ben["kokko_hirei"], ben["kokko_teigaku"], ben["kokko_kasaage"], part, econ_check)


# ---------------------------------------------------------------- ④ KYOSHUTUKIN

@dataclass
class Kyos:
    """④が渡す年齢別の拠出金と国庫負担。`[形態 2, 制度 NSYS, 2, YEARS.n, AGES.n]`。

    3つ目の軸: 0 = 前年度末の翌年度分（行の年度 y に y−1 の `_P` を置く。港の
    `Kyosdx[…, 0]`）、1 = 当年度末（`Kyosdx[…, 1]`）。形態: 0 基本, 1 加給。
    """
    kyos: np.ndarray
    kokko: np.ndarray = None
    extra: np.ndarray = None   # 調整期間の一致（tougou）のときだけ: 国年（ss=7）＋特別国庫（ss=8）の
                               # [形態 2, 2（0 拠出金 / 1 国庫）, 2, YEARS.n, AGES.n]。無ければ None


def read_kyoshutukin(path):
    Y, X = YEARS.n, AGES.n
    kyos = np.zeros((2, NSYS, 2, Y, X))
    kokko = np.zeros((2, NSYS, 2, Y, X))
    kt = None
    xs = AGES.s(AGE_LO, AGE_HI)
    for l in lines_of(path):
        if l.startswith("shikyu_keitai:"):
            kt = int(l.split(":")[1]) - 1
            continue
        f = l.split(",")
        if kt is None or len(f) < 4 or not f[0].strip().isdigit():
            continue
        ss = int(f[1])
        if ss not in _KYOS_SEIDO:
            continue
        s = _KYOS_SEIDO[ss]
        kubun = int(f[2])
        y = YEARS.i(int(f[0]) + YEARS.first)
        vals = np.array([float(x) for x in f[4:4 + (AGE_HI - AGE_LO + 1)]])
        if kubun == 1:
            kyos[kt, s, 0, y, xs] = vals
        elif kubun == 2:
            kyos[kt, s, 1, y, xs] = vals
        elif kubun == 3:
            kokko[kt, s, 0, y, xs] = vals
        elif kubun == 4:
            kokko[kt, s, 1, y, xs] = vals
    return Kyos(kyos, kokko)


def kyos_from_kiso(kyo, tokubetu=None):
    """高速版④の `Kyoshutu`（調整前）から。港の並び（年齢 0 = 計、形態 0 = 計）を外す。
    `tokubetu=(P, nm)`（④の `KisoOut.kyoshutukin["tokubetu_nendomatu_P"/"tokubetu_nendomatu"]`）を渡すと
    調整期間の一致のぶん（国年 ss=7 と特別国庫 ss=8。港の `KYOSHUTUKIN` の追加ブロック）も `extra` に置く。"""
    Y, X = YEARS.n, AGES.n
    kyos = np.zeros((2, NSYS, 2, Y, X))
    kokko = np.zeros((2, NSYS, 2, Y, X))
    xs = AGES.s(AGE_LO, AGE_HI)
    for s, ns in enumerate(KISO_NS_OF):
        for kt in range(2):
            kyos[kt, s, 0, 1:, xs] = kyo.kyoshutukin_P[ns, :-1, 1:, kt + 1]
            kyos[kt, s, 1, :, xs] = kyo.kyoshutukin_nm[ns, :, 1:, kt + 1]
            kokko[kt, s, 0, 1:, xs] = kyo.kyoshutukin_kokko_P[ns, :-1, 1:, kt + 1]
            kokko[kt, s, 1, :, xs] = kyo.kyoshutukin_kokko_nm[ns, :, 1:, kt + 1]
    extra = None
    if tokubetu is not None:
        tP, tnm = tokubetu                              # (YEARS.n, NA+1, 3): 年齢 0 = 計、形態 0 = 計
        extra = np.zeros((2, 2, 2, Y, X))
        for kt in range(2):
            # ss=7 国年の拠出金・国庫（④の NS=0）＋ ss=8 特別国庫（拠出金の欄も国庫の欄も同じ値）
            extra[kt, 0, 0, 1:, xs] = kyo.kyoshutukin_P[0, :-1, 1:, kt + 1] + tP[:-1, 1:, kt + 1]
            extra[kt, 0, 1, :, xs] = kyo.kyoshutukin_nm[0, :, 1:, kt + 1] + tnm[:, 1:, kt + 1]
            extra[kt, 1, 0, 1:, xs] = kyo.kyoshutukin_kokko_P[0, :-1, 1:, kt + 1] + tP[:-1, 1:, kt + 1]
            extra[kt, 1, 1, :, xs] = kyo.kyoshutukin_kokko_nm[0, :, 1:, kt + 1] + tnm[:, 1:, kt + 1]
    return Kyos(kyos, kokko, extra)


def kokusyushi_from_kiso(kiso):
    """調整期間の一致で⑤が読む国年の収支項目（港の `provide` ファイル → `Kokusyushi[10, YEARS.n]`）。
    ④の調整前の値（港は `printout(0)` で書く）。
      0 保険料収入（国年 ＋ 付加 ＋ こども子育て繰入）  1 一時金付加分国庫（1/4）  2 付加年金国庫（1/4）
      3 その他収入（融資債権）  4 その他収入（妻積）  5 一時金納付分  6 一時金付加分  7 付加年金
      8 業務勘定への繰入  9 新法寡婦年金（年度末）"""
    D = kiso.D
    K = np.zeros((10, YEARS.n))
    K[0] = D.hokenryou_y + D.fuka_hokenryou_y + D.kodomo_noufukin
    K[1] = D.ichijikin[:, 1] / 4.
    K[2] = D.fuka_sum / 4.
    K[3] = D.yuushi
    K[4] = kiso.tumatumi[0]
    K[5] = D.ichijikin[:, 0]
    K[6] = D.ichijikin[:, 1]
    K[7] = D.fuka_sum
    K[8] = D.fukushi
    K[9] = D.kafu_nm[:, 0]
    return K


# ---------------------------------------------------------------- その他

def read_tumatumi(path):
    """④ `TUMATUMI…csv` → (NSYS, YEARS.n)。列 2〜5 = 厚年・国共・地共・私学。"""
    out = np.zeros((NSYS, YEARS.n))
    for y, v in read_year_rows(path, YEARS.first).items():
        if YEARS.contains(y) and len(v) >= 5:
            out[:, YEARS.i(y)] = v[1:5]
    return out


def read_nofu(path):
    """`nof2024.csv`（年度, 納付金, 住宅融資債権）→ (納付金[YEARS.n], 住宅[YEARS.n])。"""
    nofu = YEARS.zeros()
    jyutaku = YEARS.zeros()
    for y, v in read_year_rows(path, YEARS.first).items():
        if YEARS.contains(y) and len(v) >= 2:
            nofu[YEARS.i(y)] = v[0]
            jyutaku[YEARS.i(y)] = v[1]
    return nofu, jyutaku


def fill_under_67(k):
    """改定率の表（67〜115 歳）を 67 歳未満に 67 歳の値で埋め、表に無い年度は 1。"""
    k = k.copy()
    empty = ~k[:, AGES.i(67):].any(axis=1)
    k[empty] = 1.
    k[:, :AGES.i(67)] = k[:, AGES.i(67)][:, None]
    return k


def read_kaite(path):
    """`kaiteb…` / `KOKUKAITE…`（年度−2000, 67歳, …, 115歳）→ (YEARS.n, AGES.n)。"""
    return fill_under_67(read_year_age_table(path, YEARS.first, first_age=67))


def read_cuta_kiso(path):
    """④ `cuta…`（年度−2000, 63歳, …, 115歳）→ (YEARS.n, AGES.n)。表に無い所は 1。"""
    t = read_year_age_table(path, YEARS.first, first_age=AGE_LO)
    out = np.ones_like(t)
    has = t[:, AGES.i(AGE_LO):AGES.i(AGE_HI) + 1].any(axis=1)
    out[has, AGES.i(AGE_LO):AGES.i(AGE_HI) + 1] = t[has, AGES.i(AGE_LO):AGES.i(AGE_HI) + 1]
    return out


def read_scutrk1(path):
    """① `waku…-m.csv`（西暦, 調整率）→ (YEARS.n,)。"""
    return read_waku_m(path)


def collapse_below_67(a):
    """67 歳未満を 66 歳に足し込む（港 `shus.c:77` の `if(x<67) dx=66`）。最後の軸が年齢。"""
    out = a.copy()
    lo, x66 = AGES.i(AGE_LO), AGES.i(66)
    out[..., x66] = a[..., lo:x66 + 1].sum(axis=-1)
    out[..., lo:x66] = 0.
    return out
