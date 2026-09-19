#!/bin/bash
# =============================================================================
# 2024年財政検証プログラムを最初から最後まで通す
# =============================================================================
# 使い方:
#   検証/実行/run_pipeline.sh <試算番号> [出生率 死亡率 入国超過 労働力率]
#   例: 検証/実行/run_pipeline.sh 3001          # 高成長実現ケース
#       検証/実行/run_pipeline.sh 3003 1 1 0 2  # 過去30年投影（労働参加漸進）
#
# 引数: 試算番号（= 経済前提ファイル econ-XXXX.csv の番号）
#       出生率(1中位/2高位/3低位)          既定 1
#       死亡率(1中位/2高位/3低位)          既定 1
#       入国超過(0:16万/1:6.9万/2:25万)    既定 0
#       労働力率(1進展/2漸進/3現状)        既定 1
#
# 環境変数で番号を分けられる（分布推計の前段を作るときに使う）:
#   SHISAN  試算番号     既定: 第1引数
#   ECON    経済前提番号 既定: 第1引数
#   WAKU    外枠番号     既定: 第1引数
#   YOBI    予備番号     既定: 000
#   SKIP_BUILD=1  ビルドを飛ばす（同じビルドを使い回す）
#
# 必要なもの: gcc/g++、iconv、patch、約3GBの空きディスク
#
# リポジトリ内の原本は読み取りのみ。UTF-8 に変換したコピーをビルドツリーに
# 作り、そこに patches/glibc-portability.patch を当ててからビルドする。
# ソースを UTF-8 化してビルドするので、実行時の日本語出力も UTF-8 になる
# （原本のまま EUC-JP でビルドすれば出力も EUC-JP）。
# =============================================================================
set -e

BANGO="${1:-3001}"
JIN="${2:-1}"; QX="${3:-1}"; NC="${4:-0}"; ROUDR="${5:-1}"
SHISAN="${SHISAN:-$BANGO}"
ECON="${ECON:-$BANGO}"
WAKU="${WAKU:-$BANGO}"
YOBI="${YOBI:-000}"

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
SRC="$ROOT/papers/001365945/プログラム"
DATA="$ROOT/papers/001365945/データ/suuri/rev2024"
BUILD="${BUILD_DIR:-/tmp/nenkin-build}"
# プログラムは出力先を絶対パスで持っているので、この場所は変えられない
SUURI=/suuri/rev2024

step() { echo; echo "############ $* ############"; }

# --------------------------------------------------------------- 準備
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    step "ソースを UTF-8 に変換してビルドツリーへ"
    rm -rf "$BUILD"; mkdir -p "$BUILD"
    cd "$SRC"
    find . -type f | while read -r f; do
        mkdir -p "$BUILD/$(dirname "$f")"
        iconv -f EUC-JP -t UTF-8 "$f" > "$BUILD/$f" 2>/dev/null || cp "$f" "$BUILD/$f"
    done

    step "移植パッチを適用（glibc 移植性、4箇所）"
    cd "$BUILD" && patch -p1 --no-backup-if-mismatch < "$HERE/patches/glibc-portability.patch"

    # 原本 snaps.h / stdfm.c が宣言する fdiv() は、新しい glibc の C23 縮小演算
    # 関数 fdiv() と名前が衝突する。単語単位の機械的な改名で回避する。
    step "fdiv() の名前衝突を回避（識別子の一律改名）"
    cd "$BUILD/国民年金" && sed -i 's/\bfdiv\b/nenkin_fdiv/g' *.c *.h
fi

step "データを $SUURI に配置"
mkdir -p "$SUURI"
cp -rn "$DATA"/* "$SUURI/" 2>/dev/null || true
mkdir -p "$SUURI"/{nat,bas,emp,bunpu,wakuc}/{exec,rslt,log}
mkdir -p "$SUURI"/nat/data "$SUURI"/bas/{data,settei}
mkdir -p "$SUURI"/emp/rslt/u-rev/{shus,shusg,kiso,kisor,hou,kaite,hikaku,ashimoto,bunpu,prt}
mkdir -p "$SUURI"/emp/rslt/ez_arev/{cutr,shushi}
mkdir -p "$SUURI"/wakuc/rslt/ver_4_1
mkdir -p "$SUURI"/bunpu/rslt

# --------------------------------------------------------------- ビルド
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    step "① 被保険者推計 をビルド"
    cd "$BUILD/被保険者推計" && make >/dev/null

    step "② 厚生年金 給付費推計 をビルド"
    cd "$BUILD/厚生年金/給付費推計" && g++ -Ofast -w -I ext -I common -I lib \
        -o "$SUURI/emp/exec/usys20" *.cpp

    step "③ 国民年金 をビルド"
    cd "$BUILD/国民年金" && g++ -O2 -w -o "$SUURI/nat/exec/ver0000.out" \
        main.c stdfm.c cntl.c file_open.c seid.c econ.c waku.c kaizen.c dtst.c \
        kiso.c noufuritu.c siml.c str_op.c shke.c stat.c printout.c

    step "④ 基礎年金 をビルド"
    cd "$BUILD/基礎年金" && g++ -O2 -w -o "$SUURI/bas/exec/ver0000.out" *.c

    step "⑤ 厚生年金 収支計算 をビルド"
    cd "$BUILD/厚生年金/収支計算" && gcc -O2 -w -o "$SUURI/emp/exec/asys20" *.c -lm

    step "⑥ 分布推計 をビルド"
    cd "$BUILD/分布推計" && g++ -Ofast -w -I ext -I common -I lib \
        -o "$SUURI/bunpu/exec/programme_bunpu_cpp" *.cpp
fi

# --------------------------------------------------------------- 実行
# 適用拡大なし(0)・基礎45年化なし(0)＝通常試算で固定
step "① 被保険者推計 を実行（外枠 $WAKU）"
cd "$SUURI/wakuc" && printf "%s\n0\n0\n%s\n%s\n%s\n%s\n" \
    "$WAKU" "$JIN" "$QX" "$NC" "$ROUDR" | "$SUURI/wakuc/exec/wakuc_4_1" > /dev/null

step "② 厚生年金 給付費推計 を実行（厚年＋共済3制度）"
cd "$SUURI/emp" && printf "11\n%s\n%s\n%s\n4\n0\n0\n0\n0\n%s\n" \
    "$SHISAN" "$ECON" "$WAKU" "$((ROUDR-1))" | "$SUURI/emp/exec/usys20" > /dev/null

step "③ 国民年金 を実行"
cd "$SUURI/nat" && "$SUURI/nat/exec/ver0000.out" \
    "$SUURI/nat/io_file/infile.csv" "$SUURI/nat/io_file/outfile.csv" \
    "$SHISAN" "$ECON" "$WAKU" 0 M 0 1 0 2027 0 2031 3 "$WAKU" > /dev/null

step "④ 基礎年金 を実行（マクロ経済スライドの調整終了年度を解く）"
: > "$SUURI/bas/rslt/output.csv"
cd "$SUURI/bas" && "$SUURI/bas/exec/ver0000.out" \
    "$SUURI/bas/io_file/infile.csv" "$SUURI/bas/io_file/outfile.csv" \
    "$SHISAN" "$SHISAN" "$ECON" "$WAKU" "$WAKU" "$YOBI" 0 1 0 0 2031 3 0 0 0 \
    | grep -E "終了年度|カット率|給付率|代替率換算" || true

# 基礎年金が出したカット率ファイルを収支計算が読む場所へ渡す
cp "$SUURI/bas/rslt/cuta-$SHISAN-$SHISAN-$ECON-$WAKU-1120-$YOBI.csv" \
   "$SUURI/emp/rslt/ez_arev/cutr/"

step "⑤ 厚生年金 収支計算 を実行（所得代替率）"
cd "$SUURI/emp" && printf "0\n8\n0\n0\n0\n0\n0\n0\n%s\n%s\n%s\n%s\n" \
    "$SHISAN" "$ECON" "$WAKU" "$YOBI" | "$SUURI/emp/exec/asys20" \
    | grep -A 4 "最終代替率" || true

echo
echo "############ 完了（試算番号 $SHISAN / 経済前提 $ECON / 外枠 $WAKU / 予備 $YOBI） ############"
