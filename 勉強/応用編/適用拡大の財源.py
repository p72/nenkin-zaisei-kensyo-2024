#!/usr/bin/env python3
"""適用拡大（約860万人）で増える基礎年金は、誰が払うか（非公式・推定）。

現行制度（予備番号000）と適用拡大（KAKUDAI=4、外枠3403、予備番号040。厚生労働省のオプション試算 No.15 と全項目一致）
を比べ、2027〜2120年度の
  基礎年金の費用（拠出金の合計）、国庫負担（基礎年金の1/2・特別国庫負担）、保険料（厚生年金4制度・国民年金）、
  報酬比例など（厚生年金の支出 − 基礎年金拠出金）
の差を、現在価値（2024年度末、名目運用利回りで割り引き）と年度ごとの名目額で出す。

使い方（リポジトリの直下で）
  検証/実行/run_pipeline.sh 3003 1 1 0 2                                   # 現行制度
  WAKU=3403 KAKUDAI=4 YOBI=040 検証/実行/run_pipeline.sh 3003 1 1 0 2      # 適用拡大（①から）
  python3 勉強/応用編/適用拡大の財源.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
CASE, WAKU = "3003", "3403"
YEARS = (2030, 2040, 2060, 2080, 2100)


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


A = _load("sango", os.path.join(ROOT, "検証", "3号廃止", "analyze_sango.py"))
Z = _load("zei7", os.path.join(HERE, "税方式7万円.py"))


def kekka(waku, yobi):
    kb = A.read_blocks(os.path.join(SUURI, "bas", "rslt", f"kekka{CASE}-{CASE}-{CASE}-{waku}-1120-{yobi}a.csv"))
    h, rows = kb["収支見通し"]
    return {int(r[0]): {h[i]: r[i] for i in range(len(h)) if h[i]} for r in rows if r and r[0] is not None}


def series(r, k):
    ys = range(2027, 2121)
    return {
        "基礎年金の費用（拠出金の合計）": {y: r["kyo_total"][y] for y in ys},
        "国庫：基礎年金の1/2": {y: r["kokko_total"][y] for y in ys},
        "国庫：特別国庫負担": {y: k[y]["国庫（特別国庫）"] for y in ys},
        "保険料：厚生年金（4制度）": {y: r["kou_hoken"][y] * 1e8 for y in ys},
        "保険料：国民年金": {y: r["kn_hoken"][y] for y in ys},
        "報酬比例など（厚生年金の支出 − 拠出金）": {y: (r["kou_out"][y] - r["kou_kyoshutu"][y]) * 1e8 for y in ys},
    }


def main():
    b = A.load_run(SUURI, CASE, "000", "000")
    x = A.load_run(SUURI, CASE, "040", "040", waku=WAKU)
    if x is None:
        raise SystemExit("★ 適用拡大（外枠3403・予備040）の出力がない。使い方の手順で流すこと")
    S0, S1 = series(b, kekka(CASE, "000")), series(x, kekka(WAKU, "040"))
    D = Z.discount(CASE)
    print("## 所得代替率（調整終了後）\n")
    for nm, r in (("現行制度", b), ("適用拡大", x)):
        t, h, k = r["final_rr"]
        print(f"- {nm}：{t:.1f}%（比例 {h:.1f}／基礎 {k:.1f}）、調整終了 基礎 {r['kiso_end']}年度・比例 {r['hirei_end']}年度")
    print("\n## 現在価値（2027〜2120年度、2024年度末に割り引き、兆円）\n")
    print("| 項目 | 現行制度 | 適用拡大 | 差 |")
    print("|---|---|---|---|")
    d = {}
    for key in S0:
        p0 = sum(v * D[y] for y, v in S0[key].items()) / 1e12
        p1 = sum(v * D[y] for y, v in S1[key].items()) / 1e12
        d[key] = p1 - p0
        print(f"| {key} | {p0:,.0f} | {p1:,.0f} | {p1 - p0:+,.0f} |")
    kiso = d["基礎年金の費用（拠出金の合計）"]
    kokko = d["国庫：基礎年金の1/2"] + d["国庫：特別国庫負担"]
    hoken = d["保険料：厚生年金（4制度）"] + d["保険料：国民年金"]
    hirei = -d["報酬比例など（厚生年金の支出 − 拠出金）"]
    print("\n## 増えた基礎年金の費用の出どころ（現在価値）\n")
    print("| 出どころ | 兆円 | 基礎年金の費用の増えに対する割合 |")
    print("|---|---|---|")
    for nm, v in (("国庫負担の増え", kokko), ("保険料の増え（厚生年金＋国民年金）", hoken), ("報酬比例などの減り", hirei),
                  ("残り（積立金・運用収入の差など）", kiso - kokko - hoken - hirei)):
        print(f"| {nm} | {v:+,.0f} | {v / kiso * 100:.0f}% |")
    print(f"\n基礎年金の費用の増え：{kiso:+,.0f}兆円\n")
    print("## 年度ごとの差（兆円・名目）\n")
    print("| 年度 | 基礎年金の費用 | 国庫負担（基礎年金＋特別国庫） | 保険料（厚生年金） | 保険料（国民年金） | 報酬比例など |")
    print("|---|---|---|---|---|---|")
    for y in YEARS:
        def dd(key):
            return (S1[key][y] - S0[key][y]) / 1e12
        print(f"| {y} | {dd('基礎年金の費用（拠出金の合計）'):+.1f} | {dd('国庫：基礎年金の1/2') + dd('国庫：特別国庫負担'):+.1f} | "
              f"{dd('保険料：厚生年金（4制度）'):+.1f} | {dd('保険料：国民年金'):+.1f} | {dd('報酬比例など（厚生年金の支出 − 拠出金）'):+.1f} |")
    print(f"\n厚生年金の積立金（2120年度末・名目）：現行 {b['kou_tumitate'][2120] / 1e4:,.0f}兆円 → 適用拡大 {x['kou_tumitate'][2120] / 1e4:,.0f}兆円")


if __name__ == "__main__":
    main()
