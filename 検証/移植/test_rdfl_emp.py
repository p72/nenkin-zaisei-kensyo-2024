# -*- coding: utf-8 -*-
"""
emp_shushi/rdfl.py と原本 rdfl.c を突き合わせる
===============================================
harness_rdfl.c が原本を init_gval → cntl → set_filenum → alfopen → flck →
econ → rdfl まで通し、rdfl が埋めた配列の**生バイト列の CRC32** を吐く。
NumPy の float64 配列は C の double 配列と同じメモリ配置なので、Python 側の
`zlib.crc32(arr.tobytes())` と厳密に一致する。

配列は合計 628MB あるので全要素を %a で出すのは無理。CRC32 は1ビットの
違いでも（ほぼ確実に）変わるので、ビット一致の判定に使える。合わなかった
ときの切り分け用に、代表要素を %a でも比べる。

あわせて `flck()` が書いた 01shushi のヘッダ部分を**バイト単位で**比較する。
ここは入力（EUC-JP）由来のバイト列とソース（UTF-8）由来の文字列が
1つのファイルに混在する場所なので、cfile.py のバイト透過が効いているかの
検査になる。

前提: `検証/実行/run_pipeline.sh` で①〜④まで走らせて⑤の入力が
できていること（`STEPS=1234 検証/実行/run_pipeline.sh 3001`）。
無ければ skip する。
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
REPO = os.path.dirname(os.path.dirname(HERE))
CSRC = os.path.join(REPO, "papers", "001365945", "プログラム", "厚生年金", "収支計算")
PATCH = os.path.join(REPO, "検証", "実行", "patches", "glibc-portability.patch")

SYSTEMS = ("emp_shushi",)
select(*SYSTEMS)

CASE = dict(shisan="3001", econ="3001", waku="3001", yobi="000")

# ハーネスが出す配列（CRC32 で比べるもの）
ARRAYS = """
Ap Apdum Ap65 Ap70 A Adum A60 A65 A70 Aiku Aikudum Aal
Apart Aikupart A60part A65part A70part An Aniku Anpart Anikupart
T4xtp D3bxtp Kfpbxtp Kofbxtp Kofte Kofkk
Kyosdx Kfkyosdx Tumazumi Kokusyushi Nofu Jyutaku
Kra Krb Scutrk1 Scutrrki Scutrrh Scutrrt
Ri H Ci Ri2 HCdum Id_Hhd Id_Cid Id_Cid_2
""".split()


def suuri():
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        prefix = os.path.join(REPO, "work")
    return prefix.rstrip("/") + "/suuri/rev2024"


def inputs_ready():
    """①〜④の出力が揃っているか。"""
    need = [
        f"emp/rslt/u-rev/shus/shus.{CASE['shisan']}-{CASE['econ']}"
        f"-{CASE['waku']}_kou",
        f"bas/data/KYOSHUTUKIN{CASE['shisan']}-{CASE['shisan']}"
        f"-{CASE['econ']}-{CASE['waku']}-{CASE['yobi']}",
        "emp/data/ez-arev/nof2024.csv",
    ]
    return all(os.path.isfile(os.path.join(suuri(), p)) for p in need)


def find_cc():
    for cand in ("cc", "gcc", "clang"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            return cand
    return None


def has_zlib(cc, d):
    src = os.path.join(d, "zt.c")
    with open(src, "w") as f:
        f.write("#include <zlib.h>\nint main(){return (int)crc32(0L,0,0);}\n")
    r = subprocess.run([cc, "-o", os.path.join(d, "zt"), src, "-lz"],
                       capture_output=True, text=True)
    return r.returncode == 0


@pytest.fixture(scope="session")
def harness():
    """原本を UTF-8 に変換し、SYSPATH を実行領域に差し替えてビルドする。

    `検証/実行/run_pipeline.sh` がビルド前にやっているのと同じ処理
    （iconv → パッチ → SYSPATH の書き換え）。原本には触らない。
    """
    if not os.path.isdir(CSRC):
        pytest.skip("原本のソースが無い（./fetch.sh で取得してください）")
    if not inputs_ready():
        pytest.skip("⑤の入力が無い"
                    "（STEPS=1234 検証/実行/run_pipeline.sh 3001 を先に実行）")
    cc = find_cc()
    if cc is None:
        pytest.skip("C コンパイラが無い")

    d = tempfile.mkdtemp(prefix="rdfl_emp_")
    if not has_zlib(cc, d):
        pytest.skip("zlib（-lz）が無いので CRC32 比較ができない")

    # ---- iconv で UTF-8 に ----
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

    # ---- SYSPATH を実行領域に差し替え（run_pipeline.sh と同じ） ----
    seth = os.path.join(build, "set.h")
    with open(seth, encoding="utf-8") as f:
        s = f.read()
    s = s.replace('#define SYSPATH "/suuri/rev2024"',
                  f'#define SYSPATH "{suuri()}"')
    with open(seth, "w", encoding="utf-8") as f:
        f.write(s)
    assert suuri() in open(seth, encoding="utf-8").read(), "SYSPATH の差し替え失敗"

    # ---- ファイル名バッファを広げる（run_pipeline.sh と同じ） ----
    # 原本は SYSPATH が "/suuri/rev2024"（14文字）である前提の寸法で、
    # fopn.c の char flname[100] は長いプレフィックスを付けると溢れる。
    # glibc の stack protector が
    #   *** stack smashing detected ***
    # で落とす。原本のままなら起きないので、差し替えたときだけ広げる。
    fopnc = os.path.join(build, "fopn.c")
    with open(fopnc, encoding="utf-8") as f:
        s = f.read()
    assert "char flname[100]" in s, "fopn.c の flname[100] が見つからない"
    s = s.replace("char flname[100]", "char flname[1024]")
    with open(fopnc, "w", encoding="utf-8") as f:
        f.write(s)

    # ---- main.c だけ -Dmain=orig_main で ----
    main_o = os.path.join(d, "main.o")
    r = subprocess.run(
        [cc, "-O0", "-Dmain=orig_main", "-c", os.path.join(build, "main.c"),
         "-I", build, "-o", main_o],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"main.c のコンパイルに失敗:\n{r.stderr[:2000]}")

    exe = os.path.join(d, "harness")
    r = subprocess.run(
        [cc, "-O0", "-o", exe, os.path.join(HERE, "harness_rdfl.c"), main_o]
        + [os.path.join(build, f) for f in
           ("cntl.c", "fopn.c", "flck.c", "econ.c", "rdfl.c", "stdfun.c")]
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


def shushi_paths():
    """flck() が書く 01shushi の 5 本と Tokutyo。"""
    c = CASE
    base = os.path.join(suuri(), "emp/rslt/ez_arev/shushi")
    names = []
    for ps in ("tou", "kou", "kok", "ren", "sig"):
        names.append(os.path.join(
            base, f"01shushi.{c['shisan']}-{c['shisan']}-{c['econ']}"
                  f"-{c['waku']}-1120-{c['yobi']}e_08{ps}.csv"))
    return names


def run_c(harness, text):
    r = subprocess.run([harness], input=text.encode("ascii"),
                       capture_output=True, timeout=900)
    stdout = r.stdout.decode("latin-1")
    assert r.returncode == 0, (
        f"rc={r.returncode}\n{stdout[-3000:]}\n{r.stderr.decode('latin-1')[-2000:]}")
    crc, ints, dbls = {}, {}, {}
    for ln in stdout.splitlines():
        if ln[1:2] != " ":
            continue
        parts = ln.split(" ")
        if parts[0] == "c":
            crc[parts[1]] = (int(parts[2], 16), int(parts[3]))
        elif parts[0] == "i":
            ints[parts[1]] = int(parts[2])
        elif parts[0] == "d":
            dbls[parts[1]] = float.fromhex(parts[2])
    return crc, ints, dbls


def run_py(text):
    for m in ("main", "cntl", "econ", "fopn", "flck", "fcls", "rdfl",
              "glva", "stdfun", "cnum", "cfile", "cscan", "setconst"):
        sys.modules.pop(m, None)
    import glva
    import cntl as cntl_mod
    import main as main_mod
    import fopn
    import flck
    import econ as econ_mod
    import rdfl as rdfl_mod
    from cscan import Scan

    glva.init_gval()
    scan = Scan(text)
    cntl_mod.cntl(scan)
    main_mod.set_filenum(scan)
    fopn.alfopen()
    flck.flck()
    econ_mod.econ()
    rdfl_mod.rdfl()

    G = glva.G
    # flck が書いたものを確定させる
    for fp in list(G.ofp01_shushi) + [G.ofp_Tokutyo]:
        if fp is not None:
            fp.close()
    return G


def bits(x):
    return struct.pack(">d", float(x)).hex()


def test_rdfl_が原本と一致(harness, tmp_path):
    text = emp_stdin(**CASE)

    # ---- C を先に走らせ、flck の出力を退避する ----
    crc_c, ints_c, dbls_c = run_c(harness, text)
    saved = {}
    for p in shushi_paths():
        if os.path.isfile(p):
            q = str(tmp_path / os.path.basename(p))
            shutil.copy2(p, q)
            saved[p] = q

    # ---- Python を走らせる（同じ場所に上書きする） ----
    G = run_py(text)

    # ---- Ks / Ke ----
    assert int(G.Ks) == ints_c["Ks"], f"Ks: C={ints_c['Ks']} Python={G.Ks}"
    assert int(G.Ke) == ints_c["Ke"], f"Ke: C={ints_c['Ke']} Python={G.Ke}"

    # ---- 配列の生バイト列の CRC32 ----
    mismatch = []
    total_bytes = 0
    for name in ARRAYS:
        assert name in crc_c, f"ハーネスが {name} を出していない"
        c_crc, c_size = crc_c[name]
        a = getattr(G, name)
        assert a.nbytes == c_size, (
            f"{name} のバイト数が違う: C={c_size} Python={a.nbytes}")
        p_crc = zlib.crc32(a.tobytes())
        total_bytes += a.nbytes
        if p_crc != c_crc:
            mismatch.append(f"{name} (C={c_crc:08x} Python={p_crc:08x}, "
                            f"{a.nbytes/1e6:.1f}MB)")

    # ---- 代表要素（切り分け用。CRC が合えばここも合う） ----
    for expr, cval in sorted(dbls_c.items()):
        pval = _eval_expr(G, expr)
        if bits(pval) != bits(cval):
            mismatch.append(f"{expr}: C={cval!r} Python={float(pval)!r}")

    assert not mismatch, ("原本と一致しない:\n  " + "\n  ".join(mismatch)
                          + f"\n（比較したのは {len(ARRAYS)} 配列 / "
                            f"{total_bytes/1e6:.0f}MB）")

    assert total_bytes > 600e6, f"比較したのが {total_bytes/1e6:.0f}MB しかない"


def _eval_expr(G, expr):
    """"Ap[1][0][22-STTY]" のような C の添字式を評価する。"""
    from setconst import ECSTY, ECXA, STTY
    name, rest = expr.split("[", 1)
    idx = []
    for part in ("[" + rest).replace("]", "").split("[")[1:]:
        idx.append(eval(part, {"STTY": STTY, "ECSTY": ECSTY, "ECXA": ECXA}))
    return getattr(G, name)[tuple(idx)]


def test_flck_の出力がバイト一致(harness, tmp_path):
    """flck() が書いた 01shushi のヘッダ部分を byte 比較する。

    入力（EUC-JP）由来のバイト列と、ソース（UTF-8）由来の「予備:」が
    1つのファイルに混在する場所。cfile.py のバイト透過が効いているかを見る。
    """
    text = emp_stdin(**CASE)

    run_c(harness, text)
    saved = {}
    for p in shushi_paths():
        assert os.path.isfile(p), f"C がこのファイルを作っていない: {p}"
        q = str(tmp_path / ("c_" + os.path.basename(p)))
        shutil.copy2(p, q)
        saved[p] = q

    run_py(text)

    for p, q in saved.items():
        with open(q, "rb") as f:
            cb = f.read()
        with open(p, "rb") as f:
            pb = f.read()
        assert cb == pb, (
            f"{os.path.basename(p)} のバイト列が違う\n"
            f"  C     {len(cb)}B {cb[:200]!r}\n"
            f"  Python {len(pb)}B {pb[:200]!r}")
        assert len(cb) > 0, f"{os.path.basename(p)} が空"
