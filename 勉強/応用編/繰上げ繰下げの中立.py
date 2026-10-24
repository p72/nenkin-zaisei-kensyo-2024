#!/usr/bin/env python3
"""繰上げ減額率・繰下げ増額率は年金財政に中立か：2024年財政検証の前提で計算し直す（非公式・推定）。

厚生労働省（第12回社会保障審議会年金部会 資料1、2019年10月18日）と同じ式で、
「65歳から受け取った場合と生命年金現価が等しくなる率」を求める。

  生命年金現価：基準年齢で生きている人が、受給開始年齢から受け取る年金（年額1）を、
                生存率で重み付けし、割引率で基準年齢の価値に割り戻して足したもの
  繰下げ増額率 = A / C − 1     A：65歳開始、C：繰下げ開始（どちらも65歳基準）
  繰上げ減額率 = 1 − A / B     A：65歳開始、B：繰上げ開始（どちらも60歳基準）

前提（どれも計算プログラムの入出力から読む）
  死亡率：③の入力 QX-M2023.csv（2023年推計・死亡中位、2019〜2070年。2071年以降は2070年の値）。
          生まれた年度の世代を、その年ごとの死亡率で追いかける（コホート）。男女平均は生存率の単純平均
  割引率：実質運用利回り（対物価）。経済前提 econ-XXXX.csv の長期の値と、国債利回りからの目安
  スライド：④のカット率 cuta（基礎年金）。既裁定の年金は物価で改定（実質一定）とみなし、
            マクロ経済スライドで目減りする分だけを追う。使うときは通常試算（000）の出力が要る
  年金は年の真ん中にまとめて払う形で近似する

使い方（リポジトリの直下で）
  python3 勉強/応用編/繰上げ繰下げの中立.py report     # 記事の表
  python3 勉強/応用編/繰上げ繰下げの中立.py graph      # 記事の図（勉強/応用編/図/）

  スライド込みの行は、通常試算（検証/実行/run_pipeline.sh 3001、3003 1 1 0 2）を流してあるときだけ出る。
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "検証"))
import suuri_env  # noqa: E402

BIRTH = 1960          # 2025年度に65歳になる世代
AMAX = 110            # 生存率を追う上限の年齢
# 割引率（実質、対物価）。2024年財政検証の長期（2034年度以降）の値と、国債利回りからの目安
RATES = (("1人当たりゼロ成長", 0.014), ("30年国債−物価2%", 0.020), ("過去30年投影", 0.022),
         ("成長型経済移行", 0.032), ("高成長実現", 0.034))
SEX = {0: "男女平均", 1: "男", 2: "女"}


def _qx():
    """{(性, 年): [年齢別の死亡率]}。性 1=男 2=女。ファイルは10万人あたりで、男・女の順に年が並ぶ。"""
    rows = list(csv.reader(open(suuri_env.suuri("nat", "base_data", "kisoritu", "QX-M2023.csv"))))[1:]
    half = len(rows) // 2
    out = {}
    for s, blk in ((1, rows[:half]), (2, rows[half:])):
        for r in blk:
            out[(s, 2000 + int(r[0]))] = [float(v) / 1e5 for v in r[1:]]
    return out


Q = _qx()
YMAX = max(y for _, y in Q)


def surv(s, a0, birth=BIRTH):
    """a0歳で生きている人の、各年齢の年初の生存率。s=0 は男女の単純平均。"""
    if s == 0:
        m, f = surv(1, a0, birth), surv(2, a0, birth)
        return {a: (m[a] + f[a]) / 2 for a in m}
    l = {a0: 1.0}
    for a in range(a0, AMAX):
        qa = Q[(s, min(birth + a, YMAX))]
        l[a + 1] = l[a] * (1 - (qa[a] if a < len(qa) else 1.0))
    return l


def yomei(l, a0):
    return sum((l[a] + l[a + 1]) / 2 for a in range(a0, AMAX))


def pv(l, start, ref, r, idx=None):
    """ref歳から見た、start歳から受け取る年金（年額1）の生命年金現価。idx は年齢→実質の給付の指数。"""
    v = 1 / (1 + r)
    return sum((l[a] + l[a + 1]) / 2 * v ** (a + 0.5 - ref) * (idx[a] if idx else 1.0)
               for a in range(start, AMAX))


def churitsu(s, r, idx=None):
    """中立になる1か月あたりの率。{('繰下げ', 70): 率, ...}"""
    l65, l60 = surv(s, 65), surv(s, 60)
    out = {}
    for x in (70, 75):
        out[("繰下げ", x)] = (pv(l65, 65, 65, r, idx) / pv(l65, x, 65, r, idx) - 1) / ((x - 65) * 12)
    out[("繰上げ", 60)] = (1 - pv(l60, 65, 60, r, idx) / pv(l60, 60, 60, r, idx)) / (5 * 12)
    return out


def mochidashi(s, r, idx=None, zou=0.007, gen=0.004):
    """今の率（＋0.7%・▲0.4%）で受給開始を選んだ人1人あたりの、財政の持ち出し（%）。
    65歳から受け取る人の生命年金現価に対する割合。＋は本人が得（財政は持ち出し）。{受給開始年齢: %}"""
    l65, l60 = surv(s, 65), surv(s, 60)
    a65, b65 = pv(l65, 65, 65, r, idx), pv(l60, 65, 60, r, idx)
    out = {x: ((1 + zou * 12 * (x - 65)) * pv(l65, x, 65, r, idx) / a65 - 1) * 100 for x in range(66, 76)}
    out.update({x: ((1 - gen * 12 * (65 - x)) * pv(l60, x, 60, r, idx) / b65 - 1) * 100 for x in range(60, 65)})
    out[65] = 0.0
    return out


def slide(case, birth=BIRTH):
    """基礎年金のマクロ経済スライドによる目減り（65歳=1）。④の cuta を世代に沿って読む。出力が無ければ None。"""
    v = f"{case}-{case}-{case}-{case}"
    p = suuri_env.suuri("emp", "rslt", "ez_arev", "cutr", f"cuta-{v}-1120-000.csv")
    if not os.path.exists(p):
        return None
    cut = {}
    for line in open(p):
        f = [x for x in line.strip().split(",") if x.strip()]
        cut[int(float(f[0])) + 2000] = {63 + j: float(x) for j, x in enumerate(f[1:])}
    idx = {}
    for a in range(60, AMAX + 1):
        c = cut[max(min(birth + a, max(cut)), min(cut))]
        idx[a] = c.get(max(a, 63), c[max(c)])
    return {a: x / idx[65] for a, x in idx.items()}


def report():
    print(f"対象：{BIRTH}年度生まれ（{BIRTH + 65}年度に65歳）。死亡率は QX-M2023（死亡中位）を世代に沿って読む")
    for s in (0, 1, 2):
        print(f"  65歳の平均余命（{SEX[s]}）：{yomei(surv(s, 65), 65):.1f}年")
    print("\n■ 中立になる1か月あたりの率（男女平均）")
    print("割引率                    繰下げ70歳  繰下げ75歳  繰上げ60歳")
    for name, r in RATES:
        c = churitsu(0, r)
        print(f"{name:12s} {r * 100:4.1f}%     {c[('繰下げ', 70)] * 100:.2f}%      {c[('繰下げ', 75)] * 100:.2f}%      "
              f"{c[('繰上げ', 60)] * 100:.2f}%")
    print("今の制度                     0.70%      0.70%      0.40%")

    rows = [(f"{name} {r * 100:.1f}%", r, None) for name, r in RATES]
    for case, name, r in (("3003", "過去30年投影", 0.022), ("3001", "高成長実現", 0.034)):
        idx = slide(case)
        if idx:
            rows.append((f"{name} {r * 100:.1f}%＋基礎年金のスライド", r, idx))
            c0, c1 = churitsu(0, r), churitsu(0, r, idx)
            print(f"  スライド込み（{name}）：繰下げ70歳 {c0[('繰下げ', 70)] * 100:.2f}%→{c1[('繰下げ', 70)] * 100:.2f}%、"
                  f"75歳 {c0[('繰下げ', 75)] * 100:.2f}%→{c1[('繰下げ', 75)] * 100:.2f}%、"
                  f"繰上げ60歳 {c0[('繰上げ', 60)] * 100:.2f}%→{c1[('繰上げ', 60)] * 100:.2f}%")

    print("\n■ 今の率で選んだ人1人あたりの財政の持ち出し（%、男女平均。＋は本人が得）")
    xs = (60, 62, 64, 66, 68, 70, 72, 75)
    print("前提" + "".join(f"{x:>8d}" for x in xs))
    for lab, r, idx in rows:
        m = mochidashi(0, r, idx)
        print(f"{lab:32s}" + "".join(f"{m[x]:+8.1f}" for x in xs))

    print("\n■ 男女別（過去30年投影 2.2%）")
    for s in (1, 2):
        m, c = mochidashi(s, 0.022), churitsu(s, 0.022)
        print(f"{SEX[s]}：持ち出し 繰下げ70歳 {m[70]:+.1f}%、75歳 {m[75]:+.1f}%、繰上げ60歳 {m[60]:+.1f}%"
              f" ／ 中立な率 繰下げ70歳 {c[('繰下げ', 70)] * 100:.2f}%、75歳 {c[('繰下げ', 75)] * 100:.2f}%、"
              f"繰上げ {c[('繰上げ', 60)] * 100:.2f}%")


NOTE = ("非公式：厚生労働省の試算ではない。2024年財政検証の計算プログラムの入力（死亡率・経済前提）から、"
        "厚労省（2019年年金部会資料）と同じ生命年金現価の式で推定。"
        f"{BIRTH}年度生まれ・男女平均。年金は年央払いで近似。加給年金・遺族年金・在職停止・自己選択は入れていない。")


def graph():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "IPAPGothic"
    xs = list(range(60, 76))
    # 割引率は大きさの違いなので、同じ色相の濃淡で表す（低い利回りほど薄く）
    blues = ("#9ec5e8", "#6aa4d8", "#2f6fb3", "#1d4f8c", "#0b2f5e")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1.35, 1]})
    a = axes[0]
    for (name, r), c in zip(RATES, blues):
        m = mochidashi(0, r)
        a.plot(xs, [m[x] for x in xs], color=c, lw=2, marker="o", ms=4, label=f"{name}（実質{r * 100:.1f}%）")
    idx = slide("3003")
    if idx:
        m = mochidashi(0, 0.022, idx)
        a.plot(xs, [m[x] for x in xs], color="#2f6fb3", lw=2, ls="--", marker="o", ms=4, mfc="white",
               label="過去30年投影＋基礎年金のスライド")
    a.axhline(0, color="#333", lw=0.8)
    a.axvline(65, color="#999", lw=0.6, ls=":")
    a.set_xticks(xs[::1], [str(x) if x % 5 == 0 or x in (68, 72) else "" for x in xs])
    a.set_xlabel("受給開始年齢（歳）")
    a.set_ylabel("財政の持ち出し（65歳受給の生命年金現価に対する%）")
    a.set_title("今の率（繰上げ▲0.4%・繰下げ＋0.7%／月）で選んだ人1人あたり（男女平均）", fontsize=11)
    a.text(60.2, a.get_ylim()[1] * 0.92, "＋：本人が得・財政は持ち出し\n−：財政が得", fontsize=9, color="#444", va="top")
    a.grid(axis="y", color="#e5e5e5", lw=0.6)
    a.legend(fontsize=8.5, frameon=False, loc="lower left")

    b = axes[1]
    for s, c in ((1, "#1d4f8c"), (2, "#c2410c"), (0, "#777777")):
        m = mochidashi(s, 0.022)
        b.plot(xs, [m[x] for x in xs], color=c, lw=2, marker="o", ms=4, label=SEX[s])
        b.annotate(SEX[s], (75, m[75]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=9, color=c)
    b.axhline(0, color="#333", lw=0.8)
    b.axvline(65, color="#999", lw=0.6, ls=":")
    b.set_xticks(xs, [str(x) if x % 5 == 0 or x in (68, 72) else "" for x in xs])
    b.set_xlim(59.5, 78)
    b.set_xlabel("受給開始年齢（歳）")
    b.set_title("男女別（過去30年投影、実質2.2%）", fontsize=11)
    b.grid(axis="y", color="#e5e5e5", lw=0.6)
    fig.suptitle("繰上げ・繰下げは年金財政に中立か（非公式の推定）", fontsize=13, y=0.99)
    fig.text(0.01, 0.005, NOTE, fontsize=7.5, color="#555", va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    out = os.path.join(HERE, "図", "繰上げ繰下げ_財政の持ち出し.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print(out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": report, "graph": graph}[cmd]()
