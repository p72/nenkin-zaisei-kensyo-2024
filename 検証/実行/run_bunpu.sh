#!/bin/bash
# =============================================================================
# 分布推計（マイクロシミュレーション）を動かす
# =============================================================================
#   検証/実行/run_bunpu.sh [外枠番号] [経済前提番号]
#   例: 検証/実行/run_bunpu.sh 2011 3001
#
# 外枠番号は分布推計の基礎率が用意されているものだけ（kisoritsu01 の
# ファイル名末尾）:
#   2011 2012 2111 2112 2211 2212 2311 2312 2411 2412 2511 2512
#
# 外枠番号の3桁目が**適用拡大の区分**（①被保険者推計の2番目の入力と同じ
# 0〜5）を表す。2011→0、2111→1、2211→2、…、2511→5。
# 末尾が**労働力率の設定**（同じく①の7番目の入力、1 進展 / 2 漸進 / 3 現状）。
# 2011→進展、2012→漸進。データにあるのは 1 と 2 だけで、これは分布推計が
# 成長型経済移行・継続ケース（労働参加進展）と過去30年投影ケース（漸進）の
# 2ケースについてのみ公表されていることに対応する
# （「令和6(2024)年財政検証結果レポート」第5章 p.26）。
# main.cpp:16-20 が object01b と3桁目の一致を要求することと、
# main.cpp:109-129 が object01b ∈ {2,3,4} のとき外枠2111と2311の遷移表の差
# （＝適用拡大の効果）を取ることから読み取れる。
# したがって前段の①〜⑤も同じ適用拡大で流す必要がある。下で自動的にそうする。
#
# ─────────────────────────────────────────────────────────────────────────
#  ※ 出力を公表値と比較してはならない
#
#  同梱データには初期母集団 bunpu/kisosuu/ がディレクトリごと欠落している
#  （仕様書 §12.5）。make_kisosuu.py が同梱の遷移表から状態別人数を復元して
#  補うが、個人ごとの加入月数と年金額は集計表からは原理的に復元できないため
#  すべて 0 になる。したがって基準年齢17歳のコホート以外は加入歴を失った
#  状態で走り出し、年金額を過小に評価する。
#
#  このスクリプトの目的は「プログラムが動くことを示す」ことであって、
#  厚労省の分布推計結果を再現することではない。
# ─────────────────────────────────────────────────────────────────────────
set -e

WAKU="${1:-2011}"
ECON="${2:-3001}"
SHISAN="${SHISAN:-$ECON}"
YOBI=125          # 分布推計は cuta/cutb の予備番号 125（object01f=1）を読む

HERE=$(cd "$(dirname "$0")" && pwd)
SUURI=/suuri/rev2024
BUNPU="$SUURI/bunpu"

# 分布推計が読む入力の対応（prog04.cpp）
#   object01a = 外枠番号        seni_*_{a}.csv, PENSION_{d}-{e}-{a}, bunpu_*.{d}-{e}-{a}
#   object01d = 試算番号        kaitea-{d}-{e}e, cuta-{d}-{d}-{e}-{a}-1120-125
#   object01e = 経済前提番号    econ-{e}.csv
# object01b / object01c は main.cpp:16-30 の検査を通る値に決まる
B=$(( (WAKU / 100) % 10 ))
C=0
F=1               # 1 → cuta/cutb の予備番号 125 を使う
KAKUDAI=$B        # 外枠番号の3桁目 = 適用拡大の区分
ROUDR=$(( WAKU % 10 ))   # 外枠番号の末尾 = 労働力率（1進展/2漸進/3現状）

step() { echo; echo "############ $* ############"; }

step "前段（①〜⑤）を外枠 $WAKU / 経済前提 $ECON / 予備 $YOBI / 適用拡大 $KAKUDAI / 労働力率 $ROUDR で実行"
SHISAN="$SHISAN" ECON="$ECON" WAKU="$WAKU" YOBI="$YOBI" KAKUDAI="$KAKUDAI" \
    "$HERE/run_pipeline.sh" "$ECON" 1 1 0 "$ROUDR"

step "初期母集団 kisosuu を同梱の遷移表から組み立て"
python3 "$HERE/make_kisosuu.py" \
    --kisoritsu "$BUNPU/kisoritsu" --out "$BUNPU/kisosuu" --shisan "$WAKU"

step "入力の存在確認"
miss=0
for f in "$SUURI/emp/data/u-rev/econ/econ-$ECON.csv" \
         "$SUURI/emp/rslt/u-rev/kaite/kaitea-$SHISAN-$ECON""e" \
         "$SUURI/emp/rslt/u-rev/kaite/kaiteb-$SHISAN-$ECON""e" \
         "$SUURI/nat/data/PENSION_$SHISAN-$ECON-$WAKU.csv" \
         "$SUURI/emp/rslt/ez_arev/cutr/cuta-$SHISAN-$SHISAN-$ECON-$WAKU-1120-$YOBI.csv" \
         "$SUURI/emp/rslt/ez_arev/cutr/cutb-$SHISAN-$SHISAN-$ECON-$WAKU-1120-$YOBI.csv"; do
    if [ -f "$f" ]; then echo "  ok   $(basename "$f")"
    else echo "  ★欠落 $f"; miss=1; fi
done
for s in kou kok ren sig; do
    for p in bb g; do
        f="$SUURI/emp/rslt/u-rev/bunpu/bunpu_$p.$SHISAN-$ECON-${WAKU}_$s.csv"
        if [ -f "$f" ]; then echo "  ok   $(basename "$f")"
        else echo "  ★欠落 $f"; miss=1; fi
    done
done
[ "$miss" = "1" ] && { echo "入力が足りません。中止します。" >&2; exit 1; }

step "⑥ 分布推計 を実行"
mkdir -p "$BUNPU/rslt"
# 相対パス（../kisosuu、../rslt、../../emp）を使うので exec から動かす
cd "$BUNPU/exec"
printf "%s\n%s\n%s\n%s\n%s\n%s\n" "$WAKU" "$B" "$C" "$SHISAN" "$ECON" "$F" \
    | ./programme_bunpu_cpp

echo
echo "############ 完了 ############"
echo "出力: $BUNPU/rslt/"
ls -la "$BUNPU/rslt/" | head -20
echo
echo "※ 初期母集団の加入月数・年金額は 0 から始まる。基準年齢17歳のコホート"
echo "   以外は加入歴を失っているため、この出力を公表値と比較してはならない。"
