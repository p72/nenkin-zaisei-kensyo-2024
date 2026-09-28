#!/usr/bin/env python3
"""基礎年金を税方式にして、増える国庫負担を赤字国債でまかなったら（思考実験・非公式）。

設計
  - 給付は現行制度のまま（基礎年金も報酬比例も、マクロ経済スライドも今どおり）
  - 実施年度（2027年度）から国民年金保険料を廃止し、厚生年金保険料は基礎年金に当たる分を下げる
    → ⑤の ZEI レバー（予備番号901、税方式7万円.py の run と同じ出力を使う）
  - 国は基礎年金拠出金を全額負担する。今の国庫負担との差（拠出金のうち保険料でまかなっていた分）を、
    毎年赤字国債で出す。税は決めない

名目GDP（推定）
  - 2024年度 642.4兆円（内閣府「2024年度国民経済計算年次推計」2020年基準、第一次年次推計値）
  - 以後は (1＋物価上昇率)(1＋実質経済成長率) で延ばす。物価上昇率は経済前提ファイル（econ-{case}.csv）、
    実質経済成長率は財政検証の長期の前提を2025年度から一定とした
  - 感応度として、名目GDPを標準報酬総額に比例させた系列も出す（2060年以降の人口減少が効く）

使い方（リポジトリの直下で。通常試算3001〜3003と、税方式7万円.py run の901が要る）
  python3 勉強/応用編/基礎年金の赤字国債.py report   # 表
  python3 勉強/応用編/基礎年金の赤字国債.py graph    # 図（勉強/応用編/図/）
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
s = importlib.util.spec_from_file_location("zei7", os.path.join(HERE, "税方式7万円.py"))
Z = importlib.util.module_from_spec(s)
s.loader.exec_module(Z)

START = 2027
GDP_2024 = 642.4147e12          # 名目GDP（2024年度）。内閣府 point_20251208.pdf 4頁
REAL = {"3003": -0.1, "3002": 1.1, "3001": 1.6}   # 実質経済成長率（%）。財政検証結果の概要 2頁
CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"), ("3001", "高成長実現"))
YEARS = (2027, 2030, 2040, 2050, 2060, 2080, 2100, 2120)


def keisan(case):
    """年度ごとの国債発行額・残高・名目GDP（円・名目）。"""
    co, _, a = Z._mods()
    v = f"{case}-{case}-{case}-{case}"
    run = a.load_run(Z.SUURI, case, "000", "000")
    emp0 = co.read_emp(v, "000", Z.SH)
    econ = {int(float(l.split(",")[0])) + 2000: [float(x) for x in l.split(",")]
            for l in open(os.path.join(Z.SUURI, "emp", "data", "u-rev", "econ", f"econ-{case}.csv"))}
    W = {y: emp0[y]["標準報酬総額"] for y in range(2024, 2121)}
    try:
        d = Z.delta(case)
    except (OSError, AttributeError):
        d = None                   # 901 を流していないケース（保険料の引き下げ幅は出さない）
    G, GW = {2024: GDP_2024}, {2024: GDP_2024}
    for y in range(2025, 2121):
        G[y] = G[y - 1] * (1 + econ[y][6] / 100) * (1 + REAL[case] / 100)
        GW[y] = GDP_2024 * W[y] / W[2024]
    Dc = Z.discount(case)
    b0 = bg = br = pv = pvh = 0.0
    out = {}
    for y in range(START, 2121):
        D = run["kyo_total"][y] - run["kokko_total"][y]
        g = G[y] / G[y - 1] - 1
        r = (1 + econ[y][1] / 100) * (1 + econ[y][6] / 100) - 1   # 名目運用利回り
        bg_ri, br_ri = bg * g, br * r                                 # その年度の利払い
        b0, bg, br = b0 + D, bg + bg_ri + D, br + br_ri + D
        pv += D * Dc[y]
        hoken = run["kn_hoken"][y] + (d * W[y] * 1e12 if d is not None else float("nan"))
        pvh += hoken * Dc[y]
        out[y] = dict(D=D, hoken=hoken, b0=b0, bg=bg, br=br, G=G[y], GW=GW[y], g=g, r=r,
                      ri_g=bg_ri, ri_r=br_ri)
    rate = {yb: co.read_rate(v, yb, Z.SH)[2120]["所得代替率"] for yb in ("000", "901") if d is not None or yb == "000"}
    return dict(y=out, pv=pv, pvh=pvh, delta=d, rate=rate)


def report():
    for case, cname in CASES:
        k = keisan(case)
        o = k["y"]
        print(f"## {cname}（{case}）")
        if k["delta"] is not None:
            print(f"厚生年金保険料率の引き下げ {k['delta'] * 100:.2f}pt、所得代替率（2120年度）"
                  f"現行 {k['rate']['000'] * 100:.4f}% ／ 税方式 {k['rate']['901'] * 100:.4f}%")
        print(f"名目成長率 {o[2040]['g'] * 100:.2f}%、名目運用利回り {o[2040]['r'] * 100:.2f}%（2040年度）")
        print()
        print("| 年度 | 発行額 | 対GDP | 累積（元本） | 累積÷GDP | 利払い込み（金利＝名目成長率） | 利払い込み（金利＝運用利回り） | 参考：GDPを賃金総額連動にした累積（元本）÷GDP |")
        print("|---|---|---|---|---|---|---|---|")
        for y in YEARS:
            x = o[y]
            print(f"| {y} | {x['D'] / 1e12:.1f}兆円 | {x['D'] / x['G'] * 100:.2f}% | {x['b0'] / 1e12:,.0f}兆円 | "
                  f"{x['b0'] / x['G'] * 100:.0f}% | {x['bg'] / x['G'] * 100:.0f}% | {x['br'] / x['G'] * 100:.0f}% | "
                  f"{x['b0'] / x['GW'] * 100:.0f}% |")
        x = o[2120]
        print()
        print(f"- 現在価値（2024年度末、2027〜2120年度の発行額の合計）: {k['pv'] / 1e12:.0f}兆円"
              f"（2024年度GDPの {k['pv'] / GDP_2024 * 100:.0f}%）")
        if k["delta"] is not None:
            print(f"- 同じ期間に廃止する保険料の現在価値: {k['pvh'] / 1e12:.0f}兆円")
        print(f"- 2120年度の利払い: 金利＝名目成長率 {x['ri_g'] / 1e12:.1f}兆円、金利＝運用利回り {x['ri_r'] / 1e12:.1f}兆円"
              f"（発行額 {x['D'] / 1e12:.1f}兆円）")
        print(f"- 2120年度の名目GDP: {x['G'] / 1e12:,.0f}兆円")
        print()


def graph():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "IPAPGothic"
    col = {"3003": "#2a78d6", "3002": "#eb6834", "3001": "#1baf7a"}
    fig, ax = plt.subplots(1, 2, figsize=(12, 5.2))
    ys = list(range(START, 2121))
    for case, cname in CASES:
        o = keisan(case)["y"]
        a1 = [o[y]["D"] / o[y]["G"] * 100 for y in ys]
        a2 = [o[y]["b0"] / o[y]["G"] * 100 for y in ys]
        a3 = [o[y]["bg"] / o[y]["G"] * 100 for y in ys]
        ax[0].plot(ys, a1, color=col[case], lw=2, label=cname)
        ax[1].plot(ys, a3, color=col[case], lw=2, label=f"{cname}（利払いも国債）")
        ax[1].plot(ys, a2, color=col[case], lw=2, ls="--", label=f"{cname}（元本のみ）")
        ax[1].annotate(f"{a3[-1]:.0f}%", (2120, a3[-1]), xytext=(4, 0), textcoords="offset points",
                       va="center", fontsize=9, color="#333333")
        ax[1].annotate(f"{a2[-1]:.0f}%", (2120, a2[-1]), xytext=(4, 0), textcoords="offset points",
                       va="center", fontsize=9, color="#333333")
    ax[0].set_title("毎年の赤字国債の発行額（名目GDP比）")
    ax[0].set_ylim(0, 2.5)
    ax[1].set_title("累積残高（名目GDP比）　利払いの金利＝名目成長率")
    ax[1].set_xlim(2025, 2130)
    for x in ax:
        x.set_xlabel("年度")
        x.set_ylabel("%")
        x.grid(True, color="#dddddd", lw=0.6)
        x.spines[["top", "right"]].set_visible(False)
    ax[0].legend(frameon=False, fontsize=9)
    ax[1].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("基礎年金を税方式にして、赤字国債でまかなった場合（非公式の思考実験）", fontsize=13)
    fig.text(0.01, 0.01, "非公式：2024年財政検証の計算プログラムに独自のレバーを加えた試算。厚生労働省の試算ではない。"
             "名目GDPは2024年度642.4兆円（内閣府）を物価上昇率と財政検証の実質経済成長率で延ばした推定。",
             fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    out = os.path.join(HERE, "図", "赤字国債_対GDP.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": report, "graph": graph}[cmd]()
