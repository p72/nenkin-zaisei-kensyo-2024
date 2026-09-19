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
#   KAKUDAI 適用拡大 0〜5 既定: 0（通常試算）
#   SIGO    基礎45年化 0/1 既定: 0（通常試算）
#   SKIP_BUILD=1  ビルドを飛ばす（同じビルドを使い回す）
#
#   SUURI_PREFIX  実行領域の置き場所。既定は <リポジトリ>/work
#                 （root 権限が要らないので、ローカルでもそのまま動く）
#                 SUURI_PREFIX=/ にすると従来どおり /suuri/rev2024 を使う
#
# 分布推計の外枠番号は3桁目が適用拡大の区分を表す（2011→0、2211→2 …）。
# その外枠を作るときは KAKUDAI をその値に合わせる必要がある。
# run_bunpu.sh が自動でそうする。
#
# 必要なもの: gcc/g++、iconv、patch、約3GBの空きディスク
#
# リポジトリ内の原本は読み取りのみ。UTF-8 に変換したコピーをビルドツリーに
# 作り、そこに patches/glibc-portability.patch を当ててからビルドする。
# ソースを UTF-8 化してビルドするので、実行時の日本語出力も UTF-8 になる
# （原本のまま EUC-JP でビルドすれば出力も EUC-JP）。
#
# -----------------------------------------------------------------------------
# 絶対パス /suuri/rev2024 について
# -----------------------------------------------------------------------------
# 原本は出力先も入力ファイルリストも /suuri/rev2024 という絶対パスで持って
# いる（専用UNIXサーバの固定構成が前提だった名残）。
#
#   プログラム側  被保険者推計/readdata.c など16ファイル（Makefile を含む）
#   データ側      {nat,bas}/io_file/{infile,outfile}.csv の4ファイル
#
# ルート直下に書き込めない環境（macOS は Catalina 以降 / が読み取り専用、
# 共有サーバで sudo が無い等）でも動くように、この2種類を**コピーの上で**
# 書き換えて任意の場所に寄せる。原本は触らない。
#
#   プログラム側 → ビルドツリー（毎回 rm -rf して作り直すので冪等）
#   データ側     → 原本から sed して実行領域へ書き出す（毎回生成なので冪等）
#
# データ側は CSV の3列目が必ず「,」に続くので `,/suuri/` を目印にする。
# =============================================================================
set -e

BANGO="${1:-3001}"
JIN="${2:-1}"; QX="${3:-1}"; NC="${4:-0}"; ROUDR="${5:-1}"
SHISAN="${SHISAN:-$BANGO}"
ECON="${ECON:-$BANGO}"
WAKU="${WAKU:-$BANGO}"
YOBI="${YOBI:-000}"
KAKUDAI="${KAKUDAI:-0}"
SIGO="${SIGO:-0}"

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
SRC="$ROOT/papers/001365945/プログラム"
DATA="$ROOT/papers/001365945/データ/suuri/rev2024"
BUILD="${BUILD_DIR:-/tmp/nenkin-build}"

# 実行領域（PREFIX・SUURI を決める）
. "$HERE/suuri_env.sh"

step() { echo; echo "############ $* ############"; }

# --------------------------------------------------------------- 準備
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    # 文字コードは EUC-JP だが、丸数字（①②③④）が NEC特殊文字として
    # 入っているため標準の EUC-JP では変換に失敗する（被保険者推計/cntl.c、
    # 収支計算/shus_out.c、収支計算/shus_fullout.c の3本）。NEC/IBM拡張を
    # 含む EUCJP-MS を使うと全ファイルきれいに通り、実行時の日本語出力も
    # 読める形になる。
    step "ソースを UTF-8 に変換してビルドツリーへ（EUCJP-MS）"
    rm -rf "$BUILD"; mkdir -p "$BUILD"
    cd "$SRC"
    find . -type f | while read -r f; do
        mkdir -p "$BUILD/$(dirname "$f")"
        iconv -f EUCJP-MS -t UTF-8 "$f" > "$BUILD/$f" 2>/dev/null || cp "$f" "$BUILD/$f"
    done

    step "移植パッチを適用（glibc 移植性、4箇所）"
    cd "$BUILD" && patch -p1 --no-backup-if-mismatch < "$HERE/patches/glibc-portability.patch"

    # 原本 snaps.h / stdfm.c が宣言する fdiv() は、新しい glibc の C23 縮小演算
    # 関数 fdiv() と名前が衝突する。単語単位の機械的な改名で回避する。
    step "fdiv() の名前衝突を回避（識別子の一律改名）"
    cd "$BUILD/国民年金" && sed -i 's/\bfdiv\b/nenkin_fdiv/g' *.c *.h

    if [ -n "$PREFIX" ]; then
        step "絶対パス /suuri を $PREFIX/suuri に寄せる（ビルドツリーのコピー）"
        cd "$BUILD"
        grep -rl '/suuri/' . | while read -r f; do
            sed -i "s|/suuri/|$PREFIX/suuri/|g" "$f"
        done

        # パスが長くなる分、固定長のファイル名バッファを広げる。
        # 原本は /suuri/rev2024（14文字）前提の寸法になっていて、
        # 収支計算の char flname[100] はプレフィックスを付けると溢れる。
        # glibc の _FORTIFY_SOURCE が検出して
        #   *** buffer overflow detected ***: terminated
        # で落ちる（⑤の実行中に発生）。原本のままなら起きないので、
        # プレフィックスを付けたときだけ広げる。
        step "ファイル名バッファを拡張（パスが $((${#PREFIX})) 文字伸びるため）"
        sed -i 's/char flname\[100\]/char flname[1024]/' 厚生年金/収支計算/fopn.c
        sed -i -E 's/(char[[:space:]]+(filename|pathname)[[:space:]]*)\[250\]/\1[1024]/' \
            被保険者推計/*.c 被保険者推計/*.h
        grep -n 'flname\[' 厚生年金/収支計算/fopn.c
    fi
fi

step "データを $SUURI に配置"
mkdir -p "$SUURI"
cp -rn "$DATA"/* "$SUURI/" 2>/dev/null || true

# 入出力ファイルリストは原本から毎回生成する（cp -rn は上書きしないので、
# 実行領域に残った書き換え済みの版を二重に書き換えてしまうのを避ける）
for rel in nat/io_file/infile.csv nat/io_file/outfile.csv \
           bas/io_file/infile.csv bas/io_file/outfile.csv; do
    mkdir -p "$SUURI/$(dirname "$rel")"
    if [ -n "$PREFIX" ]; then
        sed "s|,/suuri/|,$PREFIX/suuri/|g" "$DATA/$rel" > "$SUURI/$rel"
    else
        cp "$DATA/$rel" "$SUURI/$rel"
    fi
done

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
step "① 被保険者推計 を実行（外枠 $WAKU / 適用拡大 $KAKUDAI / 45年化 $SIGO）"
cd "$SUURI/wakuc" && printf "%s\n%s\n%s\n%s\n%s\n%s\n%s\n" \
    "$WAKU" "$KAKUDAI" "$SIGO" "$JIN" "$QX" "$NC" "$ROUDR" \
    | "$SUURI/wakuc/exec/wakuc_4_1" > /dev/null

step "② 厚生年金 給付費推計 を実行（厚年＋共済3制度）"
cd "$SUURI/emp" && printf "11\n%s\n%s\n%s\n4\n%s\n%s\n0\n0\n%s\n" \
    "$SHISAN" "$ECON" "$WAKU" "$KAKUDAI" "$SIGO" "$((ROUDR-1))" \
    | "$SUURI/emp/exec/usys20" > /dev/null

step "③ 国民年金 を実行"
cd "$SUURI/nat" && "$SUURI/nat/exec/ver0000.out" \
    "$SUURI/nat/io_file/infile.csv" "$SUURI/nat/io_file/outfile.csv" \
    "$SHISAN" "$ECON" "$WAKU" 0 M 0 1 "$KAKUDAI" 2027 0 2031 3 "$WAKU" > /dev/null

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
# grep をパイプで挟むと終了状態が隠れるので PIPESTATUS で本体の結果を見る
# （ここを素通しにしていたため、⑤が buffer overflow で落ちても「完了」と
#  表示してしまっていた）
cd "$SUURI/emp" && set +e
printf "0\n8\n%s\n%s\n0\n0\n0\n0\n%s\n%s\n%s\n%s\n" \
    "$KAKUDAI" "$SIGO" "$SHISAN" "$ECON" "$WAKU" "$YOBI" | "$SUURI/emp/exec/asys20" \
    | grep -A 4 "最終代替率"
rc=${PIPESTATUS[1]}
set -e
if [ "$rc" != "0" ]; then
    echo
    echo "★ ⑤ 収支計算 が異常終了しました（終了コード $rc）" >&2
    exit "$rc"
fi

echo
echo "############ 完了（試算番号 $SHISAN / 経済前提 $ECON / 外枠 $WAKU / 予備 $YOBI / 適用拡大 $KAKUDAI） ############"
