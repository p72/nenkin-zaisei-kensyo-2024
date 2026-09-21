# -*- coding: utf-8 -*-
"""
rdfl_fast.py（Python最適版）が rdfl.py（忠実移植）とビット一致するか
====================================================================
最適化で結果が変わっていないことを守る番犬。忠実版と最適版を同じ入力で
走らせ、39配列すべての生バイト列を CRC32 で突き合わせる。

忠実版はさらに原本 C と突き合わせてある（`test_rdfl_emp.py`）ので、
ここが通れば最適版も原本とビット一致していることになる。

前提: `STEPS=1234 検証/実行/run_pipeline.sh 3001` で⑤の入力ができていること。
"""
import os
import sys
import time
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
REPO = os.path.dirname(os.path.dirname(HERE))
SYSTEMS = ("emp_shushi",)
select(*SYSTEMS)

CASE = ("3001", "3001", "3001", "000")

ARRAYS = """
Ap Apdum Ap65 Ap70 A Adum A60 A65 A70 Aiku Aikudum Aal
Apart Aikupart A60part A65part A70part An Aniku Anpart Anikupart
T4xtp D3bxtp Kfpbxtp Kofbxtp Kofte Kofkk
Kyosdx Kfkyosdx Tumazumi Kokusyushi Nofu Jyutaku
Kra Krb Scutrk1 Scutrrki Scutrrh Scutrrt
""".split()


def suuri():
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        prefix = os.path.join(REPO, "work")
    return prefix.rstrip("/") + "/suuri/rev2024"


def inputs_ready():
    s, e, w, y = CASE
    need = [f"emp/rslt/u-rev/shus/shus.{s}-{e}-{w}_kou",
            f"bas/data/KYOSHUTUKIN{s}-{s}-{e}-{w}-{y}",
            "emp/data/ez-arev/nof2024.csv"]
    return all(os.path.isfile(os.path.join(suuri(), p)) for p in need)


def run(mod):
    for m in ("main", "cntl", "econ", "fopn", "flck", "fcls", "rdfl",
              "rdfl_fast", "glva", "stdfun", "cnum", "cfile", "cscan",
              "setconst"):
        sys.modules.pop(m, None)
    import glva
    import cntl as C
    import main as M
    import fopn
    import flck
    import econ as E
    from cscan import Scan

    s, e, w, y = CASE
    text = f"0\n8\n0\n0\n0\n0\n0\n0\n{s}\n{e}\n{w}\n{y}\n"
    glva.init_gval()
    sc = Scan(text)
    C.cntl(sc)
    M.set_filenum(sc)
    fopn.alfopen()
    flck.flck()
    E.econ()

    R = __import__(mod)
    t0 = time.time()
    R.rdfl()
    el = time.time() - t0

    G = glva.G
    crc = {n: zlib.crc32(getattr(G, n).tobytes()) for n in ARRAYS}
    nbytes = sum(getattr(G, n).nbytes for n in ARRAYS)
    for fp in list(G.ofp01_shushi) + [G.ofp_Tokutyo]:
        if fp is not None:
            fp.close()
    return el, crc, int(G.Ks), int(G.Ke), nbytes


@pytest.mark.skipif(not inputs_ready(),
                    reason="⑤の入力が無い"
                           "（STEPS=1234 検証/実行/run_pipeline.sh 3001）")
def test_最適版が忠実版とビット一致():
    t_slow, c_slow, ks1, ke1, nb = run("rdfl")
    t_fast, c_fast, ks2, ke2, _ = run("rdfl_fast")

    assert (ks1, ke1) == (ks2, ke2), f"Ks/Ke が違う: {ks1}/{ke1} vs {ks2}/{ke2}"

    bad = [n for n in ARRAYS if c_slow[n] != c_fast[n]]
    assert not bad, (
        "最適版が忠実版と違う配列:\n  "
        + "\n  ".join(f"{n}: 忠実 {c_slow[n]:08x} / 最適 {c_fast[n]:08x}"
                      for n in bad))

    assert nb > 600e6, f"比較したのが {nb/1e6:.0f}MB しかない"
    # 遅くなっていたら最適化の意味が無い（環境差があるので緩めに見る）
    assert t_fast < t_slow, f"最適版が速くない: 忠実 {t_slow:.1f}s 最適 {t_fast:.1f}s"
    print(f"\n  忠実 {t_slow:.1f} 秒 / 最適 {t_fast:.1f} 秒 "
          f"({t_slow/t_fast:.1f} 倍速) / {nb/1e6:.0f}MB 一致")


def test_要素ごとのベクトル化はビット一致を壊さない():
    """最適化方針の根拠。要素ごとの演算をベクトル化しても、各要素にかかる
    演算の順序は変わらないので結果はビット単位で同じ。
    順序が変わって危ないのは総和などの**縮約**だけ。"""
    import struct

    import numpy as np

    NK, NX, NS, NU = 30, 40, 3, 4

    def setup():
        A = np.empty((NS, NU, NK, NX))
        B = np.empty((NS, NU, NK, NX))
        C = np.zeros((NS, NU, NK, NX))
        A[:] = 1.0 + 0.001 * np.arange(NX)
        B[:] = 0.99
        return A, B, C

    # スカラー（原本と同じ書き方）
    A, B, C = setup()
    for s in range(NS):
        for u in range(NU):
            for k in range(1, NK):
                for x in range(1, NX):
                    C[s, u, k, x] = (C[s, u, k - 1, x - 1] * B[s, u, k, x]
                                     + A[s, u, k, x] * 0.5)
    sca = C.copy()

    # ベクトル化（k は逐次のまま、s/u/x を一括）
    A, B, C = setup()
    for k in range(1, NK):
        C[:, :, k, 1:] = (C[:, :, k - 1, 0:NX - 1] * B[:, :, k, 1:]
                          + A[:, :, k, 1:] * 0.5)

    assert sca.tobytes() == C.tobytes(), "ベクトル化で結果が変わった"

    # 一方、**縮約**は順序で変わる（だから入れない）。
    # NumPy の np.sum は対数的に足す（pairwise summation）ので、原本のような
    # 先頭から順に足す加算とは結果が違う。0.1 を千回足すだけで差が出る。
    #   素朴  99.9999999999986
    #   np.sum 100.00000000000001
    v = np.full(1000, 0.1)
    naive = 0.0
    for e in v.tolist():
        naive += e
    assert struct.pack(">d", naive) != struct.pack(">d", float(np.sum(v))), (
        "np.sum と素朴な加算が一致してしまった。縮約の順序依存を示す例として"
        "選び直す必要がある（NumPy の実装が変わった可能性）")
    # 原本の順序を保つには、縮約はスカラーのまま回すか math.fsum を使わずに
    # 素朴に足す。ベクトル化してよいのは要素ごとの演算だけ。
