#!/bin/bash
# =============================================================================
# 同梱の経済前提8ケースすべてを通しで実行し、所得代替率を一覧にする
# =============================================================================
#   検証/実行/run_all_cases.sh            # 8ケース全部
#   検証/実行/run_all_cases.sh 3001 3003  # 指定したケースだけ
#
# 1ケース10〜15分、出力は約2GB。ディスクを食うので、要約を採ったあと
# 巨大な中間ファイル（shus / kisor / ashimoto / 90nenbe）を消していく。
# 分布推計用に全出力を残したい場合は run_pipeline.sh を直接使うこと。
#
# 労働力率の設定は公表資料の対応に合わせる（§15.0.0）:
#   高成長実現・成長型経済移行 → 労働参加進展(1)
#   過去30年投影               → 労働参加漸進(2)
#   1人当たりゼロ成長          → 労働参加現状(3)
# =============================================================================
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
. "$HERE/suuri_env.sh"
CASES=${@:-"3001 3002 3003 3004 3201 3202 3203 3204"}
OUT="${RESULT_FILE:-/tmp/nenkin-results.txt}"

roudr_for() {  # ケース番号 → 労働力率の設定
    case "${1: -1}" in
        1|2) echo 1 ;;
        3)   echo 2 ;;
        4)   echo 3 ;;
        *)   echo 1 ;;
    esac
}

: > "$OUT"
printf "%-8s %-28s %10s %10s %10s %8s %8s\n" \
    ケース ケース名 合計 比例 基礎 "調整(比例)" "調整(基礎)" | tee -a "$OUT"

name_for() {
    case "${1:0:4}" in
        3001|3201) echo "高成長実現" ;;
        3002|3202) echo "成長型経済移行・継続" ;;
        3003|3203) echo "過去30年投影" ;;
        3004|3204) echo "1人当たりゼロ成長" ;;
    esac
    :
}

for c in $CASES; do
    r=$(roudr_for "$c")
    nm=$(name_for "$c")
    [ "${c:0:2}" = "32" ] && nm="$nm(経済変動)"

    echo "### $c ($nm) 実行中 …" >&2
    log=$(mktemp)
    if BUILD_DIR="${BUILD_DIR:-/tmp/nenkin-build}" \
       "$HERE/run_pipeline.sh" "$c" 1 1 0 "$r" > "$log" 2>&1; then
        # ⑤収支計算の出力から所得代替率と調整終了年度を拾う
        nums=$(grep -A 2 "最終代替率" "$log" | grep -oE "[0-9]+\.[0-9]{4,}")
        tot=$(echo "$nums" | sed -n 1p | cut -c1-7)
        pro=$(echo "$nums" | sed -n 2p | cut -c1-7)
        kis=$(echo "$nums" | sed -n 3p | cut -c1-7)
        # 比例側の調整最終年度は 収支計算 の出力から。ソースの一部が EUC-JP の
        # まま残るためラベルに頼らず「2桁の整数 (小数)」の並びで拾う
        ky=$(grep -A 4 "最終代替率" "$log" | grep -oE "[0-9]{2} \([0-9]+\.[0-9]+\)" \
             | grep -oE "^[0-9]{2}" | head -1)
        # 基礎側は ④基礎年金 が西暦で出すのでそれを使う
        ny=$(grep -oE "終了年度 [0-9]{4}" "$log" | grep -oE "[0-9]{4}" | head -1)
        printf "%-8s %-28s %10s %10s %10s %8s %8s\n" \
            "$c" "$nm" "${tot:-?}" "${pro:-?}" "${kis:-?}" \
            "${ky:+20$ky}" "${ny:-?}" | tee -a "$OUT"
    else
        printf "%-8s %-28s %s\n" "$c" "$nm" "実行失敗（ログ: $log）" | tee -a "$OUT"
        continue
    fi
    cp "$log" "/tmp/nenkin-log-$c.txt"; rm -f "$log"

    # ディスクを空ける（要約は採り終わっている）
    rm -rf "$SUURI"/emp/rslt/u-rev/{shus,kisor,ashimoto}/* 2>/dev/null
    rm -f "$SUURI"/emp/rslt/ez_arev/shushi/90nenbe.* 2>/dev/null
done

echo
echo "=== 結果一覧（$OUT） ==="
cat "$OUT"
