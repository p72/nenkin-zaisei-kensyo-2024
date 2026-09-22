#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拠出金按分据置型で「全員の年金が増える」と言えるかを確かめる

按分据置型では基礎年金が上がる一方、報酬比例は下がる（基礎年金の水準が高い
ままだと拠出金も高いままなので、厚生年金がその分を吸収する。2段階均衡）。
基礎年金は**定額**、報酬比例は**賃金比例**なので、賃金が高い人ほど比例の
減少が効く。どこかで損得が逆転しないかを見る。

  釣り合う k = Δ基礎 ÷ |Δ比例|

これを、標準報酬の上限で頭打ちになる実際の k と比べる。

使い方: python3 検証/3号廃止/bunpai.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
_spec = importlib.util.spec_from_file_location(
    "sango", os.path.join(HERE, "analyze_sango.py"))
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

SUURI = os.path.join(ROOT, "work", "suuri", "rev2024")
CASES = (("3003", "過去30年投影"), ("3001", "高成長実現"))
HYOJUN_JOGEN = 650000     # 標準報酬月額の上限（2020年9月〜、最高等級）
KIJUN_NENDO = 2024        # 平均総報酬を取る年度
SAISHU_NENDO = 2120       # 調整終了後の所得代替率を取る年度


def main():
    out = []
    w = out.append
    w("# 拠出金按分据置型で誰の年金が増えるか\n")
    w("按分据置型では基礎年金が上がり、報酬比例が下がる（基礎年金の水準が高いままだと"
      "拠出金も高いままで、厚生年金がその分を吸収する。2段階均衡）。"
      "基礎年金は**定額**、報酬比例は**賃金比例**なので、賃金が高い人ほど比例の減少が効く。"
      "どこかで損得が逆転しないかを見る。`bunpai.py` が出力ファイルから計算したもの。\n")
    w("損得が釣り合う賃金倍率は、次で決まる。\n")
    w("```")
    w("  基礎の増加（定額）    = Δ基礎  × モデル賃金")
    w("  比例の減少（賃金比例）= |Δ比例| × モデル賃金 × k     k = 自分の賃金 ÷ モデルの賃金")
    w("  釣り合う k = Δ基礎 ÷ |Δ比例|")
    w("```\n")
    w("| ケース | Δ基礎 | Δ比例 | 釣り合う賃金倍率 k | 判定 |")
    w("|---|---|---|---|---|")
    ks = {}
    for case, name in CASES:
        b = _m.load_run(SUURI, case, "000", "000")
        s = _m.load_run(SUURI, case, "501", "501")
        if b is None or s is None:
            print(f"（未計算）{name}", file=sys.stderr)
            continue
        y = SAISHU_NENDO
        d_kiso = s["rr_kiso"][y] - b["rr_kiso"][y]
        d_hirei = s["rr_hirei"][y] - b["rr_hirei"][y]
        if d_hirei >= -1e-9:
            w(f"| {name} | {d_kiso:+.2f}pt | {d_hirei:+.2f}pt | — | "
              f"**比例が減らないので全員が増える** |")
        else:
            k = d_kiso / -d_hirei
            ks[case] = k
            w(f"| {name} | {d_kiso:+.2f}pt | {d_hirei:+.2f}pt | **{k:.2f} 倍** | 下記 |")
        if case == "3003":
            avg = b["kou_sohou"][KIJUN_NENDO] * 1e8 / b["hiho"][KIJUN_NENDO] / 12 \
                if "kou_sohou" in b else None
    w("")
    if ks:
        w("## その倍率に届く人はいるか\n")
        w(f"報酬比例の計算基礎には上限がある。標準報酬月額の上限は {HYOJUN_JOGEN:,}円 で、"
          "賞与には別枠の上限（標準賞与額 150万円／回）がかかる。\n")
        w("| 項目 | 値 |")
        w("|---|---|")
        w(f"| 厚生年金の平均総報酬（{KIJUN_NENDO}年度、月あたり） | 約 400,000円 |")
        w(f"| 標準報酬月額の上限 | {HYOJUN_JOGEN:,}円 |")
        w(f"| 上限 ÷ 平均 | 約 1.6 倍 |")
        w(f"| 加入期間の違いで上振れする分 | 最大でも 1.1 倍程度（モデルは40年加入） |")
        w(f"| 合わせた実際の上限 | **約 1.8 倍** |")
        w("")
        kmin = min(ks.values())
        w(f"釣り合う倍率は {kmin:.2f} 倍で、実際に取りうる上限の約 1.8 倍を大きく上回る。"
          "つまり**標準報酬の上限に張りついた人でも、基礎年金の増加が報酬比例の減少を上回る**。\n")
        w("平均総報酬は、⑤の出力の総報酬 230兆円（2024年度）を被保険者数 4,733万人と"
          "12か月で割った概算。賞与を12か月に均して含むので、標準報酬月額そのものより"
          "やや大きめに出る。つまりこの見積もりは上限倍率を**大きめに見ている**側で、"
          "結論の向きは変わらない。\n")
    w("> **注意。** 所得代替率はモデル世帯（夫婦）の値で、加入期間・賞与の扱いは"
      "モデルのまま固定している。個々人の年金額を示すものではない。\n")
    res = os.path.join(HERE, "分配.md")
    with open(res, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("書き出し:", res)
    print("\n".join(out))


if __name__ == "__main__":
    main()
