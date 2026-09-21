# -*- coding: utf-8 -*-
"""
emp_shushi/cntl.py と main.py(set_filenum) を原本と突き合わせる
===============================================================
harness_cntl.c が原本 cntl.c と main.c をそのままリンクして
init_gval() → cntl() → set_filenum() を呼び、決まったグローバル変数を
全部吐く。それを Python 移植版の結果と比べる。

int は完全一致、double は %a によるビット単位一致で見る。

標準入力は `検証/実行/run_pipeline.sh` の `emp_stdin()` と同じ形で組み立てる。
6つのレバーの組み合わせを回して、条件付きの追加入力
（Flg_Sigo==1 の Wcfile2、Touitu>=1 の Cutrfile5）まで通す。
"""
import math
import os
import struct
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
REPO = os.path.dirname(os.path.dirname(HERE))
CSRC = os.path.join(REPO, "papers", "001365945", "プログラム", "厚生年金", "収支計算")

SYSTEMS = ("emp_shushi",)
select(*SYSTEMS)


def find_cc():
    for cand in ("cc", "gcc", "clang"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            return cand
    return None


@pytest.fixture(scope="session")
def harness():
    if not os.path.isdir(CSRC):
        pytest.skip("原本のソースが無い（./fetch.sh で取得してください）")
    cc = find_cc()
    if cc is None:
        pytest.skip("C コンパイラが無い")

    d = tempfile.mkdtemp(prefix="cntl_emp_")
    exe = os.path.join(d, "harness")

    # main.c だけ -Dmain=orig_main を付けてコンパイルする（ハーネス側の
    # main() まで改名されないように分けている）。
    main_o = os.path.join(d, "main.o")
    r = subprocess.run(
        [cc, "-O0", "-Dmain=orig_main", "-c", os.path.join(CSRC, "main.c"),
         "-I", CSRC, "-o", main_o],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.fail(f"main.c のコンパイルに失敗:\n{r.stderr[:2000]}")

    r = subprocess.run(
        [cc, "-O0", "-o", exe,
         os.path.join(HERE, "harness_cntl.c"),
         main_o,
         os.path.join(CSRC, "cntl.c"),
         os.path.join(CSRC, "stdfun.c"),
         "-I", CSRC, "-lm"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")
    return exe


def emp_stdin(shisan="3001", econ="3001", waku="3001", yobi="000",
              kakudai=0, sigo=0, waku_m=None, houjou=0, tougou=0,
              yobi2="001", carry=1, dmacro=0):
    """run_pipeline.sh の emp_stdin() と同じ順序で標準入力を組む。"""
    out = ["0", "8", str(kakudai), str(sigo)]
    if sigo == 1:
        out.append(waku_m if waku_m is not None else waku)
    out += [str(houjou), str(tougou)]
    if tougou >= 1:
        out.append(yobi2)
    out += [str(1 - carry), str(dmacro)]
    out += [shisan, econ, waku, yobi]
    return "\n".join(out) + "\n"


def run_c(harness, text):
    """原本を EUC-JP のままビルドしているので、標準出力の案内文は EUC-JP で
    出てくる（`検証/実行/run_pipeline.sh` は iconv で UTF-8 に変換してから
    ビルドするため、本番のバイナリは UTF-8 を吐く）。ここで見たい dump 行は
    ASCII なので、バイト透過の latin-1 で読む。"""
    r = subprocess.run([harness], input=text.encode("ascii"),
                       capture_output=True, timeout=60)
    stdout = r.stdout.decode("latin-1")
    assert r.returncode == 0, (
        f"rc={r.returncode}\n{stdout[-2000:]}\n{r.stderr.decode('latin-1')}")
    out = {}
    for ln in stdout.splitlines():
        if not ln or ln[1:2] != " ":
            continue
        kind, name, val = ln.split(" ", 2)
        if kind == "i":
            out[name] = ("i", int(val))
        elif kind == "d":
            out[name] = ("d", float.fromhex(val))
        elif kind == "s":
            assert val.startswith("[") and val.endswith("]"), ln
            out[name] = ("s", val[1:-1])
    return out


def run_py(text):
    for m in ("main", "cntl", "econ", "fopn", "flck", "fcls",
              "glva", "stdfun", "cnum", "cfile", "cscan", "setconst"):
        sys.modules.pop(m, None)
    import glva
    import cntl as cntl_mod
    import main as main_mod
    from cscan import Scan

    glva.init_gval()
    scan = Scan(text)
    cntl_mod.cntl(scan)
    main_mod.set_filenum(scan)

    return glva.G, glva


def bits(x):
    return struct.pack(">d", float(x)).hex()


CASES = [
    dict(),                                                 # 通常試算
    dict(kakudai=1), dict(kakudai=4), dict(kakudai=5),      # 適用拡大
    dict(sigo=1, waku_m="3011"),                            # 45年化
    dict(houjou=1), dict(houjou=2), dict(houjou=3),         # 報酬上限
    dict(tougou=1, yobi2="002"),                            # 調整期間の一致
    dict(carry=0),                                          # キャリーオーバー廃止
    dict(dmacro=1),                                         # 名目下限撤廃
    # 組み合わせ
    dict(kakudai=2, sigo=1, waku_m="3012", houjou=2,
         tougou=1, yobi2="003", carry=0, dmacro=1),
    dict(shisan="3003", econ="3003", waku="3003", yobi="007", kakudai=3),
]


@pytest.mark.parametrize("kw", CASES, ids=[str(sorted(c.items())) for c in CASES])
def test_cntl_が原本と一致(harness, kw):
    text = emp_stdin(**kw)
    got_c = run_c(harness, text)
    G, glva = run_py(text)

    n = 0
    for name, (kind, cval) in sorted(got_c.items()):
        if name.startswith("sum_"):
            continue
        pval = getattr(G, name)
        if kind == "i":
            assert int(pval) == cval, f"{name}: C={cval} Python={pval}"
        elif kind == "d":
            assert bits(pval) == bits(cval), (
                f"{name}: C={cval!r} ({float(cval).hex()}) "
                f"Python={float(pval)!r} ({float(pval).hex()})")
        elif kind == "s":
            assert pval == cval, f"{name}: C={cval!r} Python={pval!r}"
        n += 1
    assert n >= 80, f"見た変数が {n} 個しかない"

    # init_gval() が 1.0 で埋めた配列の合計も突き合わせる
    import numpy as np
    sum_kra = float(np.sum(G.Kra) + np.sum(G.Krb))
    sum_tok = float(np.sum(G.Scutrrh) + np.sum(G.Scutrrt) + np.sum(G.Scutrrki)
                    + np.sum(G.Escutrrh) + np.sum(G.Escutrrt) + np.sum(G.Tokutyo))
    assert bits(sum_kra) == bits(got_c["sum_Kra_Krb"][1]), (
        f"init_gval の Kra/Krb: C={got_c['sum_Kra_Krb'][1]} Python={sum_kra}")
    assert bits(sum_tok) == bits(got_c["sum_Scutr_etc"][1]), (
        f"init_gval の Scutr 他: C={got_c['sum_Scutr_etc'][1]} Python={sum_tok}")


def test_不正な入力は原本と同じく落ちる(harness):
    """範囲外の値でエラー終了する箇所が一致しているか。"""
    bad = [
        dict(kakudai=6),      # Flg_Part > 5
        dict(houjou=4),       # Flg_Houjou > 3
        dict(tougou=2),       # Touitu > 1
    ]
    for kw in bad:
        text = emp_stdin(**kw)
        r = subprocess.run([harness], input=text.encode("ascii"),
                           capture_output=True, timeout=60)
        assert r.returncode != 0, f"C が落ちなかった: {kw}"

        with pytest.raises(SystemExit) as ei:
            run_py(text)
        assert ei.value.code == 1, f"Python の終了コードが違う: {kw}"
