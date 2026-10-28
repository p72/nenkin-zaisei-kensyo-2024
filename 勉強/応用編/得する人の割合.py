#!/usr/bin/env python3
"""厚生年金の国庫負担を廃止して国民全員に一律給付したら（財政均衡）：得をする人の割合と、世代内・世代間の再分配（思考実験・非公式・推定）。

厚生労働省「年金額の分布推計」（2024年財政検証 関連資料。65歳時点の老齢年金月額の分布、物価で2024年度に
割り戻した実質額、生年度×男女×7区分）に、「…国民全員に一律給付したら」の案（予備番号701）の損得を当てはめる。
分布推計が出ているのは成長型経済移行・継続（3002）と過去30年投影（3003）の2つなので、その2つで計算する。

  一人ひとりの年金月額 T のうち、基礎年金の満額（その世代の65歳時点）までを基礎年金、残りを報酬比例とみなす
  損得（65歳時点の価値・万円）＝ 一律給付（0〜64歳の分は年金と同じ実質の運用利回りで65歳まで運用）
                               − 報酬比例のカット（報酬比例 × カット率 × 生命年金現価率）
  区分の中は一様に分布しているとし、25万円以上の区分は25〜35万円に一様とおく
  生存率・一律給付・カット率・利回りは 世代別の損得.py と同じ。個人単位で、配偶者の遺族厚生年金は入れていない
  男女計は、公表の男女計の分布に合うように男女を重み付ける（最小二乗。ほぼ半々になる）

使い方（リポジトリの直下で）
  ./fetch.sh                                            # papers/001270447/（年金額の分布推計.xlsx）を取得
  検証/実行/run_pipeline.sh 3003 1 1 0 2 && 検証/実行/run_pipeline.sh 3002
  python3 勉強/応用編/国庫負担の廃止.py run 3003 && python3 勉強/応用編/国庫負担の廃止.py run 3002
  python3 勉強/応用編/得する人の割合.py report          # 記事の表
  python3 勉強/応用編/得する人の割合.py graph           # 記事の図（勉強/応用編/図/）

openpyxl が要る（pip install openpyxl）。
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
XLSX = os.path.join(ROOT, "papers", "001270447", "財政検証関連資料", "05年金額の分布推計", "年金額の分布推計.xlsx")
SHEET = "老齢年金の年金月額分布（現行制度）"
EDGES = (0, 5, 7, 10, 15, 20, 25, 35)        # 万円。25万円以上は35万円まで
CASES = (("3003", "過去30年投影"), ("3002", "成長型経済移行・継続"))
COHORTS = tuple(range(1959, 2005, 5))
# 公表表の列：成長型の男女計の7区分が7列目から、男16列目、女25列目。過去30年投影は30列あと
COL = {"計": 6, "男": 15, "女": 24}
OFFSET = {"3002": 0, "3003": 30}


def _load(name, fname):
    s = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


G = _load("sedai", "世代別の損得.py")


def bunpu():
    """{(試算番号, 生年度, "計"/"男"/"女"): [7区分の割合]}"""
    import openpyxl
    ws = openpyxl.load_workbook(XLSX, data_only=True)[SHEET]
    out = {}
    for r in ws.iter_rows(values_only=True):
        if not r[0] or "年度生" not in str(r[0]):
            continue
        c = int(str(r[0])[:4])
        for case, off in OFFSET.items():
            for sx, col in COL.items():
                out[case, c, sx] = [float(x) for x in r[off + col:off + col + 7]]
    return out


def _bins(p, f, n=400):
    """区分の中を一様分布として、関数 f（年金月額 → 損得）の期待値を、得の分・損の分・得をする人の割合に分けて返す。"""
    mean = gain = loss = share = 0.0
    for w, lo, hi in zip(p, EDGES[:-1], EDGES[1:]):
        for i in range(n):
            v = f(lo + (hi - lo) * (i + 0.5) / n)
            mean += w * v / n
            if v > 0:
                gain += w * v / n
                share += w / n
            else:
                loss += w * v / n
    return dict(mean=mean, gain=gain, loss=loss, share=share)


def keisan(case):
    """{生年度: {"男"/"女"/"計": dict(mean, gain, loss, share, thr, T)}, "kiso": 万円}} とカット率"""
    P = bunpu()
    S, SV = G._series(case, "unyo"), G._survival(case)
    R, cut = S["R"], S["cut"]
    res = {}
    for c in COHORTS:
        pre = 0.0
        for a in range(65):
            pre = (pre + S["ichi"]["zenin"].get(c + a, 0.0)) * (1 + R[c + a + 1])
        kiso = S["KISO"][65, c + 65] / 12 / 1e4          # 基礎年金の満額（65歳・実質・月額・万円）
        o = {"kiso": kiso}
        for sx, key in (("男", "1"), ("女", "2")):
            s = d = 1.0
            bi = ann = 0.0
            for a in range(65, G.AGE_MAX + 1):
                y = c + a
                if a > 65:
                    s *= SV[key](a, y)
                    d /= 1 + R[y]
                bi += d * s * S["ichi"]["zenin"].get(y, 0.0)
                if y >= G.START:
                    ann += d * s * 12
            b = (pre + bi) / 1e4                          # 一律給付の価値（万円）
            f = lambda t, b=b, ann=ann: b - cut * ann * max(t - kiso, 0.0)   # noqa: E731
            r = _bins(P[case, c, sx], f)
            r["thr"] = b / (cut * ann)                    # 損得がつり合う報酬比例（月額・万円）
            r["T"] = kiso + r["thr"]                      # つり合う年金月額
            o[sx] = r
        pm, pf, pt = P[case, c, "男"], P[case, c, "女"], P[case, c, "計"]
        w = sum((t - f) * (m - f) for m, f, t in zip(pm, pf, pt)) / sum((m - f) ** 2 for m, f in zip(pm, pf))
        o["計"] = {k: w * o["男"][k] + (1 - w) * o["女"][k] for k in ("mean", "gain", "loss", "share")}
        o["計"]["w"] = w
        res[c] = o
    return res, cut


def report():
    for case, cname in CASES:
        r, cut = keisan(case)
        print(f"## {cname}（報酬比例 −{cut * 100:.1f}%）\n")
        print("| 生まれた年度（65歳になる年度） | 得をする人：男女計 | 男性 | 女性 | 損得がつり合う年金月額（男／女） |")
        print("|---|---|---|---|---|")
        for c in COHORTS:
            o = r[c]
            print(f"| {c}（{c + 65}） | {o['計']['share'] * 100:.0f}% | {o['男']['share'] * 100:.0f}% | {o['女']['share'] * 100:.0f}% | "
                  f"{o['男']['T']:.1f}万円／{o['女']['T']:.1f}万円 |")
        print("\n| 生まれた年度 | 男女計の平均（万円） | 男性の平均 | 女性の平均 | 得をする人の分 | 損をする人の分 | 得をする人1人あたり | 損をする人1人あたり |")
        print("|---|---|---|---|---|---|---|---|")
        for c in COHORTS:
            o = r[c]
            t = o["計"]
            pw = t["gain"] / t["share"] if t["share"] > 0 else 0.0
            pl = t["loss"] / (1 - t["share"]) if t["share"] < 1 else 0.0
            print(f"| {c} | {t['mean']:+,.0f} | {o['男']['mean']:+,.0f} | {o['女']['mean']:+,.0f} | "
                  f"{t['gain']:+,.0f} | {t['loss']:+,.0f} | {pw:+,.0f} | {pl:+,.0f} |")
        print()


NOTE = ("非公式：厚生労働省の試算ではない。厚労省「年金額の分布推計」（2024年財政検証 関連資料。65歳時点の老齢年金月額の分布、物価で2024年度に割り戻し）に、"
        "独自のレバー（国庫負担の廃止と報酬比例の一律カット）の損得を当てはめた推定。年金月額のうち基礎年金の満額までを基礎年金、残りを報酬比例とみなす。"
        "損得は一律給付（0〜64歳の分は年金と同じ実質の運用利回りで65歳まで運用）と報酬比例のカットの、65歳時点の価値（2024年度の物価）の差。"
        "区分の中は一様分布、25万円以上は25〜35万円とした。個人単位で、配偶者の遺族厚生年金は入れていない。男女計は公表の男女計の分布に合うよう男女を重み付けた。")


def graph():
    matplotlib, plt = G._fig_base()
    fig, ax = plt.subplots(2, 2, figsize=(14, 11), sharex=True)
    col = {"計": "#333333", "男": "#2a78d6", "女": "#d9622b"}
    for j, (case, cname) in enumerate(CASES):
        r, cut = keisan(case)
        cs = list(COHORTS)
        a = ax[0][j]
        for sx, lab in (("男", "男性"), ("女", "女性"), ("計", "男女計")):
            v = [r[c][sx]["share"] * 100 for c in cs]
            a.plot(cs, v, color=col[sx], lw=2.4 if sx == "計" else 2, marker="o", ms=5, label=lab)
            for x, y, ha, dx in ((cs[0], v[0], "right", -6), (cs[-1], v[-1], "left", 6)):
                a.annotate(f"{y:.0f}%", (x, y), xytext=(dx, 0), textcoords="offset points", va="center", ha=ha,
                           fontsize=9.5, color=col[sx])
        a.axhline(50, color="#999", lw=0.8, ls=":")
        a.set_ylim(0, 105)
        a.set_title(f"{cname}（報酬比例 −{cut * 100:.1f}%）\n一生分で見て得をする人の割合", fontsize=11)
        if j == 0:
            a.set_ylabel("得をする人の割合（%）")
        b = ax[1][j]
        g = [r[c]["計"]["gain"] for c in cs]
        lo = [r[c]["計"]["loss"] for c in cs]
        m = [r[c]["計"]["mean"] for c in cs]
        b.bar(cs, g, width=3.2, color="#a9d8bd", label="得をする人の分（世代の全員で割った値）")
        b.bar(cs, lo, width=3.2, color="#f3c1ad", label="損をする人の分（同）")
        for sx, lab in (("男", "男性の平均"), ("女", "女性の平均")):
            b.plot(cs, [r[c][sx]["mean"] for c in cs], color=col[sx], marker="o", ms=4.5, lw=1.6, ls="--", label=lab)
        b.plot(cs, m, color="#111", marker="D", ms=6, lw=1.8, label="男女計の平均（世代全体の得・損）")
        for x, y in zip(cs, m):
            b.annotate(f"{y:+,.0f}", (x, y), xytext=(0, 9 if y >= 0 else -14), textcoords="offset points",
                       ha="center", fontsize=8.5, color="#111")
        b.axhline(0, color="#555", lw=0.9)
        b.set_title("1人あたりの損得（万円、65歳時点・今の物価）", fontsize=11)
        b.set_xlabel("生まれた年度（上の目盛りは65歳になる年度）")
        if j == 0:
            b.set_ylabel("万円")
        for a2 in (a, b):
            a2.set_xticks(cs, [str(c) for c in cs], fontsize=8.5)
            a2.set_xlim(1953, 2010)
            a2.grid(True, color="#ddd", lw=0.6)
            a2.spines[["top", "right"]].set_visible(False)
            G._secx(a2)
            a2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))
    h, l = ax[0][0].get_legend_handles_labels()
    h2, l2 = ax[1][0].get_legend_handles_labels()
    fig.legend(h + h2, l + l2, loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.955))
    fig.suptitle("厚生年金の国庫負担を廃止して国民全員に一律給付（財政均衡）：得をする人の割合と、世代内・世代間の再分配"
                 "（厚労省の年金額の分布推計で重み付け・非公式の推定）", fontsize=12, y=0.99)
    G._note(fig, NOTE)
    fig.tight_layout(rect=(0, 0.07, 1, 0.9))
    out = os.path.join(HERE, "図", "得する人の割合.png")
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print("書き出し:", out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": report, "graph": graph}[cmd]()
