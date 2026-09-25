#!/usr/bin/env python3
"""運用利回りだけを名目で置き換えて④⑤を流し直す思考実験（非公式）。

「運用利回り4.95%が続いたら」を再現するための道具。原本にレバーは無いので、
次の2つを一時的に書き換えて④⑤を流し、終わったら必ず元に戻す。

  1. 経済前提 emp/data/u-rev/econ/econ-{試算番号}.csv の「物価に対する実質の運用利回り」
     （2・3列目。④が3列目、⑤が2列目を読む）を、名目が指定値になる値に置き換える
  2. ②の出力 emp/rslt/u-rev/shus/shus.{番号}-{番号}-{番号}_{kou,kok,ren,sig} の
     「経済的要素」の利回りの欄。⑤はこの値と経済前提が一致しないと止まる
     （収支計算/rdfl.c の rdfl_u_sys）。②は利回りを出力に書くだけで計算には
     使っていない（給付費推計/econ.cpp・crshfl.cpp）ので、②を流し直すのと同じになる

どちらも2025年度以降だけを置き換える（2024年度以前は実績）。①〜③は流し直さない。

使い方（リポジトリの直下で）
  python3 勉強/応用編/運用利回り.py run 3003 0.0495     # 過去30年投影の賃金・物価で運用4.95%
  python3 勉強/応用編/運用利回り.py run 3001 0.0495     # 高成長実現の賃金・物価で運用4.95%
  python3 勉強/応用編/運用利回り.py report              # 積立度合・使い切れない積立金の表
  python3 勉強/応用編/運用利回り.py table 3003 3001     # 財政見通し対照表（勉強/応用編/図/）

前提：通常試算（予備番号 000）と、パッチ済みのビルドがあること
      （検証/実行/run_pipeline.sh を一度流してあれば足りる）。結果は予備番号 495 に書く。
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
YOBI = "495"
START = 25          # 2025年度から置き換える
SEIDO = ("kou", "kok", "ren", "sig")


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def targets(case):
    econ = os.path.join(SUURI, "emp", "data", "u-rev", "econ", f"econ-{case}.csv")
    usys = [os.path.join(SUURI, "emp", "rslt", "u-rev", "shus", f"shus.{case}-{case}-{case}_{s}")
            for s in SEIDO]
    return econ, usys


def patch_econ(p, nom):
    rows = [l.rstrip("\n").split(",") for l in open(p)]
    for r in rows:
        if int(float(r[0])) >= START:
            cpi = float(r[6]) / 100
            r[1] = r[2] = f"{((1 + nom) / (1 + cpi) - 1) * 100:.6f}"
    with open(p, "w") as f:
        f.write("\n".join(",".join(r) for r in rows) + "\n")


def patch_usys(p, nom):
    L = open(p, encoding="utf-8", errors="surrogateescape").read().split("\n")
    i = next(j for j, l in enumerate(L) if re.match(r"^\s*1, -?\d\.\d{5},", l))
    n = 0
    while i < len(L) and re.match(r"^\s*(\d+), ?-?\d\.\d{5},", L[i]):
        if int(L[i].split(",")[0]) >= START:
            f = L[i].split(",")
            f[1] = f" {nom:.5f}"
            L[i] = ",".join(f)
            n += 1
        i += 1
    with open(p, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write("\n".join(L))
    return n


def run(case, nom):
    econ, usys = targets(case)
    files = [econ] + usys
    bak = tempfile.mkdtemp(prefix="unyo-bak-", dir=SUURI)
    before = {p: md5(p) for p in files}
    for p in files:
        shutil.copy2(p, os.path.join(bak, os.path.basename(p)))
    try:
        patch_econ(econ, nom)
        for p in usys:
            print(os.path.basename(p), "利回りの欄", patch_usys(p, nom), "行")
        args = [os.path.join(ROOT, "検証", "実行", "run_pipeline.sh"), case]
        if case == "3003":
            args += ["1", "1", "0", "2"]          # 過去30年投影は労働参加漸進
        env = dict(os.environ, SKIP_BUILD="1", STEPS="45", YOBI=YOBI)
        subprocess.run(args, env=env, check=True)
    finally:
        for p in files:
            shutil.copy2(os.path.join(bak, os.path.basename(p)), p)
        shutil.rmtree(bak)
        bad = [p for p in files if md5(p) != before[p]]
        if bad:
            sys.exit("★ 元に戻せなかったファイルがある: " + ", ".join(bad))
        print("経済前提と u-sys を元に戻した（md5 一致）")
    # 年齢別の詳細（1本130MB超）は使わないので消す
    for p in glob.glob(os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi",
                                    f"90nenbe.{case}-*-1120-{YOBI}e_*")):
        os.remove(p)


def _modules():
    sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
    sys.path.insert(0, os.path.join(ROOT, "検証", "3号廃止"))
    import compare_option as co
    import make_taishohyo as T
    return co, T


def _discount(case, nom=None):
    rows = {int(float(l.split(",")[0])) + 2000: [float(x) for x in l.split(",")]
            for l in open(targets(case)[0])}
    D, d = {2024: 1.0}, 1.0
    for y in range(2025, 2121):
        r = rows.get(y, rows[max(rows)])
        d /= 1 + (nom if nom else (1 + r[1] / 100) * (1 + r[6] / 100) - 1)
        D[y] = d
    return D


def report(nom=0.0495):
    """厚生年金の積立度合、使い切れない積立金（現在価値）、保険料率への換算（推定）。"""
    co, T = _modules()
    print("| ケース | 運用 | 厚生年金の積立度合（2060／2100／2120） | 使い切れない積立金（現在価値） | 保険料率に換算 |")
    print("|---|---|---|---|---|")
    for case, cname in (("3003", "過去30年投影"), ("3001", "高成長実現")):
        v = f"{case}-{case}-{case}-{case}"
        for lab, yb, n in (("公式", "000", None), (f"{nom*100:.2f}%", YOBI, nom)):
            e = co.read_emp(v, yb, T.SH)
            D = _discount(case, n)
            spare = (e[2120]["年度末積立金"] - e[2120]["支出合計"]) * D[2120]
            pvw = sum(e[y]["標準報酬総額"] * D[y] for y in range(2025, 2121))
            dd = "／".join(f"{e[y]['積立度合']:.1f}" for y in (2060, 2100, 2120))
            print(f"| {cname} | {lab} | {dd} | {spare:.1f}兆円 | {spare / pvw * 100:.2f}ポイント |")


NOTES = {
    "3003": dict(
        desc="賃金・物価・人口などの前提は過去30年投影ケースのまま",
        note='<b style="font-weight:bold">給付は天井（調整なし）に当たり、積立金は使い道がないまま増え続ける。</b>'
             "報酬比例は調整なし、基礎年金は2025年度に小さく調整するだけ。"
             "2120年度の厚生年金の積立度合は88.4（現行制度は1.0）。"
             "運用利回りと賃金上昇率の差（スプレッド）は現行の約1.7%に対し約3.6%。"),
    "3001": dict(
        desc="賃金・物価・人口などの前提は高成長実現ケースのまま（公式の運用利回りは2026〜2033年度 名目4.96%、"
             "2034年度以降 5.47%）",
        note='<b style="font-weight:bold">報酬比例は天井（調整なし）のまま、厚生年金の積立金は使い道がないまま増え続ける。</b>'
             "公式の高成長実現より運用利回りが低いので、基礎年金の調整は2039年度から2044年度に延びる。"
             "2120年度の厚生年金の積立度合は13.9（公式の高成長実現は22.7）。"
             "運用利回りと賃金上昇率の差（スプレッド）は約0.9%（公式は約1.4%）。"),
}


def table(cases):
    """財政見通し対照表を 勉強/応用編/図/ に書く（make_taishohyo の台帳に一時的に足す）。"""
    _, T = _modules()
    out = os.path.join(HERE, "図")
    os.makedirs(out, exist_ok=True)
    for case in cases:
        n = NOTES[case]
        T.SCENARIOS[YOBI] = dict(
            name="運用利回り4.95%", label="運用4.95%", yobi4=YOBI, base=("000", "000", "現行制度"),
            title="運用利回りが名目4.95%で続いた場合（思考実験）",
            desc="運用4.95%：2025年度以降の積立金の運用利回りを名目年4.95%（GPIF の市場運用開始以来の年率実績）"
                 "とする。" + n["desc"],
            note=n["note"],
            note3="運用4.95%は、公表された計算プログラムの経済前提（運用利回り）だけを書き換えて④⑤を計算した"
                  '<b style="font-weight:bold">非公式の思考実験</b>で、厚生労働省の試算ではない。')
        sys.argv = ["make_taishohyo.py", "--case", case, "--yobi", YOBI]
        T.main()
        for ext in ("png", "pdf"):
            src = os.path.join(T.HERE, "図", f"対照表_{case}_{YOBI}_運用利回り4.95%.{ext}")
            shutil.move(src, os.path.join(out, f"対照表_{case}_運用495.{ext}"))
        print("移した:", os.path.join(out, f"対照表_{case}_運用495.png"))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "run" and len(sys.argv) == 4:
        run(sys.argv[2], float(sys.argv[3]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "report":
        report()
    elif len(sys.argv) >= 3 and sys.argv[1] == "table":
        table(sys.argv[2:])
    else:
        sys.exit(__doc__)
