#!/bin/bash
# =============================================================================
# 第3号被保険者に保険料を求めるシナリオを一式流す
# =============================================================================
# 前提: 通常試算（YOBI=000）を先に通しておく
#   検証/実行/run_pipeline.sh 3003 1 1 0 2   # 過去30年投影
#   検証/実行/run_pipeline.sh 3001           # 高成長実現
# ①②③の出力は3号廃止で変わらないので、④⑤だけ（STEPS=45）を
# 予備番号（YOBI）を変えて流し直す。ビルドは毎回やる（④にパッチが要る）。
#
#   予備番号   レバー
#   000        通常試算（ベース）
#   100/101    調整期間の一致（ベース側の比較対象）
#   301        3号廃止 2027年度・全員納付（第1号移行型）
#   501        同上だが拠出金の按分は据え置き（拠出金按分据置型・国年充当。保険料は国民年金勘定に入る）
#   310/311    3号廃止 2027年度・全員納付 ＋ 調整期間の一致
#   510/511    拠出金按分据置型 ＋ 調整期間の一致（310/311 と一致するはず。
#              一致の下では按分の置き方は勘定間の移転にすぎない）
#   321        3号廃止 2027年度・納付率を SANGO_NOUFU_ALT に（感度）
#   601        第1号の全員を第3号として登録（ICHIGO。思考実験、3号廃止の裏返し）
#   541        適用拡大（約860万人）＋拠出金按分据置型。外枠 3403/3401 の上で流す。
#              前提: 適用拡大（KAKUDAI=4）を①から流しておく
#                WAKU=3403 KAKUDAI=4 YOBI=040 検証/実行/run_pipeline.sh 3003 1 1 0 2
#                WAKU=3401 KAKUDAI=4 YOBI=040 検証/実行/run_pipeline.sh 3001
#              無ければ飛ばす
#
# 使い方: 検証/3号廃止/run_sango.sh [実施年度(既定2027)] [感度用の納付率(既定0.8)]
# =============================================================================
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$ROOT/検証/実行/run_pipeline.sh"
YEAR="${1:-2027}"
NOUFU_ALT="${2:-0.8}"

run() { echo; echo "======== $* ========"; env "$@"; }

# ④にパッチを当てたビルドを一度だけ作り、以降は使い回す。
# 毎回 rm -rf してビルドし直すと遅いうえ、複数の実行が同じビルドツリーを
# 消し合って「*.cpp が無い」で落ちる。
echo "======== パッチ済みのビルドを作る（以降は SKIP_BUILD=1 で使い回す） ========"
env STEPS=0 SANGO="$YEAR" "$RUN" 3003 1 1 0 2
export SKIP_BUILD=1

for CASE in "3003 1 1 0 2" "3001"; do
    # shellcheck disable=SC2086
    set -- $CASE
    run STEPS=45 YOBI=100 YOBI2=101 TOUGOU=1                       "$RUN" "$@"
    run STEPS=45 YOBI=301 SANGO="$YEAR"                            "$RUN" "$@"
    run STEPS=45 YOBI=501 SANGO="$YEAR" SANGO_MODE=1               "$RUN" "$@"
    run STEPS=45 YOBI=310 YOBI2=311 SANGO="$YEAR" TOUGOU=1         "$RUN" "$@"
    run STEPS=45 YOBI=510 YOBI2=511 SANGO="$YEAR" SANGO_MODE=1 TOUGOU=1 "$RUN" "$@"
    run STEPS=45 YOBI=321 SANGO="$YEAR" SANGO_NOUFU="$NOUFU_ALT"   "$RUN" "$@"
    run STEPS=45 YOBI=601 ICHIGO="$YEAR"                           "$RUN" "$@"
    KWAKU=$(( $1 + 400 ))   # 適用拡大の外枠（3003→3403、3001→3401）
    if [ -d "$ROOT/work/suuri/rev2024/wakuc/rslt/ver_4_1/rslt$KWAKU" ]; then
        run STEPS=45 WAKU=$KWAKU KAKUDAI=4 YOBI=541 SANGO="$YEAR" SANGO_MODE=1 "$RUN" "$@"
    else
        echo "（外枠 $KWAKU が無いので 541 を飛ばす。先に適用拡大を①から流す）"
    fi
done
echo; echo "######## 3号廃止シナリオ 完了 ########"
