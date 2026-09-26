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
#   STEPS         流す工程。既定 12345（①〜⑤全部）
#                 例 STEPS=25 なら②給付費推計と⑤収支計算だけ流す。
#                 高在老撤廃・標準報酬上限のように公表値が基礎年金側を
#                 通常試算のまま据え置いているオプションで使う（後述）。
#
# -----------------------------------------------------------------------------
# オプション試算のレバー（既定は全部0＝通常試算）
# -----------------------------------------------------------------------------
#   KAKUDAI 0〜5  被用者保険の適用拡大
#                 1:90万人 2:200万人 3:270万人 4:860万人 5:賃金要件のみ撤廃
#   SIGO    0/1   基礎年金の拠出期間45年化
#   KOZAX   0/1   65歳以上の在職老齢年金の撤廃
#   HOUJOU  0〜3  標準報酬月額の上限の見直し（1:75万 2:83万 3:98万）
#   TOUGOU  0/1   マクロ経済スライドの調整期間の一致（基礎と比例）
#   DMACRO  0/1   名目下限措置の撤廃（マクロ経済スライドのフル発動）
#   CARRY   0/1   キャリーオーバー（1:あり＝現行、0:行わない）★既定は1
#
#   ★原本にないレバー（このリポジトリの追加。公表値との照合対象ではない）
#   SANGO   0/西暦4桁  第3号被保険者の廃止（第1号への振替）の実施年度。
#                 0 なら現行どおり。例 SANGO=2027
#   NIGO    0/西暦4桁  第2号被保険者の廃止（第1号への振替）の実施年度。
#                 被用者年金の算定対象者が0になり、基礎年金拠出金が全額
#                 国民年金勘定に寄る＝「基礎年金拠出金制度の廃止」。
#                 第2号は厚年保険料18.3%を払い続ける前提なので、定額保険料は
#                 その上乗せになる（保険料率を下げるレバーは未実装）。
#   SANGO_NOUFU 0〜1  振替後の納付率（2号・3号の両方に適用。既定 1）。
#   SANGO_MODE  0/1   3号廃止の財政構造（既定 0）
#                 0: 第1号への完全移行。拠出金の按分の頭数も国民年金へ移す。
#                    被用者年金の拠出金が年3.1兆円減り、その半分が国庫負担の
#                    減で相殺されて、被用者年金勘定に年1.5兆円の黒字が立つ。
#                    公的年金全体の純増（本人が新たに払う年1.2兆円）はそちらへ
#                    流れ、基礎年金の財源はかえって悪化する。
#                 1: 保険料だけ徴収し、拠出金の按分は現行のまま据え置く。
#                    増収は国民年金勘定に入る。基礎年金の水準が上がると
#                    その費用は被用者年金（報酬比例の削減）と国庫にもかかる。
#                    給付側は 0 と同じ。調整期間の一致の下では 0 と15桁一致。
#   ICHIGO  0/西暦4桁  第1号被保険者の全員を第3号として登録する実施年度（思考実験）。
#                 国民年金の拠出金算定対象者と産休・育休の免除者を0にし、
#                 第1号被保険者数（未納・免除を含む頭数）を厚生年金の第3号に
#                 足す。国民年金の保険料収入も拠出金の按分も0になり、
#                 基礎年金の水準が国民年金勘定から切り離される。
#                 給付側は触らない（未納・免除期間が納付済期間に変わる分の
#                 給付増は入らない）。SANGO/NIGO と同じパッチ・同じ流し方。
#   KOKKO   0/西暦4桁  厚生年金への国庫負担の廃止の実施年度（思考実験）。
#                 ⑤収支計算で、被用者年金4制度の「国庫負担」を実施年度以降
#                 収入に入れない（patches/kokko-cut.patch）。基礎年金拠出金は
#                 そのまま払うので、拠出金の国庫負担分（1/2）も厚生年金の
#                 保険料と積立金でまかなうことになる。失う収入（年12〜15兆円）は
#                 マクロ経済スライドを2120年度まで続けても埋まらないので、
#                 ⑤は現行どおりの調整経路のうえで、実施年度以降の報酬比例を
#                 一律 m 倍（既裁定を含む）して2120年度に均衡する m を2分法で
#                 求める。④（国民年金勘定・基礎年金の水準）は動かない。出力の
#                 「国庫負担」は0になり、内訳の (再)国庫基礎 などの列に
#                 「国が払わずに済んだ額」が残る。④の出力は通常試算と同じなので、
#                 YOBI を変えて STEPS=45 で流す（ビルドは必要）。
#                 TOUGOU・SAIMU とは組み合わせられない。
#   KOKKO_MODE 0/1  国庫負担の廃止の調整方法（既定 0）
#                 0: 報酬比例の一律削減で均衡させる
#                 1: マクロ経済スライドだけで調整する。均衡しないので⑤は
#                    「最終年度まで調整しても均衡できませんでした」と出し、
#                    最終年度まで調整し続けた状態を出力する（確かめる用）
#
#   SAIMU   0/1/2  債務の試算（原本の機能。既定 0）
#                 0: 通常試算
#                 1: 過去分試算（既発生債務。基準年度2025年度、債務種類 AK）
#                 2: 受給者分試算（既裁定債務。同 AJ）
#                 1/2 は先に同じ番号で通常試算を通しておくこと。⑤が通常試算の
#                 カット率ファイル（cutr/cuta・cutb）を読むため（fopn.c:141-155）。
#                 原本が受け付ける組合せは基準年度25・障害遺族2・加給等1・
#                 死亡率改善1 だけで、それ以外は原本が自分で止まる
#                 （②fileio.cpp:159-183、⑤main.c:112-142）。
#                 出力は AK/AJ 接頭辞つき、かつ末尾が _09sum になる。
#                 patches/sango-haishi.patch を④基礎年金の waku.c に当て、
#                 実施年度以降の被用者年金4制度の3号（20〜59歳）を国民年金の
#                 拠出金算定対象者（納付者）へ移す。頭割りと保険料収入の両方に
#                 効く。給付側は触らない（3号期間はもともと納付済期間）。
#                 ①②③の出力は変わらないので、通常試算と同じ番号で
#                 YOBI を変え STEPS=45 と組み合わせれば④⑤だけ流し直せる
#                 （ビルドは必要。SKIP_BUILD=1 と併用しないこと）。
#
#   WAKU_M  外枠番号  SIGO=1 のとき⑤が読む waku****-m.csv の番号（既定 WAKU）
#   YOBI2   3桁      TOUGOU=1 のとき⑤が書く統一カット率の予備番号（既定 001）
#                    YOBI と必ず別の番号にすること（同名を2重に開いて壊れる）
#
# どのレバーがどのプログラムに入るかは原本で確認済み:
#
#   レバー   ②給付費推計          ④基礎年金       ⑤収支計算
#   KAKUDAI  flg_part (入力6)      ―               Flg_Part (入力3)
#   SIGO     flg_sigo (入力7)      ―               Flg_Sigo (入力4)
#   KOZAX    flg_kozax(入力8)      ―               ―
#   HOUJOU   houjou   (入力9)      ―               Flg_Houjou (入力5)
#   TOUGOU   ―                    argv[15]        Touitu (入力6)
#   DMACRO   ―                    argv[11]        Flg_Dmakuro (入力8)
#   CARRY    ―                    argv[10]        Flg_Kmakuro (入力7、極性が逆)
#
# CARRY の極性に注意。④の argv[10] は「1=キャリーオーバーあり」ですが、
# ⑤の Flg_Kmakuro は「1=キャリーオーバー撤廃」です（cntl.c:168-171）。
# このスクリプトは CARRY=1（現行）に対して ⑤へ 0 を渡します。
#
# TOUGOU=1 のときだけ④を2回まわします（原本の想定する手順）。
#   1周目 CUT_KOTEI=0  基礎年金が自前で有限均衡を解き、比例側に渡す
#                      provide / KYOSHUTUKIN（ss=7,8 付き）を書く
#   ⑤     Touitu=1     基礎と比例を一括で均衡させ、統一カット率を
#                      cuta/cutb-…-1120-{YOBI2}.csv に書く
#   2周目 CUT_KOTEI=1  その統一カット率を読んで基礎年金の見通しを作り直す
#
# -----------------------------------------------------------------------------
# KOZAX・HOUJOU は基礎年金側を据え置く（STEPS=25）
# -----------------------------------------------------------------------------
# 65歳以上の在職老齢年金の撤廃と標準報酬月額の上限の見直しは、どちらも
# 報酬比例の支給停止・保険料にしか効かないので、基礎年金の財政は動かない。
# 公表値（詳細結果等2 の 25〜28）も基礎年金側が**通常試算と1ビット違わない**。
#
#   No.03（通常）と No.25（高在老撤廃）の比較
#     国民年金シート    全項目の相対差 0
#     厚生年金シート    保険料収入・その他収入・その他支出・標準報酬総額・
#                       基礎年金拠出金 の相対差 0、給付費以降だけ動く
#
# ところが②は flg_kozax を立てると kiso.* の中身がわずかに変わる（老在を
# 老退として扱う分の副作用）。そのまま③④を流すと基礎年金のカット率が
# 1e-7 ほどずれて、公表値と合わなくなる。公表値を再現するには、
# **③④を通常試算のまま据え置いて、②と⑤だけ流し直す**。
#
#   検証/実行/run_pipeline.sh 3003 1 1 0 2                       # 通常試算
#   KOZAX=1 STEPS=25 SKIP_BUILD=1 \
#       検証/実行/run_pipeline.sh 3003 1 1 0 2                   # 公表 No.25
#
# TOUGOU・DMACRO・CARRY は基礎年金側も動く（公表値もそうなっている）ので、
# ①〜⑤を通しで流す。
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
KOZAX="${KOZAX:-0}"
HOUJOU="${HOUJOU:-0}"
TOUGOU="${TOUGOU:-0}"
DMACRO="${DMACRO:-0}"
CARRY="${CARRY:-1}"
SANGO="${SANGO:-0}"
NIGO="${NIGO:-0}"
SANGO_NOUFU="${SANGO_NOUFU:-1}"
SANGO_MODE="${SANGO_MODE:-0}"
ICHIGO="${ICHIGO:-0}"
KOKKO="${KOKKO:-0}"
KOKKO_MODE="${KOKKO_MODE:-0}"
SAIMU="${SAIMU:-0}"
WAKU_M="${WAKU_M:-$WAKU}"
YOBI2="${YOBI2:-001}"
STEPS="${STEPS:-12345}"

die() { echo "★ $*" >&2; exit 1; }
chk() { # chk 変数名 値 許される値...
    local name="$1" val="$2" ok hit=0
    shift 2
    for ok in "$@"; do
        if [ "$val" = "$ok" ]; then hit=1; fi
    done
    if [ "$hit" = 0 ]; then
        die "$name の値が不正です: 「$val」（許されるのは $*）"
    fi
}
chk KAKUDAI "$KAKUDAI" 0 1 2 3 4 5
chk SIGO    "$SIGO"    0 1
chk KOZAX   "$KOZAX"   0 1
chk HOUJOU  "$HOUJOU"  0 1 2 3
chk TOUGOU  "$TOUGOU"  0 1
chk DMACRO  "$DMACRO"  0 1
chk CARRY   "$CARRY"   0 1
chk JIN     "$JIN"     1 2 3
chk QX      "$QX"      1 2 3
chk ROUDR   "$ROUDR"   1 2 3
chk SAIMU   "$SAIMU"   0 1 2
chk SANGO_MODE "$SANGO_MODE" 0 1
chk KOKKO_MODE "$KOKKO_MODE" 0 1
for v in SANGO NIGO ICHIGO KOKKO; do
    eval "val=\$$v"
    case "$val" in
        0) ;;
        20[2-9][0-9]|21[01][0-9]|2120) ;;
        *) die "$v の値が不正です: 「$val」（0 か 2020〜2120 の西暦4桁）" ;;
    esac
done
if ! awk -v r="$SANGO_NOUFU" 'BEGIN{ exit !(r+0 > 0 && r+0 <= 1) }'; then
    die "SANGO_NOUFU の値が不正です: 「$SANGO_NOUFU」（0 より大きく 1 以下）"
fi
# SANGO/NIGO は④のビルドにパッチが要る。SKIP_BUILD=1 でパッチ済みのビルドを
# 使い回すのは正しい使い方なので止めない（同じビルドを何度も作り直すと遅く、
# 複数の実行が同じビルドツリーを消し合う事故も起きる）。パッチが当たっていない
# ビルドを使ってしまった場合は、④の実行後に run_bas がレバーの出力を探して止める。

# ⑤は Touitu>=1 のとき cuta/cutb を YOBI と YOBI2 の2組そろえて書き込み用に
# 開く（fopn.c:158-190）。同じ番号だと同名のファイルを2つのハンドルで開いて
# 中身が壊れるので、ここで止める。
if [ "$KOKKO" != 0 ] && { [ "$TOUGOU" != 0 ] || [ "$SAIMU" != 0 ]; }; then
    die "KOKKO は TOUGOU・SAIMU と組み合わせられません（報酬比例の一律削減が統一カット率・債務試算の前提と合わない）"
fi
if [ "$TOUGOU" = 1 ] && [ "$YOBI2" = "$YOBI" ]; then
    die "TOUGOU=1 のときは YOBI2（$YOBI2）を YOBI（$YOBI）と別の3桁にしてください"
fi

# ②③は出生率・死亡率を番号ではなくファイル名で選ぶ
#   ②seimei      4:死亡中位 5:死亡高位 6:死亡低位      → QX + 3
#   ③BIRTHFILE   birth_ratio_0:中位 _1:高位 _2:低位    → JIN − 1
#   ③DEATH       QX-M2023:中位 H:高位 L:低位
SEIMEI=$((QX + 3))
BIRTHFILE=$((JIN - 1))
case "$QX" in 1) DEATH=M ;; 2) DEATH=H ;; 3) DEATH=L ;; esac

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
SRC="$ROOT/papers/001365945/プログラム"
DATA="$ROOT/papers/001365945/データ/suuri/rev2024"
BUILD="${BUILD_DIR:-/tmp/nenkin-build}"

# 実行領域（PREFIX・SUURI を決める）
. "$HERE/suuri_env.sh"

# 工程ごとの所要秒を測る。step を呼んだ時点で直前の工程を締める。
T_START=$(date +%s)
STEP_T0=$T_START
STEP_NAME=""
STEP_SECS=()
STEP_NAMES=()

step() {
    local now
    now=$(date +%s)
    if [ -n "$STEP_NAME" ]; then
        STEP_SECS+=( "$((now - STEP_T0))" )
        STEP_NAMES+=( "$STEP_NAME" )
    fi
    STEP_NAME="$*"
    STEP_T0=$now
    if [ -n "$*" ]; then
        echo
        echo "############ $* ############"
    fi
}

step_report() {
    local i
    step ""                       # 最後の工程を締める
    echo
    echo "---- 所要時間 ----"
    for i in "${!STEP_SECS[@]}"; do
        printf '  %5d 秒  %s\n' "${STEP_SECS[$i]}" "${STEP_NAMES[$i]}"
    done
    printf '  %5d 秒  合計\n' "$(( $(date +%s) - T_START ))"
}

run_step() { case "$STEPS" in *"$1"*) return 0 ;; *) return 1 ;; esac; }

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

    if [ "$SANGO" != 0 ] || [ "$NIGO" != 0 ] || [ "$ICHIGO" != 0 ]; then
        step "号別被保険者の保険料負担レバーを④基礎年金に当てる（patches/sango-haishi.patch）"
        cd "$BUILD" && patch -p1 --no-backup-if-mismatch < "$HERE/patches/sango-haishi.patch"
    fi

    if [ "$KOKKO" != 0 ]; then
        step "厚生年金への国庫負担の廃止レバーを⑤収支計算に当てる（patches/kokko-cut.patch）"
        cd "$BUILD" && patch -p1 --no-backup-if-mismatch < "$HERE/patches/kokko-cut.patch"
    fi

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
    # 同梱の Makefile の release は `-O2`（`-fast` はコメントアウト済み）。
    # `-Ofast` は演算順の書き換えを許すので、原本と同じ `-O2` で建てる
    # （`検証/原本の不具合.md` G1・G2）。⑥だけは Makefile 自身が
    # `-Ofast` を指定しているので下ではそのままにしてある。
    cd "$BUILD/厚生年金/給付費推計" && g++ -O2 -w -I ext -I common -I lib \
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
if run_step 1; then
step "① 被保険者推計 を実行（外枠 $WAKU / 適用拡大 $KAKUDAI / 45年化 $SIGO）"
cd "$SUURI/wakuc" && printf "%s\n%s\n%s\n%s\n%s\n%s\n%s\n" \
    "$WAKU" "$KAKUDAI" "$SIGO" "$JIN" "$QX" "$NC" "$ROUDR" \
    | "$SUURI/wakuc/exec/wakuc_4_1" > /dev/null
fi

if run_step 2; then
step "② 厚生年金 給付費推計 を実行（厚年＋共済3制度）"
# 入力順は main.cpp（key, 試算番号, 経済前提, 外枠）→ cntl.cpp（seimei,
# flg_part, flg_sigo, flg_kozax, houjou, flg_inout）の計10個。
# psly/pslsi/pslsi2 は if(key==12||key==13) の中なので key=11 では読まれず、
# 債務の試算（SAIMU=1/2）のときだけ外枠の直後に3つ増えて13個になる。
emp_kyufu_stdin() {
    case "$SAIMU" in
        0) printf '11\n' ;;
        1) printf '12\n' ;;
        2) printf '13\n' ;;
    esac
    printf '%s\n%s\n%s\n' "$SHISAN" "$ECON" "$WAKU"
    if [ "$SAIMU" != 0 ]; then
        printf '25\n2\n1\n'      # 基準年度2025 / 障害遺族は将来分 / 加給等は将来分
    fi
    printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
        "$SEIMEI" "$KAKUDAI" "$SIGO" "$KOZAX" "$HOUJOU" "$((ROUDR-1))"
}
cd "$SUURI/emp" && emp_kyufu_stdin | "$SUURI/emp/exec/usys20" > /dev/null
fi

if run_step 3; then
step "③ 国民年金 を実行"
cd "$SUURI/nat" && "$SUURI/nat/exec/ver0000.out" \
    "$SUURI/nat/io_file/infile.csv" "$SUURI/nat/io_file/outfile.csv" \
    "$SHISAN" "$ECON" "$WAKU" "$BIRTHFILE" "$DEATH" "$SAIMU" 1 "$KAKUDAI" 2027 0 2031 3 "$WAKU" \
    > /dev/null
fi

# ④ 基礎年金（引数17個。順番は原本の jikko_bas.sh と cntl.c:28-60）
#   argv: infile outfile 厚年番号 国年番号 経済前提 外枠 外枠(カット用) 予備
#         過去分 キャリーオーバー 名目下限撤廃 オプション オプション開始年度
#         引上げ間隔 調整期間一致 カット率固定 カット率一本出し
# grep をパイプに挟むと終了状態が隠れるので、ここも PIPESTATUS で見る
run_bas() {   # run_bas <予備番号> <カット率固定 0/1>
    local rc baslog="$SUURI/bas/log/bas-$SHISAN-$SHISAN-$ECON-$WAKU-1120-$1.log"
    # 号別廃止レバーは④が環境変数で受け取る（patches/sango-haishi.patch）
    if [ "$SANGO" != 0 ] || [ "$NIGO" != 0 ]; then
        export SANGO_HAISHI="$SANGO" NIGO_HAISHI="$NIGO" \
               SANGO_NOUFU="$SANGO_NOUFU" SANGO_MODE="$SANGO_MODE"
    else
        unset SANGO_HAISHI NIGO_HAISHI SANGO_NOUFU SANGO_MODE
    fi
    if [ "$ICHIGO" != 0 ]; then
        export ICHIGO_SANGO="$ICHIGO"
    else
        unset ICHIGO_SANGO
    fi
    cd "$SUURI/bas" && set +e
    "$SUURI/bas/exec/ver0000.out" \
        "$SUURI/bas/io_file/infile.csv" "$SUURI/bas/io_file/outfile.csv" \
        "$SHISAN" "$SHISAN" "$ECON" "$WAKU" "$WAKU" "$1" \
        "$SAIMU" "$CARRY" "$DMACRO" 0 2031 3 "$TOUGOU" "$2" 0 \
        | tee "$baslog" | grep -E "終了年度|カット率|給付率|代替率換算|号別被保険者の保険料負担|第1号の第3号登録"
    rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" != "0" ]; then
        die "④ 基礎年金 が異常終了しました（終了コード $rc、予備番号 $1、カット率固定 $2）"
    fi
    # パッチの当たっていない④に環境変数だけ渡すと黙って通常試算になるので、
    # レバーが効いた証拠（パッチが出す1行）が標準出力に無ければ止める
    if { [ "$SANGO" != 0 ] || [ "$NIGO" != 0 ]; } && ! grep -q "号別被保険者の保険料負担" "$baslog"; then
        die "SANGO=$SANGO NIGO=$NIGO を指定しましたが④にレバーが効いていません（ビルドにパッチが当たっていない）。SKIP_BUILD を外してください"
    fi
    if [ "$ICHIGO" != 0 ] && ! grep -q "第1号の第3号登録" "$baslog"; then
        die "ICHIGO=$ICHIGO を指定しましたが④にレバーが効いていません（ビルドにパッチが当たっていない）。SKIP_BUILD を外してください"
    fi
}

if run_step 4; then
step "④ 基礎年金 を実行（マクロ経済スライドの調整終了年度を解く）"
: > "$SUURI/bas/rslt/output.csv"
run_bas "$YOBI" 0

# 基礎年金が出したカット率ファイルを収支計算が読む場所へ渡す
cp "$SUURI/bas/rslt/cuta-$SHISAN-$SHISAN-$ECON-$WAKU-1120-$YOBI.csv" \
   "$SUURI/emp/rslt/ez_arev/cutr/"
fi

# ⑤の標準入力。条件付きで増える2つに注意（収支計算/cntl.c:109-112, 161-164）
#   Flg_Sigo==1 → 続けて waku-m の外枠番号を聞かれる
#   Touitu >=1  → 続けて統一カット率の予備番号を聞かれる
emp_stdin() {
    if [ "$SAIMU" != 0 ]; then
        # 債務の試算では給付水準の決定方法を聞かれず Fpset=9 に固定される。
        # 代わりに 基準年度・障害遺族・加給等・死亡率改善 の4つを聞かれる。
        printf '%s\n25\n2\n1\n1\n' "$SAIMU"
    else
        printf '0\n8\n'
    fi
    printf '%s\n%s\n' "$KAKUDAI" "$SIGO"
    if [ "$SIGO" = 1 ]; then printf '%s\n' "$WAKU_M"; fi
    printf '%s\n%s\n' "$HOUJOU" "$TOUGOU"
    if [ "$TOUGOU" -ge 1 ]; then printf '%s\n' "$YOBI2"; fi
    printf '%s\n%s\n' "$((1 - CARRY))" "$DMACRO"
    printf '%s\n%s\n%s\n%s\n' "$SHISAN" "$ECON" "$WAKU" "$YOBI"
}

if run_step 5; then
step "⑤ 厚生年金 収支計算 を実行（所得代替率）"
# grep をパイプで挟むと終了状態が隠れるので PIPESTATUS で本体の結果を見る
# （ここを素通しにしていたため、⑤が buffer overflow で落ちても「完了」と
#  表示してしまっていた）
# 国庫負担の廃止レバーは⑤が環境変数で受け取る（patches/kokko-cut.patch）
if [ "$KOKKO" != 0 ]; then export KOKKO_CUT="$KOKKO" KOKKO_MODE; else unset KOKKO_CUT KOKKO_MODE; fi
emplog="$SUURI/emp/log/emp-$SHISAN-$SHISAN-$ECON-$WAKU-1120-$YOBI.log"
cd "$SUURI/emp" && set +e
emp_stdin | "$SUURI/emp/exec/asys20" | tee "$emplog" | grep -A 4 "最終代替率\|国庫負担の廃止\|均衡できません\|収束しません"
rc=${PIPESTATUS[1]}
set -e
if [ "$rc" != "0" ]; then
    echo
    echo "★ ⑤ 収支計算 が異常終了しました（終了コード $rc）" >&2
    exit "$rc"
fi
# パッチの当たっていない⑤に環境変数だけ渡すと黙って通常試算になるので止める
if [ "$KOKKO" != 0 ] && ! grep -q "国庫負担の廃止" "$emplog"; then
    die "KOKKO=$KOKKO を指定しましたが⑤にレバーが効いていません（ビルドにパッチが当たっていない）。SKIP_BUILD を外してください"
fi

if [ "$TOUGOU" = 1 ] && run_step 4; then
    step "④ 基礎年金 を再実行（⑤が出した統一カット率 予備$YOBI2 を読む）"
    run_bas "$YOBI2" 1
fi
fi

step_report

echo
echo "############ 完了 ############"
printf '  番号   試算 %s / 経済前提 %s / 外枠 %s / 予備 %s' \
    "$SHISAN" "$ECON" "$WAKU" "$YOBI"
if [ "$TOUGOU" = 1 ]; then printf ' (+%s)' "$YOBI2"; fi
echo
echo "  人口   出生 $JIN / 死亡 $QX / 入国超過 $NC / 労働力率 $ROUDR"
echo "  工程   $STEPS"
case "$SAIMU" in
    1) echo "  債務   過去分試算（既発生債務・基準年度2025年度・AK・_09sum）" ;;
    2) echo "  債務   受給者分試算（既裁定債務・基準年度2025年度・AJ・_09sum）" ;;
esac
echo "  レバー 適用拡大 $KAKUDAI / 45年化 $SIGO / 高在老撤廃 $KOZAX / 報酬上限 $HOUJOU"
echo "         調整期間一致 $TOUGOU / 名目下限撤廃 $DMACRO / キャリーオーバー $CARRY"
if [ "$SANGO" != 0 ] || [ "$NIGO" != 0 ]; then
    echo "  追加   号別 第3号 $SANGO 年度 / 第2号 $NIGO 年度 / 納付率 $SANGO_NOUFU / 構造 $SANGO_MODE（原本にないレバー）"
fi
if [ "$ICHIGO" != 0 ]; then
    echo "  追加   第1号の第3号登録 $ICHIGO 年度（原本にないレバー・思考実験）"
fi
if [ "$KOKKO" != 0 ]; then
    echo "  追加   厚生年金への国庫負担の廃止 $KOKKO 年度・調整方法 $KOKKO_MODE（原本にないレバー・思考実験）"
fi
