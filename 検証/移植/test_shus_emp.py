# -*- coding: utf-8 -*-
"""
emp_shushi/shus.py・shus_calc.py と原本を突き合わせる
=====================================================
harness_shus.c が原本を
    init_gval → cntl → set_filenum → alfopen → flck → econ → rdfl →
    shus_init → init_premium → shus_smodel → shus_premium → shus_fukkjn →
    shus_calc0 → shus_calc8
まで通し、計算後の配列の生バイト列の CRC32 と、代表値を %a で吐く。
Python 移植版を同じ順序で走らせて1つずつ比べる。

**所得代替率そのもの**も突き合わせる。これが⑤の看板の数字。

前提: `STEPS=1234 検証/実行/run_pipeline.sh 3001` で⑤の入力ができていること。
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
REPO = os.path.dirname(os.path.dirname(HERE))
CSRC = os.path.join(REPO, "papers", "001365945", "プログラム", "厚生年金", "収支計算")

SYSTEMS = ("emp_shushi",)
select(*SYSTEMS)

# 経済前提の違いで、調整期間を解く経路の通り方が変わる。3本回して
# 1段目（年度を整数で探すループ）の回数を変えて突き合わせる。
#
#   3001  調整終了 2024年度 → 1段目 2回、割線法 0 回（反復に入らない）
#   3003  調整終了 2026年度 → 1段目 4回、割線法 1 回
#   3004  調整終了 2052年度 → 1段目 30回、割線法 1 回（最も重い経路）
#
# なお **2分法の枝（n>=14）は実データでは通らない**。割線法が1回で
# 収束してしまうため。ここは未検証のまま残る（README に明記）。
CASES = [
    dict(shisan="3001", econ="3001", waku="3001", yobi="000"),
    dict(shisan="3003", econ="3003", waku="3003", yobi="000"),
    dict(shisan="3004", econ="3004", waku="3004", yobi="000"),
]
CASE = CASES[0]

ARRAYS = """
E3dxb Cc Prema Premb
A Aiku An Aniku A60 A65 A70
Apart Aikupart Anpart Anikupart Np
W Kw Mkiso Mhirei
Escutrrh Escutrrt Tokutyo
""".split()


def suuri():
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        prefix = os.path.join(REPO, "work")
    return prefix.rstrip("/") + "/suuri/rev2024"


def inputs_ready(c=None):
    c = c or CASE
    need = [f"emp/rslt/u-rev/shus/shus.{c['shisan']}-{c['econ']}-{c['waku']}_kou",
            f"bas/data/KYOSHUTUKIN{c['shisan']}-{c['shisan']}"
            f"-{c['econ']}-{c['waku']}-{c['yobi']}",
            "emp/data/ez-arev/nof2024.csv"]
    return all(os.path.isfile(os.path.join(suuri(), p)) for p in need)


def find_cc():
    for cand in ("cc", "gcc", "clang"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            return cand
    return None


@pytest.fixture(scope="session")
def harness():
    """原本を UTF-8 に変換し、SYSPATH を実行領域に差し替えてビルドする。
    `検証/実行/run_pipeline.sh` のビルド前処理と同じ（原本には触らない）。"""
    if not os.path.isdir(CSRC):
        pytest.skip("原本のソースが無い（./fetch.sh で取得してください）")
    if not inputs_ready():
        pytest.skip("⑤の入力が無い"
                    "（STEPS=1234 検証/実行/run_pipeline.sh 3001 を先に実行）")
    cc = find_cc()
    if cc is None:
        pytest.skip("C コンパイラが無い")

    d = tempfile.mkdtemp(prefix="shus_emp_")
    # zlib があるか
    zt = os.path.join(d, "zt.c")
    with open(zt, "w") as f:
        f.write("#include <zlib.h>\nint main(){return (int)crc32(0L,0,0);}\n")
    if subprocess.run([cc, "-o", os.path.join(d, "zt"), zt, "-lz"],
                      capture_output=True).returncode != 0:
        pytest.skip("zlib（-lz）が無いので CRC32 比較ができない")

    build = os.path.join(d, "src")
    os.makedirs(build)
    for fn in os.listdir(CSRC):
        if not (fn.endswith(".c") or fn.endswith(".h")):
            continue
        with open(os.path.join(CSRC, fn), "rb") as f:
            raw = f.read()
        try:
            txt = raw.decode("euc_jp")
        except UnicodeDecodeError:
            txt = raw.decode("latin-1")
        with open(os.path.join(build, fn), "w", encoding="utf-8") as f:
            f.write(txt)

    seth = os.path.join(build, "set.h")
    s = open(seth, encoding="utf-8").read()
    s = s.replace('#define SYSPATH "/suuri/rev2024"',
                  f'#define SYSPATH "{suuri()}"')
    open(seth, "w", encoding="utf-8").write(s)

    # 長いパスで char flname[100] が溢れるので広げる（run_pipeline.sh と同じ）
    fopnc = os.path.join(build, "fopn.c")
    s = open(fopnc, encoding="utf-8").read()
    s = s.replace("char flname[100]", "char flname[1024]")
    open(fopnc, "w", encoding="utf-8").write(s)

    main_o = os.path.join(d, "main.o")
    r = subprocess.run([cc, "-O2", "-Dmain=orig_main", "-c",
                        os.path.join(build, "main.c"), "-I", build,
                        "-o", main_o], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"main.c のコンパイルに失敗:\n{r.stderr[:2000]}")

    exe = os.path.join(d, "harness")
    r = subprocess.run(
        [cc, "-O2", "-o", exe, os.path.join(HERE, "harness_shus.c"), main_o]
        + [os.path.join(build, f) for f in
           ("cntl.c", "fopn.c", "flck.c", "econ.c", "rdfl.c", "stdfun.c",
            "shus.c", "shus_calc.c")]
        + ["-I", build, "-lm", "-lz"],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:3000]}")
    return exe


def emp_stdin(shisan, econ, waku, yobi, kakudai=0, sigo=0, waku_m=None,
              houjou=0, tougou=0, yobi2="001", carry=1, dmacro=0):
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
    t0 = time.time()
    r = subprocess.run([harness], input=text.encode("ascii"),
                       capture_output=True, timeout=1800)
    el = time.time() - t0
    out = r.stdout.decode("latin-1")
    assert r.returncode == 0, (
        f"rc={r.returncode}\n{out[-3000:]}\n{r.stderr.decode('latin-1')[-2000:]}")
    crc, ints, dbls = {}, {}, {}
    for ln in out.splitlines():
        if ln[1:2] != " ":
            continue
        p = ln.split(" ")
        if p[0] == "c":
            crc[p[1]] = (int(p[2], 16), int(p[3]))
        elif p[0] == "i":
            ints[p[1]] = int(p[2])
        elif p[0] == "d":
            dbls[p[1]] = float.fromhex(p[2])
    return crc, ints, dbls, el, out


def run_py(text, rdfl_mod="rdfl_fast"):
    for m in ("main", "cntl", "econ", "fopn", "flck", "fcls", "rdfl",
              "rdfl_fast", "shus", "shus_calc", "glva", "stdfun", "cnum",
              "cfile", "cscan", "setconst"):
        sys.modules.pop(m, None)
    import glva
    import cntl as C
    import main as M
    import fopn
    import flck
    import econ as E
    import shus as S
    import shus_calc as SC
    from cscan import Scan

    glva.init_gval()
    sc = Scan(text)
    C.cntl(sc)
    M.set_filenum(sc)
    fopn.alfopen()
    flck.flck()
    E.econ()
    __import__(rdfl_mod).rdfl()

    G = glva.G
    t0 = time.time()
    S.shus_init()
    S.init_premium()
    SC.shus_smodel()
    S.shus_premium()
    S.shus_fukkjn()
    SC.shus_calc0()
    rc8 = -1
    if G.Fpset == 8:
        rc8 = SC.shus_calc8()
    if G.Fpset == 9:
        SC.shus_calc9()
    el = time.time() - t0

    for fp in list(G.ofp01_shushi) + [G.ofp_Tokutyo]:
        if fp is not None:
            fp.close()
    return G, rc8, el


def bits(x):
    return struct.pack(">d", float(x)).hex()


def _eval_expr(G, expr):
    """"Kw[Ke-STTY][0]" のような C の添字式を評価する。"""
    from setconst import ECSTY, ECXA, STTY
    env = {"STTY": STTY, "ECSTY": ECSTY, "ECXA": ECXA,
           "Ks": int(G.Ks), "Ke": int(G.Ke)}
    name, rest = expr.split("[", 1)
    idx = []
    for part in ("[" + rest).replace("]", "").split("[")[1:]:
        idx.append(eval(part, env))
    return getattr(G, name)[tuple(idx)]


@pytest.mark.parametrize("case", CASES,
                         ids=[c["shisan"] for c in CASES])
def test_shus_の計算が原本と一致(harness, case, tmp_path):
    if not inputs_ready(case):
        pytest.skip(f"{case['shisan']} の入力が無い"
                    f"（STEPS=1234 検証/実行/run_pipeline.sh {case['shisan']}）")
    text = emp_stdin(**case)
    crc_c, ints_c, dbls_c, t_c, cout = run_c(harness, text)

    # C が書いた 01shushi を退避（Python が同じ場所に上書きするので）
    for p in os.listdir(os.path.join(suuri(), "emp/rslt/ez_arev/shushi")):
        pass

    G, rc8, t_p = run_py(text)

    assert rc8 == ints_c["rc8"], (
        f"shus_calc8 の戻り値が違う: C={ints_c['rc8']} Python={rc8}")
    assert int(G.Ks) == ints_c["Ks"] and int(G.Ke) == ints_c["Ke"]

    mismatch = []
    total = 0
    for name in ARRAYS:
        assert name in crc_c, f"ハーネスが {name} を出していない"
        c_crc, c_size = crc_c[name]
        a = getattr(G, name)
        assert a.nbytes == c_size, (
            f"{name} のバイト数が違う: C={c_size} Python={a.nbytes}")
        p_crc = zlib.crc32(a.tobytes())
        total += a.nbytes
        if p_crc != c_crc:
            mismatch.append(f"{name} (C={c_crc:08x} Python={p_crc:08x}, "
                            f"{a.nbytes/1e6:.1f}MB)")

    # 代表値
    for expr, cval in sorted(dbls_c.items()):
        if expr == "shotoku_daitairitsu":
            continue
        pval = _eval_expr(G, expr)
        if bits(pval) != bits(cval):
            mismatch.append(f"{expr}: C={cval!r} Python={float(pval)!r}")

    # 所得代替率（看板の数字）
    from setconst import ECSTY, ECXA, STTY
    Ke = int(G.Ke)
    daitai = ((float(G.Mhirei[Ke - STTY, 0])
               * float(G.Escutrrh[Ke - ECSTY, 67 - ECXA])
               + float(G.Mkiso[Ke - STTY])
               * float(G.Escutrrt[Ke - ECSTY, 67 - ECXA]))
              / float(G.Kw[Ke - STTY, 0]) * 100.)
    c_daitai = dbls_c["shotoku_daitairitsu"]
    if bits(daitai) != bits(c_daitai):
        mismatch.append(f"所得代替率: C={c_daitai!r} Python={daitai!r}")

    assert not mismatch, ("原本と一致しない:\n  " + "\n  ".join(mismatch))

    # cout は latin-1 で読んだバイト列なので、探す側も同じ表現に直す
    needle = "反復計算".encode("utf-8").decode("latin-1")
    n_iter = cout.count(needle)
    print(f"\n  [{case['shisan']}] 所得代替率 {daitai!r}（C とビット一致）")
    print(f"  反復計算 {n_iter} 回")
    print(f"  配列 {len(ARRAYS)} 本 / {total/1e6:.0f}MB 一致")
    print(f"  C {t_c:.1f} 秒 / Python {t_p:.1f} 秒（shus 部分のみ）")
