#!/usr/bin/env python3
"""65歳以上の全員に基礎年金の満額を配り、マクロ経済スライドも止めたら（思考実験・非公式）。

設計
  - 2027年度から、65歳以上の全員に基礎年金の満額。納付期間は問わない（未納・免除・無年金も満額）
  - 基礎年金のマクロ経済スライドを2027年度から止める。2026年度までに下がった分はそのまま
  - 満額の改定は今のルールどおり（67歳以下は賃金、68歳以上は物価）
  - 保険料は現行のまま。増えた給付は全部、国庫負担を追加してまかなう。
    各制度が払う基礎年金拠出金（保険料でまかなう分）は現行のままなので、報酬比例も現行のまま

計算
  ① スライド停止：④に「2026年度のカット率を2027年度以降も据え置く」カット率ファイルを
     固定カット率（CUT_KOTEI=1）として読ませて流す（予備番号951）。⑤は流さない
  ② 全員に満額  ：65歳以上の年齢別人口（①の waku-20）× 年齢別の満額 × 12 から、
     ①で流した老齢基礎年金の給付費を引く（推定）。
     満額は③の値で組み立てる。67歳以下は ROREI の「基礎年金満額（基本額）」の列。
     68歳以上は、③がこの表の年齢の添字を 67 ずらして書く（検証/原本の不具合.md J4）ので、
     KOKUKAITE（生の年齢で書かれた単年度の改定率）で1年ずつ進めて作る
  追加の国庫 ＝（65歳以上の満額の合計＋障害・遺族の基礎年金（①））− 現行の基礎年金給付費

使い方（リポジトリの直下で。通常試算3001〜3003が要る）
  python3 勉強/応用編/全員に満額.py run            # ④を3ケース流す（予備番号951）
  python3 勉強/応用編/全員に満額.py check          # 固定カット率の経路が通常試算を再現するか
  python3 勉強/応用編/全員に満額.py report         # 表
  python3 勉強/応用編/全員に満額.py graph          # 図（勉強/応用編/図/）
"""
import csv
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
s = importlib.util.spec_from_file_location("kokusai", os.path.join(HERE, "基礎年金の赤字国債.py"))
K = importlib.util.module_from_spec(s)
s.loader.exec_module(K)
Z = K.Z
SUURI = Z.SUURI
START = 2027
YOBI = "951"
CASES = K.CASES
YEARS = (2027, 2030, 2040, 2050, 2060, 2080, 2100, 2120)


def _v(case):
    return f"{case}-{case}-{case}-{case}"


def _cutr(case, yobi):
    return os.path.join(SUURI, "emp", "rslt", "ez_arev", "cutr", f"cuta-{_v(case)}-1120-{yobi}.csv")


def _read_cut(path):
    """カット率ファイル。{年度: {年齢(63〜115): カット率}}"""
    out = {}
    for l in open(path):
        f = [x for x in l.strip().split(",") if x.strip()]
        out[int(float(f[0])) + 2000] = {63 + j: float(x) for j, x in enumerate(f[1:])}
    return out


def teishi_cut(case):
    """通常試算のカット率を、START 年度から据え置いたカット率ファイルを書く。
    67歳以下は前年度の67歳の値、68歳以上は前年度の1つ下の年齢の値（④の read_cut と同じ進め方）。"""
    src = os.path.join(SUURI, "bas", "rslt", f"cuta-{_v(case)}-1120-000.csv")
    lines = []
    prev = None
    for l in open(src):
        f = l.rstrip("\n").split(",")
        vals = [float(x) for x in f[1:]]
        if int(float(f[0])) + 2000 >= START:
            vals = [prev[67 - 63] if 63 + i <= 67 else prev[i - 1] for i in range(len(vals))]
        prev = vals
        lines.append(f[0] + "," + ",".join("%.14e" % x for x in vals) + "\n")
    open(_cutr(case, YOBI), "w").writelines(lines)


def run_bas(case, yobi):
    """④を固定カット率（CUT_KOTEI=1）で流す。引数は run_pipeline.sh の run_bas と同じ並び。"""
    bas = os.path.join(SUURI, "bas")
    env = {k: v for k, v in os.environ.items()
           if k not in ("SANGO_HAISHI", "NIGO_HAISHI", "SANGO_NOUFU", "SANGO_MODE", "ICHIGO_SANGO")}
    out = os.path.join(bas, "rslt", "output.csv")
    keep = open(out, "rb").read() if os.path.exists(out) else None
    log = os.path.join(bas, "log", f"bas-{_v(case)}-1120-{yobi}.log")
    with open(log, "w") as fp:
        subprocess.run([os.path.join(bas, "exec", "ver0000.out"),
                        os.path.join(bas, "io_file", "infile.csv"), os.path.join(bas, "io_file", "outfile.csv"),
                        case, case, case, case, case, yobi, "0", "1", "0", "0", "2031", "3", "0", "1", "0"],
                       cwd=bas, env=env, stdout=fp, stderr=subprocess.STDOUT, check=True)
    if keep is not None:
        open(out, "wb").write(keep)            # 通常試算の output.csv を戻す
    empty = os.path.join(bas, "rslt", f"cuta-{_v(case)}-1120-{yobi}.csv")
    if os.path.exists(empty) and os.path.getsize(empty) == 0:
        os.remove(empty)                       # CUT_KOTEI=1 では書かれない（空のまま開かれる）


def run():
    for case, cname in CASES:
        teishi_cut(case)
        run_bas(case, YOBI)
        print(f"④ {cname}（{case}）予備{YOBI}：完了")


def check():
    """通常試算のカット率をそのまま固定カット率として読ませ、④の出力が通常試算と一致するか。
    「収支見通し」の運用収入・年度末積立金は比べない。固定カット率の経路は tyousei() を通らず、
    調整前（b）の積立金がそのまま残る（検証/原本の不具合.md L1）。この試算はその2欄を使わない。"""
    _, _, a = Z._mods()
    case, tmp = "3003", "950"
    src = os.path.join(SUURI, "bas", "rslt", f"cuta-{_v(case)}-1120-000.csv")
    open(_cutr(case, tmp), "w").write(open(src).read())
    try:
        run_bas(case, tmp)
        worst = 0.0
        for name in ("基礎年金給付費（新法＋旧法）", "基礎年金拠出金", "基礎年金拠出金（国庫）", "特別国庫負担内訳"):
            b0 = a.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{_v(case)}-1120-000a.csv"))[name][1]
            b1 = a.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{_v(case)}-1120-{tmp}a.csv"))[name][1]
            for r0, r1 in zip(b0, b1):
                for x0, x1 in zip(r0[1:], r1[1:]):
                    if x0:
                        worst = max(worst, abs(x1 / x0 - 1))
        print(f"固定カット率の経路：通常試算との最大の相対差 {worst:.1e}（カット率ファイルの14桁の丸めの分）")
    finally:
        for p in (_cutr(case, tmp),
                  os.path.join(SUURI, "bas", "rslt", f"kekka{_v(case)}-1120-{tmp}a.csv"),
                  os.path.join(SUURI, "bas", "rslt", f"kekka{_v(case)}-1120-{tmp}b.csv"),
                  os.path.join(SUURI, "bas", "rslt", f"TUMATUMI-{case}-{case}-{case}-{tmp}-00.csv"),
                  os.path.join(SUURI, "bas", "log", f"bas-{_v(case)}-1120-{tmp}.log")):
            if os.path.exists(p):
                os.remove(p)


def pop_by_age(case):
    """①被保険者推計が使う人口（男女計）。{年度: {年齢: 人}}（65歳以上）"""
    p = os.path.join(SUURI, "wakuc", "rslt", "ver_4_1", f"rslt{case}", f"waku{case}-20.csv")
    L = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    hd = L[1]
    i65 = hd.index("65")
    return {int(r[2]): {int(hd[j]): float(r[j]) for j in range(i65, len(r)) if hd[j].strip().isdigit() and r[j].strip()}
            for r in L[2:] if len(r) > 5 and r[1] == "0"}


def mangaku(case):
    """年齢別の満額（年額・スライド前）。{年度: {年齢: 円}}。
    67歳以下は ROREI の「基礎年金満額（基本額）」の先頭の列（J4 でもこの列だけは正しい）。
    68歳以上は、前年度の1つ下の年齢の満額 × KOKUKAITE の単年度改定率。2022年度は全年齢が同額。"""
    f = os.path.join(SUURI, "nat", "rslt", f"ROREI{case}-{case}-{case}.csv")
    L = open(f, encoding="utf-8", errors="replace").read().split("\n")
    i = [k for k, l in enumerate(L) if l.startswith("基礎年金満額（基本額）")][0]
    f67 = {}
    for l in L[i + 2:]:
        c = l.split(",")
        if not c[0].strip().isdigit():
            break
        f67[int(c[0])] = float(c[1])
    kt = {}
    for l in open(os.path.join(SUURI, "nat", "data", f"KOKUKAITE-{case}-{case}E.csv")):
        r = [float(x) for x in l.split(",") if x.strip()]
        if r:
            kt[int(r[0]) + 2000] = {67 + j: x for j, x in enumerate(r[1:])}
    F = {2022: {x: f67[2022] for x in range(60, 116)}}
    for y in range(2023, 2121):
        p = F[y - 1]
        F[y] = {x: (f67[y] if x <= 67 else p[x - 1] * kt[y][x]) for x in range(60, 116)}
    return F


def keisan(case):
    co, _, a = Z._mods()
    v = _v(case)
    F, P = mangaku(case), pop_by_age(case)
    C0 = _read_cut(os.path.join(SUURI, "bas", "rslt", f"cuta-{v}-1120-000.csv"))
    C1 = _read_cut(_cutr(case, YOBI))
    kb0 = a.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{v}-1120-000a.csv"))
    kb1 = a.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{v}-1120-{YOBI}a.csv"))
    g0 = {int(r[0]): r for r in kb0["基礎年金給付費（新法＋旧法）"][1]}   # 列1 合計、7 老齢、13 障害、19 遺族（制度計）
    g1 = {int(r[0]): r for r in kb1["基礎年金給付費（新法＋旧法）"][1]}
    run0 = a.load_run(SUURI, case, "000", "000")
    toku = a.series(kb0["特別国庫負担内訳"], "合計")
    emp0 = co.read_emp(v, "000", Z.SH)
    G, D = K.gdp(case), Z.discount(case)
    r0 = co.read_rate(v, "000", Z.SH)
    out, pv = {}, [0.0, 0.0, 0.0]
    for y in range(START, 2121):
        mangaku_kei = sum(n * F[y][min(x, 115)] * C1[y][min(x, 115)] for x, n in P[y].items())
        base, stop = g0[y][1], g1[y][1]
        new = mangaku_kei + g1[y][13] + g1[y][19]
        kokko0 = run0["kokko_total"][y] + toku[y]
        shohi1 = Z.SHOHI_2025 / 7.8 * emp0[y]["標準報酬総額"] / emp0[2025]["標準報酬総額"]
        out[y] = dict(base=base, new=new, extra=new - base, e1=stop - base, e2=new - stop,
                      kokko0=kokko0, G=G[y], shohi=(new - base) / shohi1,
                      pop=sum(P[y].values()), juryo=g1[y][7] / mangaku_kei)
        pv = [p + x * D[y] for p, x in zip(pv, (new - base, stop - base, new - stop))]
    rate = {}
    for y in (2040, 2060, 2120):
        rb = r0[y]
        kiso = rb["代替率(基礎)"] * C1[y][67] / C0[y][67]
        rate[y] = (rb["所得代替率"], kiso + rb["代替率(比例)"], rb["代替率(基礎)"], kiso)
    return out, pv, rate


def report():
    summ = []
    for case, cname in CASES:
        o, pv, rate = keisan(case)
        print(f"## {cname}（{case}）")
        print()
        print("| 年度 | 現行の給付費 | 新しい給付費 | 追加の国庫 | ①スライド停止 | ②全員に満額 | 対GDP | 国庫の合計 | 国庫の割合 | 消費税に換算 |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for y in YEARS:
            x = o[y]
            print(f"| {y} | {x['base'] / 1e12:.1f}兆円 | {x['new'] / 1e12:.1f}兆円 | **{x['extra'] / 1e12:.1f}兆円** | "
                  f"{x['e1'] / 1e12:.1f}兆円 | {x['e2'] / 1e12:.1f}兆円 | {x['extra'] / x['G'] * 100:.2f}% | "
                  f"{(x['kokko0'] + x['extra']) / 1e12:.1f}兆円 | {x['kokko0'] / x['base'] * 100:.0f}% → "
                  f"{(x['kokko0'] + x['extra']) / x['new'] * 100:.0f}% | {x['shohi']:.1f}ポイント |")
        print()
        print(f"- 現在価値（2027〜2120年度）: {pv[0] / 1e12:.0f}兆円（①{pv[1] / 1e12:.0f}兆円、②{pv[2] / 1e12:.0f}兆円）、"
              f"2024年度GDPの {pv[0] / K.GDP_2024 * 100:.0f}%")
        print(f"- 満額に換算した受給者の割合（現行、65歳以上人口に対して）: 2027年度 {o[2027]['juryo'] * 100:.0f}%、"
              f"2060年度 {o[2060]['juryo'] * 100:.0f}%、2100年度 {o[2100]['juryo'] * 100:.0f}%")
        for y, (a0, a1, k0, k1) in rate.items():
            print(f"- {y}年度 所得代替率 {a0 * 100:.1f}% → {a1 * 100:.1f}%（基礎 {k0 * 100:.1f}% → {k1 * 100:.1f}%）")
        print()
        summ.append((cname, o, pv, rate))
    return summ


def graph():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "IPAPGothic"
    col = {"3003": "#2a78d6", "3002": "#eb6834", "3001": "#1baf7a"}
    fig, ax = plt.subplots(1, 2, figsize=(12, 5.2))
    ys = list(range(START, 2121))
    for case, cname in CASES:
        o, _, _ = keisan(case)
        v = [o[y]["extra"] / o[y]["G"] * 100 for y in ys]
        ax[0].plot(ys, v, color=col[case], lw=2, label=cname)
        if case == "3003":
            e1 = [o[y]["e1"] / o[y]["G"] * 100 for y in ys]
            e2 = [o[y]["e2"] / o[y]["G"] * 100 for y in ys]
            ax[1].stackplot(ys, e2, e1, colors=("#eda100", "#e87ba4"), edgecolor="white", linewidth=0.5,
                            labels=("②全員に満額（未納・免除・無年金などの底上げ）", "①マクロ経済スライドの停止"))
    ax[0].set_title("追加の国庫負担（名目GDP比）")
    ax[0].set_ylim(0, 2.2)
    ax[0].legend(frameon=False, fontsize=9)
    ax[1].set_title("過去30年投影の内訳（名目GDP比）")
    ax[1].set_ylim(0, 2.2)
    ax[1].legend(frameon=False, fontsize=9, loc="upper left")
    for x in ax:
        x.set_xlabel("年度")
        x.set_ylabel("%")
        x.grid(True, color="#dddddd", lw=0.6)
        x.spines[["top", "right"]].set_visible(False)
    fig.suptitle("65歳以上の全員に基礎年金の満額、マクロ経済スライドも停止（非公式の思考実験）", fontsize=13)
    fig.text(0.01, 0.01, "非公式：2024年財政検証の計算プログラムに独自の設定を加えた試算。厚生労働省の試算ではない。"
             "名目GDPは2024年度642.4兆円（内閣府）を物価上昇率と財政検証の実質経済成長率で延ばした推定。",
             fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    out = os.path.join(HERE, "図", "全員に満額_追加の国庫.png")
    fig.savefig(out, dpi=150, facecolor="white")
    print("書き出し:", out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"run": run, "check": check, "report": report, "graph": graph}[cmd]()
