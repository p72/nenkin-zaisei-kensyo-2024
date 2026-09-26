#!/usr/bin/env python3
"""第3号の保険料をどちらの財布に入れるか — 厚年留保案と按分据置型（国年充当）を比べる（非公式）。

同じ条件（2031年度から、第3号が国民年金保険料相当額を全員納付）で2つの案を流す。

  予備番号 801  厚年留保案         保険料は厚生年金勘定。厚生年金保険料率を下げる（RYUHO）
  予備番号 531  按分据置型（国年充当） 保険料は国民年金勘定。按分は現行のまま（SANGO_MODE=1）

経済前提は是枝レポートと同じ、成長型経済移行・継続（3002）と過去30年投影（3003）。

使い方（リポジトリの直下で）
  python3 勉強/応用編/第3号の保険料.py run        # 531 を流す（801 は 検証/3号廃止/ryuho.py run）
  python3 勉強/応用編/第3号の保険料.py report     # 比べる表
  python3 勉強/応用編/第3号の保険料.py table      # 財政見通し対照表（勉強/応用編/図/）
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
SH = os.path.join(SUURI, "emp", "rslt", "ez_arev", "shushi")
START = 2031
CASES = (("3003", "過去30年投影", ["1", "1", "0", "2"]), ("3002", "成長型経済移行・継続", []))
KW2024 = 369915          # 2024年度の現役男子の平均手取り（月額、⑤ shus_smodel）
W2024 = 455000           # 2024年度の男子の平均標準報酬（月額、同）


def run():
    for i, (case, _, args) in enumerate(CASES):
        env = dict(os.environ, SANGO=str(START), SANGO_MODE="1", YOBI="531", STEPS="45")
        if i > 0:
            env["SKIP_BUILD"] = "1"
        subprocess.run([os.path.join(ROOT, "検証", "実行", "run_pipeline.sh"), case] + args,
                       env=env, check=True)
        for p in os.listdir(SH):
            if p.startswith("90nenbe.") and "-1120-531e_" in p:
                os.remove(os.path.join(SH, p))


def _mods():
    sys.path.insert(0, os.path.join(ROOT, "検証", "オプション試算"))
    sys.path.insert(0, os.path.join(ROOT, "検証", "3号廃止"))
    import compare_option as co
    import make_taishohyo as T
    s = importlib.util.spec_from_file_location("a", os.path.join(ROOT, "検証", "3号廃止", "analyze_sango.py"))
    a = importlib.util.module_from_spec(s)
    s.loader.exec_module(a)
    return co, T, a


def discount(case):
    """経済前提の名目運用利回りで2024年度末に割り引く係数。"""
    rows = {int(float(l.split(",")[0])) + 2000: [float(x) for x in l.split(",")]
            for l in open(os.path.join(SUURI, "emp", "data", "u-rev", "econ", f"econ-{case}.csv"))}
    D, d = {2024: 1.0}, 1.0
    for y in range(2025, 2121):
        r = rows.get(y, rows[max(rows)])
        d /= (1 + r[1] / 100) * (1 + r[6] / 100)
        D[y] = d
    return D


def delta(case):
    p = os.path.join(SUURI, "emp", "log", f"emp-{case}-{case}-{case}-{case}-1120-801.log")
    return float(re.search(r"厚年留保案：保険料率を\d+年度から ([0-9.]+)",
                           open(p, encoding="utf-8", errors="replace").read()).group(1))


def sango_hokenryo(case):
    p = os.path.join(SUURI, "emp", "data", f"ryuho-{case}-{case}-{case}-{case}-1120-801.csv")
    return {int(l.split(",")[0]): sum(float(x) for x in l.split(",")[1:]) for l in open(p)}


def nen(y):
    return "調整なし" if y is None or y <= 2024 else f"{y}年度"


def summary(case):
    co, _, a = _mods()
    v = f"{case}-{case}-{case}-{case}"
    D = discount(case)
    Y = range(START, 2120)
    rate = {yb: co.read_rate(v, yb, SH)[2120] for yb in ("000", "801", "531")}
    run = {yb: a.load_run(SUURI, case, yb, yb) for yb in ("000", "531")}
    hk = sango_hokenryo(case)
    pv = lambda s: sum(s[y] * D[y] for y in Y)                                       # noqa: E731
    return dict(
        delta=delta(case) * 100, rate=rate, run=run,
        hokenryo=pv(hk) / 1e12,
        kokko=(pv(run["531"]["kokko_total"]) - pv(run["000"]["kokko_total"])) / 1e12,
        kyoshutu=(pv(run["531"]["kou_kyoshutu"]) - pv(run["000"]["kou_kyoshutu"])) / 1e4,
        kn_dogai=run["531"]["kn_dogai_2119"])


def report():
    print("| | " + " | ".join(f"{n}：厚年留保案 | {n}：按分据置型（国年充当）" for _, n, _ in CASES) + " |")
    print("|---|" + "---|---|" * len(CASES))
    S = {c: summary(c) for c, _, _ in CASES}
    def row(lab, f):
        print(f"| {lab} | " + " | ".join(f"{f(S[c], '801')} | {f(S[c], '531')}" for c, _, _ in CASES) + " |")
    row("所得代替率（調整終了後）", lambda s, y: f"{s['rate'][y]['所得代替率']*100:.1f}%")
    row("　うち基礎", lambda s, y: f"{s['rate'][y]['代替率(基礎)']*100:.1f}%")
    row("　うち比例", lambda s, y: f"{s['rate'][y]['代替率(比例)']*100:.1f}%")
    row("基礎の調整終了", lambda s, y: nen(s["run"]["000" if y == "801" else "531"]["kiso_end"]))
    row("比例の調整終了", lambda s, y: nen(s["run"]["000" if y == "801" else "531"]["hirei_end"]))
    row("厚生年金保険料率", lambda s, y: f"−{s['delta']:.2f}％pt" if y == "801" else "18.3%のまま")
    row("国民年金の積立度合（2119年度末）", lambda s, y: "1.0" if y == "801" else f"{s['kn_dogai']:.1f}")
    row("国庫負担の増（2031〜2119年度・現在価値）", lambda s, y: "0" if y == "801" else f"+{s['kokko']:.0f}兆円")
    row("厚生年金の基礎年金拠出金の増（同）", lambda s, y: "0" if y == "801" else f"+{s['kyoshutu']:.0f}兆円")
    print()
    for c, n, _ in CASES:
        s = S[c]
        b0, b1 = s["rate"]["000"]["代替率(基礎)"], s["rate"]["531"]["代替率(基礎)"]
        h0, h1 = s["rate"]["000"]["代替率(比例)"], s["rate"]["531"]["代替率(比例)"]
        print(f"{n}: 第3号の保険料 2031〜2119年度・現在価値 {s['hokenryo']:.0f}兆円 ／ "
              f"厚年留保案の保険料の軽減 月{W2024 * s['delta'] / 100:,.0f}円（労使計、2024年度の平均標準報酬で）／ "
              f"按分据置型の基礎年金 1人 月{(b1 - b0) / 2 * KW2024:+,.0f}円・報酬比例（夫） 月{(h1 - h0) * KW2024:+,.0f}円"
              "（2024年度の賃金水準で）")


def table():
    co, T, a = _mods()
    out = os.path.join(HERE, "図")
    os.makedirs(out, exist_ok=True)
    for case, cname, _ in CASES:
        s = summary(case)
        T.SCENARIOS["801-531"] = dict(
            name="厚年留保対按分据置", label="按分据置型", yobi="531", yobi4="531",
            base=("801", "801", "厚年留保案"),
            title="第3号の保険料を国民年金勘定に入れた場合（按分据置型・国年充当）",
            desc=f"厚年留保案（上の行）：{START}年度から第3号（20〜59歳）が国民年金保険料相当額を全員納付し、"
                 "厚生年金勘定に入れる。基礎年金拠出金の按分は現行のまま。2120年度の積立度合を現行制度と"
                 f"同じに保つよう厚生年金保険料率を{s['delta']:.2f}％pt下げる<br>"
                 f"○ 按分据置型（国年充当、網かけの行）：同じ保険料を国民年金勘定に入れる。按分は現行のまま。"
                 "厚生年金保険料率は18.3%のまま",
            note=f'<b style="font-weight:bold">同じ保険料でも、入れる財布で結果が逆になる。</b>'
                 "厚年留保案は給付を変えずに厚生年金保険料率を下げる。按分据置型は基礎年金が「調整なし」の"
                 "天井まで上がり、その分の基礎年金拠出金が厚生年金にかかって報酬比例が下がる。"
                 f"国庫負担も増える（2031〜2119年度の現在価値で約{s['kokko']:.0f}兆円）。"
                 "按分据置型の基礎の「調整なし」は天井に当たった値で、均衡解ではない。",
            note3="どちらの行も、公表された計算プログラムに独自のレバーを加えて計算した"
                  '<b style="font-weight:bold">非公式の独自計算</b>で、厚生労働省の試算ではない。'
                  "厚年留保案は是枝俊悟（大和総研、2026年9月25日）の設計に合わせた。")
        sys.argv = ["make_taishohyo.py", "--case", case, "--yobi", "801-531"]
        T.main()
        for ext in ("png", "pdf"):
            src = os.path.join(T.HERE, "図", f"対照表_{case}_801-531_厚年留保対按分据置.{ext}")
            shutil.move(src, os.path.join(out, f"対照表_{case}_厚年留保と按分据置.{ext}"))
        print("移した:", os.path.join(out, f"対照表_{case}_厚年留保と按分据置.png"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) == 2 else ""
    {"run": run, "report": report, "table": table}.get(cmd, lambda: sys.exit(__doc__))()
