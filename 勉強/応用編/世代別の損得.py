#!/usr/bin/env python3
"""厚生年金の国庫負担を廃止して一律給付にしたら（財政均衡）：世代ごとの損得と給付負担倍率（思考実験・非公式・推定）。

「厚生年金の国庫負担を廃止して一律給付にしたら」「…国民全員に一律給付したら」の2案（予備番号701）を、
生まれた年度ごとに現行制度（000）と比べる。計算プログラムは流し直さず、出力を集計する。

  受給総額：65歳以降に受け取る年金（＋一律給付）を、生存率で重み付けして65歳時点の価値にしたもの。
            全員に配る案は、0〜64歳の一律給付も65歳まで運用して足す。2024年度の物価に割り戻す
  保険料  ：20〜59歳の40年間の保険料を65歳まで積み上げたもの（2004年度以降に生まれた世代だけ）
  換算    ：年金と同じ運用利回り（実質）か、賃金上昇率（実質）。経済前提ファイルの値

  3つの世帯
    会社員40年の単身（男）：報酬比例（平均的な賃金で40年）＋基礎年金（満額）＋一律給付
    基礎年金だけの単身    ：基礎年金（満額）＋一律給付。生存率は男女計
    夫婦                  ：会社員の夫＋同い年の専業の妻。夫が先に亡くなれば妻に遺族厚生年金（報酬比例の3/4）

使い方（リポジトリの直下で。通常試算 000 と、国庫負担の廃止.py run の 701 が要る）
  python3 勉強/応用編/世代別の損得.py report     # 記事の表
  python3 勉強/応用編/世代別の損得.py graph      # 記事の図（勉強/応用編/図/）
"""
import csv
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fname):
    s = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


K = _load("kokko", "国庫負担の廃止.py")
M = _load("mangaku", "全員に満額.py")
AN = M.K.Z._mods()[2]                       # 検証/3号廃止/analyze_sango.py
CO, _ = K._modules()
SUURI, SH = K.SUURI, K.SH
START = 2027
AGE_MAX = 99                                # 99歳まで受け取るとする（100歳以上は数えない）
Y_END = 2200
COHORTS = range(1940, 2101)
HOKEN_FROM = 2004                           # 20〜59歳が全部2024年度以降になる最初の生年度
CASES = (("3003", "過去30年投影"), ("3001", "高成長実現"))
RATES = (("chingin", "賃金上昇率"), ("unyo", "運用利回り"))
TYPES = (("tanshin", "会社員40年の単身（男）"), ("fufu", "夫婦（会社員の夫＋専業の妻）"), ("kiso", "基礎年金だけの単身"))
PLANS = (("genkou", "現行制度"), ("65", "65歳以上に一律給付"), ("zenin", "全員に一律給付"))
_CACHE = {}


def _series(case, rate):
    v = f"{case}-{case}-{case}-{case}"
    rb, rc = CO.read_rate(v, "000", SH), CO.read_rate(v, "701", SH)
    kw = K.tedori(case, "000")                                   # 年度: (名目, 実質)
    cut = 1 - rc[2060]["代替率(比例)"] / rb[2060]["代替率(比例)"]  # 報酬比例の一律削減率
    econ = {int(float(l.split(",")[0])) + 2000: [float(x) for x in l.split(",")]
            for l in open(os.path.join(SUURI, "emp", "data", "u-rev", "econ", f"econ-{case}.csv"))}
    # 物価指数・実質手取り。2023年度以前は出力が無いので2024年度の実質額で代用する（推定）
    P = {y: (kw[y][0] / kw[y][1] if y >= 2024 else 1.0) for y in kw}
    TR = {y: kw[max(y, 2024)][1] for y in kw}
    ylast = max(kw)
    gw = TR[ylast] / TR[ylast - 1]                               # 最終年度の実質賃金の伸び。これで延ばす
    for y in range(ylast + 1, Y_END + 2):
        TR[y] = TR[y - 1] * gw
    col = 1 if rate == "unyo" else 3                             # 1: 運用利回り（実質）、3: 賃金上昇率（実質）
    R = {y: econ.get(y, econ[max(econ)])[col] / 100 for y in range(1900, Y_END + 2)}
    # 年齢別の基礎年金（満額・実質・年額）。2120年度より後は、67歳以下は賃金、68歳以上は物価で延ばす
    F = M.mangaku(case)
    C = M._read_cut(os.path.join(SUURI, "bas", "rslt", f"cuta-{v}-1120-000.csv"))
    KISO = {}
    for y in range(2005, Y_END + 1):
        for a in range(65, AGE_MAX + 1):
            if y <= 2120:
                yy = max(y, 2024)
                KISO[a, y] = F[yy][min(a, 115)] * C[yy][min(a, 115)] / P[yy]
            elif a <= 67:
                KISO[a, y] = KISO[a, y - 1] * gw
            else:
                KISO[a, y] = KISO[a - 1, y - 1]
    yr = max(rb)

    def hirei(Y65):
        """65歳でもらい始める報酬比例（実質・年額）。以後は実質一定とする（推定）"""
        Y = min(max(Y65, 2024), yr)
        base = rb[Y]["代替率(比例)"] * TR[Y] * 12
        return base * (TR[Y65] / TR[Y]) if Y65 > yr else base

    ichi = {}
    for who in ("65", "zenin"):
        s = K.shinkyufu(case, who)
        ichi[who] = {y: (s[y]["getsu"] / P[y] * 12 if y <= 2120 else s[2120]["wari"] / 100 * TR[y] * 12)
                     for y in range(START, Y_END + 1)}
    # 保険料（実質・月額）。会社員の標準報酬（ボーナス込み）は⑤のモデル年金の報酬比例から逆算する
    #   比例（月額）× 12 ÷ 比例カット67 ÷（5.481/1000 × 480）
    p = CO.find_one(f"03summary.{v}-1120-000*_08sum.csv", SH)
    W = {}
    for l in CO.lines_of(p)[11:]:
        f = [x.strip() for x in l.split(",")]
        if not f[0].isdigit():
            break
        y = 2000 + int(f[0])
        if y >= 2024:
            W[y] = float(f[9]) * 12 / float(f[16]) / (0.005481 * 480) / P[y]
    run = AN.load_run(SUURI, case, "000", "000")
    kb = AN.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{v}-1120-000a.csv"))
    kai = AN.series(kb["収支見通し"], "保険料改定率")
    KN = {y: run["hoken_m"][y] * kai[y] / P[y] for y in range(2024, 2121)}
    for y in range(max(W) + 1, Y_END + 1):
        W[y] = W[y - 1] * gw
    for y in range(2121, Y_END + 1):
        KN[y] = KN[y - 1] * gw
    return dict(R=R, KISO=KISO, hirei=hirei, ichi=ichi, cut=cut, W=W, KN=KN)


def _survival(case):
    """{性: 関数(年齢, 年度) → 前の年からの生存率}。①の人口（0計・1男・2女）の比から作る。
    2022年度より前は2022年度、2125年度より後は2125年度の率を使う。"""
    p = os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", f"rslt{case}", f"waku{case}-20.csv")
    L = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    h = L[1]
    pop = {}
    for r in L[2:]:
        if len(r) > 5 and r[1] in ("0", "1", "2"):
            for j in range(4, len(h)):
                if h[j].strip().isdigit() and r[j].strip():
                    pop[r[1], int(h[j]), int(r[2])] = float(r[j])
    out = {}
    for sx in ("0", "1", "2"):
        q = {(a, y): min(1.0, pop[sx, a, y] / pop[sx, a - 1, y - 1])
             for a in range(66, AGE_MAX + 1) for y in range(2022, 2126)}
        out[sx] = lambda a, y, q=q: q[a, min(max(y, 2022), 2125)]
    return out


def keisan(case, rate):
    """{生年度: {"genkou"/"65"/"zenin": {世帯: 万円}, "hoken": {"kounen": 万円, "kokunen": 万円}}}"""
    if (case, rate) in _CACHE:
        return _CACHE[case, rate]
    S, SV = _series(case, rate), _survival(case)
    R = S["R"]
    out = {}
    for c in COHORTS:
        Y65 = c + 65
        hb = S["hirei"](Y65)
        res = {p: dict(tanshin=0.0, fufu=0.0, kiso=0.0) for p, _ in PLANS}
        # 全員に配る案の、0〜64歳の一律給付（本人の名義として数える）を65歳まで運用
        pre = 0.0
        for a in range(65):
            pre = (pre + S["ichi"]["zenin"].get(c + a, 0.0)) * (1 + R[c + a + 1])
        res["zenin"]["tanshin"] += pre
        res["zenin"]["kiso"] += pre
        res["zenin"]["fufu"] += 2 * pre
        sm = sf = st = d = 1.0
        for a in range(65, AGE_MAX + 1):
            y = c + a
            if a > 65:
                sm *= SV["1"](a, y)
                sf *= SV["2"](a, y)
                st *= SV["0"](a, y)
                d /= 1 + R[y]
            kiso = S["KISO"][a, y]
            h1 = hb * (1 - S["cut"]) if y >= START else hb
            for p, h, ic in (("genkou", hb, 0.0), ("65", h1, S["ichi"]["65"].get(y, 0.0)),
                             ("zenin", h1, S["ichi"]["zenin"].get(y, 0.0))):
                res[p]["tanshin"] += d * sm * (h + kiso + ic)
                res[p]["kiso"] += d * st * (kiso + ic)
                res[p]["fufu"] += d * (sm * (h + kiso + ic) + sf * (kiso + ic) + sf * (1 - sm) * 0.75 * h)
        o = {p: {k: x / 1e4 for k, x in v.items()} for p, v in res.items()}
        if c >= HOKEN_FROM:
            pk = pn = 0.0
            for a in range(20, 65):
                y = c + a
                if a < 60:
                    pk += 0.183 * S["W"][y] * 12
                    pn += S["KN"][y] * 12
                pk *= 1 + R[y + 1]
                pn *= 1 + R[y + 1]
            o["hoken"] = dict(kounen=pk / 1e4, kokunen=pn / 1e4)
        out[c] = o
    _CACHE[case, rate] = out
    return out


def bairitsu(o, plan, typ, roushi=False):
    """給付負担倍率。会社員・夫婦は厚生年金保険料の本人負担分（roushi=True なら労使計）、基礎年金だけは国民年金保険料で割る"""
    h = o["hoken"]["kokunen"] if typ == "kiso" else o["hoken"]["kounen"] * (1 if roushi else 0.5)
    return o[plan][typ] / h


def report():
    pc = lambda o, p, k: f"{o[p][k] - o['genkou'][k]:+,.0f}（{100 * (o[p][k] / o['genkou'][k] - 1):+.1f}%）"
    for rate, rname in RATES:
        print(f"# 換算：{rname}\n")
        for case, cname in CASES:
            r = keisan(case, rate)
            print(f"## {cname}：受給総額の増減（万円、現行比）\n")
            print("| 生まれた年度（65歳になる年度） | 現行の受給総額（単身／夫婦／基礎だけ） | 65歳以上案：単身／夫婦／基礎だけ | 全員案：単身／夫婦／基礎だけ |")
            print("|---|---|---|---|")
            for c in (1940, 1950, 1959, 1962, 1970, 1980, 1995, 2010, 2030):
                o = r[c]
                print(f"| {c}（{c + 65}） | {o['genkou']['tanshin']:,.0f}／{o['genkou']['fufu']:,.0f}／{o['genkou']['kiso']:,.0f} | "
                      + "／".join(pc(o, "65", k) for k, _ in TYPES) + " | "
                      + "／".join(pc(o, "zenin", k) for k, _ in TYPES) + " |")
            print(f"\n## {cname}：給付負担倍率（2030年度生まれ。本人負担分で割る）\n")
            print("| 世帯 | 現行制度 | 65歳以上案 | 全員案 | （参考）労使計で割った現行 |")
            print("|---|---|---|---|---|")
            o = r[2030]
            for k, kn in TYPES:
                print(f"| {kn} | " + " | ".join(f"{bairitsu(o, p, k):.2f}" for p, _ in PLANS)
                      + f" | {bairitsu(o, 'genkou', k, True):.2f} |")
            print(f"\n保険料（65歳時点の価値）：厚生年金（労使計）{o['hoken']['kounen']:,.0f}万円、国民年金 {o['hoken']['kokunen']:,.0f}万円\n")


def _fig_base():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "IPAPGothic"
    return matplotlib, plt


COL_T = {"tanshin": "#eb6834", "fufu": "#2a78d6", "kiso": "#1baf7a"}
COL_P = {"genkou": "#8c8c8c", "65": "#2a78d6", "zenin": "#eb6834"}
NOTE = ("非公式：2024年財政検証の計算プログラムに独自のレバーを加えた試算の出力から推定。厚生労働省の試算ではない。"
        "受給総額は65歳以降の年金＋一律給付（全員案は0〜64歳の分を65歳まで運用して足す）を、将来推計人口から作った生存率で重み付けし、"
        "65歳時点の価値（2024年度の物価）にしたもの。")


def _end_labels(a, x, items, gap_frac=0.045):
    """線の終点に数字を置く。縦に近すぎる数字は上下にずらす。items = [(値, 文字, 色)]"""
    lo, hi = a.get_ylim()
    gap = (hi - lo) * gap_frac
    placed = []
    for v, s, c in sorted(items):
        y = v
        for p in placed:
            if abs(y - p) < gap:
                y = p + gap
        placed.append(y)
        a.annotate(s, (x, v), xytext=(x, y), textcoords="data", va="center", fontsize=8.5, color=c,
                   annotation_clip=False)


def _note(fig, text, width=None):
    import textwrap
    width = width or int(fig.get_figwidth() * 8.2)        # 7.5pt の全角が1行に入る数の目安
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, width) or [""]
    fig.text(0.01, 0.006, "\n".join(lines), fontsize=7.5, color="#555", va="bottom")
    return len(lines)


def _secx(a):
    sec = a.secondary_xaxis("top", functions=(lambda x: x + 65, lambda x: x - 65))
    sec.tick_params(labelsize=8)


def graph():
    matplotlib, plt = _fig_base()
    out = os.path.join(HERE, "図")
    # 図1・図2：受給総額の増減（割合・金額）。運用利回りで換算
    for kind in ("wariai", "kingaku"):
        fig, ax = plt.subplots(2, 2, figsize=(13, 10), sharex=True, sharey=(kind == "wariai"))
        c_end = 2100 if kind == "wariai" else 2060
        ends = {}
        for i, (case, cname) in enumerate(CASES):
            r = keisan(case, "unyo")
            cs = [c for c in COHORTS if c <= c_end]
            lo = hi = 0.0
            for j, plan in enumerate(("65", "zenin")):
                a = ax[i][j]
                a.axvspan(2055, c_end + 12, color="#f2f2f2", zorder=0)
                ends[i, j] = []
                for k, kn in (TYPES[2], TYPES[1], TYPES[0]):
                    if kind == "wariai":
                        v = [100 * (r[c][plan][k] / r[c]["genkou"][k] - 1) for c in cs]
                        lab = f"{v[-1]:+.0f}%"
                    else:
                        v = [r[c][plan][k] - r[c]["genkou"][k] for c in cs]
                        lab = f"{v[-1]:+,.0f}万"
                    lo, hi = min(lo, min(v)), max(hi, max(v))
                    a.plot(cs, v, color=COL_T[k], lw=2, label=kn)
                    ends[i, j].append((v[-1], lab, COL_T[k]))
                a.axhline(0, color="#888", lw=0.8)
                a.axvline(1962, color="#999", lw=0.8, ls=":")
                a.set_title(f"{cname}（報酬比例 −{_series_cut(case) * 100:.1f}%）\n"
                            + ("65歳以上に一律給付" if plan == "65" else "国民全員（0歳から）に一律給付（65歳までの分は運用して足す）"),
                            fontsize=10)
                a.grid(True, color="#ddd", lw=0.6)
                a.spines[["top", "right"]].set_visible(False)
                a.set_xlim(1938, c_end + 12)
                _secx(a)
                a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))
                if i == 1:
                    a.set_xlabel("生まれた年度（上の目盛りは65歳になる年度）")
                if j == 0:
                    a.set_ylabel("受給総額の増減（現行比、%）" if kind == "wariai" else "受給総額の増減（万円、65歳時点・今の物価）")
            if kind == "kingaku":
                pad = (hi - lo) * 0.08
                for j in range(2):
                    ax[i][j].set_ylim(lo - pad, hi + pad)
        if kind == "wariai":
            ax[0][0].set_ylim(-25, 125)
        for (i, j), items in ends.items():
            _end_labels(ax[i][j], c_end + 1.5, items)
        h, l = ax[0][0].get_legend_handles_labels()
        fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.95))
        fig.suptitle("厚生年金の国庫負担を廃止して一律給付（財政均衡）：世代ごとの損得"
                     + ("（現行比）" if kind == "wariai" else "（金額）") + "（非公式の思考実験）", fontsize=12, y=0.985)
        _note(fig, NOTE + "\n年金と同じ実質の運用利回りで換算。点線は1962年度生まれ（2027年度に65歳）。網かけは65歳以降が全部2120年度より後（延長した推定）。"
              + ("上下の段で縦軸の目盛りが違う。" if kind == "kingaku" else ""))
        fig.tight_layout(rect=(0, 0.06, 1, 0.93))
        name = os.path.join(out, f"世代別の損得_{'割合' if kind == 'wariai' else '金額'}.png")
        fig.savefig(name, dpi=150, facecolor="white")
        plt.close(fig)
        print("書き出し:", name)
    # 図3：給付負担倍率（2030年度生まれ）。上段が賃金上昇率、下段が運用利回りで換算
    import numpy as np
    fig, ax = plt.subplots(2, 2, figsize=(13, 10), sharey=True)
    for i, (rate, rname) in enumerate(RATES):
        for j, (case, cname) in enumerate(CASES):
            a, o, x, w = ax[i][j], keisan(case, rate)[2030], np.arange(3), 0.26
            for n, (p, pn) in enumerate(PLANS):
                vals = [bairitsu(o, p, k) for k, _ in TYPES]
                bars = a.bar(x + (n - 1) * w, vals, w - 0.02, color=COL_P[p], label=pn if p == "genkou" else f"国庫負担廃止＋{pn}")
                for b, v in zip(bars, vals):
                    a.text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.2f}", ha="center", fontsize=8.5, color="#333")
            a.set_xticks(x, ["会社員40年の単身（男）", "夫婦（会社員の夫＋専業の妻）", "基礎年金だけの単身"], fontsize=8.5)
            a.set_title(f"{cname}：{rname}で換算", fontsize=11)
            a.axhline(1, color="#888", lw=0.8, ls=":")
            a.grid(True, axis="y", color="#ddd", lw=0.6)
            a.spines[["top", "right"]].set_visible(False)
            if j == 0:
                a.set_ylabel("給付負担倍率（倍）")
    ax[0][0].set_ylim(0, 4.2)
    h, l = ax[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.95))
    fig.suptitle("給付負担倍率（2030年度生まれ）：現行制度と、国庫負担を廃止して一律給付にした2案（財政均衡）（非公式の思考実験）",
                 fontsize=12, y=0.985)
    _note(fig, NOTE + "\n負担は20〜59歳の40年間の保険料の本人負担分（夫婦は夫の分、基礎年金だけは国民年金保険料）。"
          "事業主負担を含めると会社員・夫婦の倍率は半分になる。")
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    name = os.path.join(out, "給付負担倍率_2030年度生まれ.png")
    fig.savefig(name, dpi=150, facecolor="white")
    plt.close(fig)
    print("書き出し:", name)
    # 図4：給付負担倍率の世代ごとの推移（2004〜2100年度生まれ）。換算ごとに1枚
    for rate, rname in RATES:
        fig, ax = plt.subplots(2, 3, figsize=(14, 9), sharex=True, sharey=True)
        for i, (case, cname) in enumerate(CASES):
            r = keisan(case, rate)
            cs = [c for c in COHORTS if c >= HOKEN_FROM]
            for j, (k, kn) in enumerate(TYPES):
                a = ax[i][j]
                a.axvspan(2055, 2112, color="#f2f2f2", zorder=0)
                items = []
                for p, pn in PLANS:
                    v = [bairitsu(r[c], p, k) for c in cs]
                    a.plot(cs, v, color=COL_P[p], lw=2, label=pn if p == "genkou" else f"国庫負担廃止＋{pn}")
                    items.append((v[-1], f"{v[-1]:.2f}", COL_P[p]))
                a.set_ylim(0, 4.0)
                _end_labels(a, cs[-1] + 1.5, items, 0.05)
                a.axhline(1, color="#888", lw=0.8, ls=":")
                a.set_title(f"{cname}\n{kn}", fontsize=10)
                a.grid(True, color="#ddd", lw=0.6)
                a.spines[["top", "right"]].set_visible(False)
                a.set_xlim(2000, 2112)
                _secx(a)
                if i == 1:
                    a.set_xlabel("生まれた年度")
                if j == 0:
                    a.set_ylabel("給付負担倍率（倍）")
        ax[0][0].set_ylim(0, 4.0)
        h, l = ax[0][0].get_legend_handles_labels()
        fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.94))
        fig.suptitle(f"給付負担倍率の世代ごとの推移（{rname}で換算）：現行制度と2案（財政均衡）（非公式の思考実験）", fontsize=12, y=0.985)
        _note(fig, NOTE + "\n負担は20〜59歳の保険料の本人負担分。2004年度以降に生まれた世代（保険料が全部2024年度以降）だけ。"
              "網かけは65歳以降が全部2120年度より後（延長した推定）。")
        fig.tight_layout(rect=(0, 0.06, 1, 0.92))
        name = os.path.join(out, f"給付負担倍率_世代別_{rname}.png")
        fig.savefig(name, dpi=150, facecolor="white")
        plt.close(fig)
        print("書き出し:", name)


def _series_cut(case):
    v = f"{case}-{case}-{case}-{case}"
    rb, rc = CO.read_rate(v, "000", SH), CO.read_rate(v, "701", SH)
    return 1 - rc[2060]["代替率(比例)"] / rb[2060]["代替率(比例)"]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"report": report, "graph": graph}[cmd]()
