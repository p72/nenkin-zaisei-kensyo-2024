#!/usr/bin/env python3
"""厚年留保案（第3号の保険料を厚生年金勘定に入れる）で、厚生年金保険料率をどれだけ
下げられるか — 大和総研レポート（是枝俊悟 2026-09-25）の図表3との照合。

  経済前提    成長型経済移行・継続（3002）／過去30年投影（3003、労働参加漸進）
  加入範囲    現行（通常試算）／週10時間以上（適用拡大 約860万人、KAKUDAI=4）
  保険料      国民年金保険料相当額（RYUHO_RITU=1）／その50％（0.5）
  実施年度    2031年度（レポートの仮定）

予備番号 801 全額・802 半額（通常の加入範囲）、841 全額・842 半額（週10時間以上）。
週10時間以上は外枠番号 340x（①から流し直した適用拡大）。

使い方（リポジトリの直下で）
  python3 検証/3号廃止/ryuho.py run       # 8通りを流す（通常試算・適用拡大が無ければ先に作る）
  python3 検証/3号廃止/ryuho.py report    # 図表3との照合表と、2023年度の国民年金の持ち出し
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
SH = os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi")
RUN = os.path.join(ROOT, "検証", "実行", "run_pipeline.sh")
START = 2031
CASES = (("3002", "成長型経済移行・継続", []), ("3003", "過去30年投影", ["1", "1", "0", "2"]))
HANI = (("現行法のまま", None, "000", ("801", "802")),
        ("週10時間以上", "4", "040", ("841", "842")))
RITU = ("1", "0.5")
# 大和総研レポート 図表3（％pt）。[経済][加入範囲] = (全額, 50％)
DAIWA = {"3002": {"現行法のまま": (0.32, 0.19), "週10時間以上": (0.20, 0.10)},
         "3003": {"現行法のまま": (0.40, 0.23), "週10時間以上": (0.26, 0.13)}}


def waku(case, kakudai):
    return ("34" + case[2:]) if kakudai else case


def run():
    for case, _, args in CASES:
        for _, kakudai, base, yobis in HANI:
            w = waku(case, kakudai)
            env = dict(os.environ, SKIP_BUILD="1", WAKU=w)
            if kakudai:
                env["KAKUDAI"] = kakudai
            summ = os.path.join(SH, f"03summary.{case}-{case}-{case}-{w}-1120-{base}_08sum.csv")
            if not os.path.exists(summ):          # 比べる相手（通常試算・適用拡大）を①から
                subprocess.run([RUN, case] + args, env=dict(env, YOBI=base), check=True)
            for yobi, ritu in zip(yobis, RITU):
                subprocess.run([RUN, case] + args, check=True,
                               env=dict(env, YOBI=yobi, STEPS="45", RYUHO=str(START), RYUHO_RITU=ritu))
                for p in os.listdir(SH):          # 年齢別の詳細（1本130MB超）は使わない
                    if p.startswith("90nenbe.") and f"-1120-{yobi}e_" in p:
                        os.remove(os.path.join(SH, p))


def delta(case, w, yobi):
    p = os.path.join(SUURI, "emp", "log", f"emp-{case}-{case}-{case}-{w}-1120-{yobi}.log")
    m = re.search(r"厚年留保案：保険料率を\d+年度から ([0-9.]+)",
                  open(p, encoding="utf-8", errors="replace").read())
    return float(m.group(1)) * 100


def sango(case, w, yobi, y):
    """その年度の第3号（4制度計、万人）と、第3号の保険料（兆円）。"""
    p = os.path.join(SUURI, "emp", "data", f"ryuho-{case}-{case}-{case}-{w}-1120-{yobi}.csv")
    rows = {int(l.split(",")[0]): [float(x) for x in l.split(",")[1:]] for l in open(p)}
    return sum(rows[y]) / 1e12


def report():
    print("## 図表3との照合（厚生年金保険料率の引き下げ幅、％pt）\n")
    print("| 経済前提 | 加入範囲 | 国民年金保険料相当額 | 同50％ | 大和総研 | 第3号の保険料 2031年度 |")
    print("|---|---|---|---|---|---|")
    for case, cname, _ in CASES:
        for hname, kakudai, _, yobis in HANI:
            w = waku(case, kakudai)
            d = [delta(case, w, y) for y in yobis]
            dw = DAIWA[case][hname]
            print(f"| {cname} | {hname} | **{d[0]:.2f}** | **{d[1]:.2f}** | {dw[0]:.2f}／{dw[1]:.2f} "
                  f"| {sango(case, w, yobis[0], START):.2f}兆円 |")
    print()
    sys.path.insert(0, HERE)
    import importlib.util
    s = importlib.util.spec_from_file_location("a", os.path.join(HERE, "analyze_sango.py"))
    a = importlib.util.module_from_spec(s)
    s.loader.exec_module(a)
    print("## 国民年金の「持ち出し」（2023年度、1人1か月）\n")
    print("| ケース | 拠出金単価 | うち国庫 | 国民年金の実質負担 | 保険料（実効） | 持ち出し |")
    print("|---|---|---|---|---|---|")
    for case, cname, _ in CASES:
        r = a.load_run(SUURI, case, "000", "000")
        y = 2023
        net = r["tanka"][y] - r["tanka_kokko"][y]
        eff = r["kn_hoken"][y] / r["santei_1go"][y] / 12
        print(f"| {cname} | {r['tanka'][y]:,.0f}円 | {r['tanka_kokko'][y]:,.0f}円 | {net:,.0f}円 "
              f"| {eff:,.0f}円 | {net - eff:,.0f}円 |")
    print("| 大和総研（実績） | 37,697円 | ― | 18,849円 | 16,520円 | 2,329円 |")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "run":
        run()
    elif len(sys.argv) == 2 and sys.argv[1] == "report":
        report()
    else:
        sys.exit(__doc__)
