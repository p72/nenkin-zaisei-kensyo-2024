# -*- coding: utf-8 -*-
"""
⑤を丸ごと C と Python で走らせ、出力ファイルをバイト単位で比較する
==================================================================
これが⑤の移植の最終確認。部品ごとの照合（`test_*_emp.py`）ではなく、
**原本のバイナリと移植版を同じ入力で走らせて、出てきたファイルを
1バイトずつ比べる**。

比較するのは 14 本（約 690MB）。

    01shushi.*_08{tou,kou,kok,ren,sig}.csv   制度別の収支見通し  各 1MB
    03summary.*_08sum.csv                    所得代替率のサマリ   0.5MB
    90nenbe.*_08{tou,kou,kok,ren,sig}.csv    年齢別の給付費     各 137MB
    cuta-*.csv / cutb-*.csv                  次回に渡すカット率   各 0.13MB
    Tokutyo.*.csv                            特別調整率          0.1MB

`90nenbe` は 5 本で 684MB あるので、SHA256 で比べる（内容を2重に持たない）。
小さい 9 本は中身も退避して、違ったときに最初の差分行を出せるようにする。

前提
----
- `検証/実行/run_pipeline.sh` で①〜④まで走らせて⑤の入力ができていること
- 原本のバイナリ `$SUURI/emp/exec/asys20` が建っていること
  （`run_pipeline.sh` がビルドする）

時間がかかる（C 約20秒＋Python 約3分）ので `slow` を付けてある。
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

CASE = dict(shisan="3001", econ="3001", waku="3001", yobi="000")


def suuri():
    prefix = os.environ.get("SUURI_PREFIX")
    if prefix is None:
        prefix = os.path.join(REPO, "work")
    return prefix.rstrip("/") + "/suuri/rev2024"


def out_paths(c=CASE):
    """⑤が書く 14 本。(パス, 小さいか) の組で返す。"""
    su = suuri()
    s, e, w, y = c["shisan"], c["econ"], c["waku"], c["yobi"]
    stem = f"{s}-{s}-{e}-{w}-1120-{y}"
    sh = os.path.join(su, "emp/rslt/ez_arev/shushi")
    cu = os.path.join(su, "emp/rslt/ez_arev/cutr")
    out = []
    for ps in ("tou", "kou", "kok", "ren", "sig"):
        out.append((os.path.join(sh, f"01shushi.{stem}e_08{ps}.csv"), True))
    out.append((os.path.join(sh, f"03summary.{stem}_08sum.csv"), True))
    for ps in ("tou", "kou", "kok", "ren", "sig"):
        # 137MB ×5。ハッシュだけで比べる
        out.append((os.path.join(sh, f"90nenbe.{stem}e_08{ps}.csv"), False))
    out.append((os.path.join(cu, f"cuta-{stem}.csv"), True))
    out.append((os.path.join(cu, f"cutb-{stem}.csv"), True))
    out.append((os.path.join(cu, f"Tokutyo.{s}-{s}-{e}-{w}-1120_{y}.csv"), True))
    return out


def stdin_text(c=CASE):
    return ("0\n8\n0\n0\n0\n0\n0\n0\n"
            f"{c['shisan']}\n{c['econ']}\n{c['waku']}\n{c['yobi']}\n")


def inputs_ready():
    c = CASE
    need = [f"emp/rslt/u-rev/shus/shus.{c['shisan']}-{c['econ']}-{c['waku']}_kou",
            f"bas/data/KYOSHUTUKIN{c['shisan']}-{c['shisan']}"
            f"-{c['econ']}-{c['waku']}-{c['yobi']}",
            "emp/data/ez-arev/nof2024.csv"]
    return all(os.path.isfile(os.path.join(suuri(), p)) for p in need)


def sha(path, buf=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


@pytest.mark.slow
def test_収支計算の出力がCとバイト一致(tmp_path):
    exe = os.path.join(suuri(), "emp/exec/asys20")
    if not inputs_ready():
        pytest.skip("⑤の入力が無い"
                    "（STEPS=1234 検証/実行/run_pipeline.sh 3001 を先に実行）")
    if not os.path.isfile(exe):
        pytest.skip(f"原本のバイナリが無い（{exe}）。"
                    "検証/実行/run_pipeline.sh がビルドします")

    text = stdin_text().encode("ascii")
    paths = out_paths()

    # ---- C ----
    t0 = time.time()
    r = subprocess.run([exe], input=text, capture_output=True, timeout=3600)
    t_c = time.time() - t0
    assert r.returncode == 0, (
        f"C の⑤が失敗 rc={r.returncode}\n"
        f"{r.stdout.decode('utf-8', 'replace')[-2000:]}")

    c_sha = {}
    saved = {}
    for p, small in paths:
        assert os.path.isfile(p), f"C がこのファイルを作っていない: {p}"
        c_sha[p] = sha(p)
        if small:
            q = str(tmp_path / os.path.basename(p))
            shutil.copy2(p, q)
            saved[p] = q

    # ---- Python ----
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import main;"
         " sys.exit(main.main())",
         os.path.join(HERE, "emp_shushi")],
        input=text, capture_output=True, timeout=7200)
    t_p = time.time() - t0
    assert r.returncode == 0, (
        f"Python の⑤が失敗 rc={r.returncode}\n"
        f"{r.stdout.decode('utf-8', 'replace')[-2000:]}\n"
        f"{r.stderr.decode('utf-8', 'replace')[-3000:]}")

    # ---- 比較 ----
    bad = []
    total = 0
    for p, small in paths:
        assert os.path.isfile(p), f"Python がこのファイルを作っていない: {p}"
        total += os.path.getsize(p)
        if sha(p) == c_sha[p]:
            continue
        msg = f"{os.path.basename(p)} が違う"
        if small and p in saved:
            msg += "\n" + _first_diff(saved[p], p)
        bad.append(msg)

    assert not bad, "C と一致しないファイル:\n" + "\n".join(bad)

    assert total > 600e6, f"比較したのが {total/1e6:.0f}MB しかない"
    print(f"\n  {len(paths)} ファイル / {total/1e6:.0f}MB がバイト一致")
    print(f"  C {t_c:.1f} 秒 / Python {t_p:.1f} 秒（{t_p/t_c:.1f} 倍）")


def _first_diff(a, b, maxlen=300):
    """最初に違う行を返す（違ったときの手掛かり用）。"""
    with open(a, "rb") as fa, open(b, "rb") as fb:
        n = 0
        while True:
            la, lb = fa.readline(), fb.readline()
            n += 1
            if not la and not lb:
                return "  （行単位では差が見つからない＝末尾の差か）"
            if la != lb:
                return (f"  {n} 行目\n"
                        f"    C      {la[:maxlen]!r}\n"
                        f"    Python {lb[:maxlen]!r}")


def test_出力ファイルの一覧が14本():
    """比較対象を数え間違えていないかの番犬。"""
    assert len(out_paths()) == 14
    assert sum(1 for _, small in out_paths() if not small) == 5, "90nenbe は5本"
