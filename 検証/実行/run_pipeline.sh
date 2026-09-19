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

# ⑤は Touitu>=1 のとき cuta/cutb を YOBI と YOBI2 の2組そろえて書き込み用に
# 開く（fopn.c:158-190）。同じ番号だと同名のファイルを2つのハンドルで開いて
# 中身が壊れるので、ここで止める。
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

step() { echo; echo "############ $* ############"; }
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
# psly/pslsi/pslsi2 は if(key==12||key==13) の中なので key=11 では読まれない。
cd "$SUURI/emp" && printf "11\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n" \
    "$SHISAN" "$ECON" "$WAKU" "$SEIMEI" \
    "$KAKUDAI" "$SIGO" "$KOZAX" "$HOUJOU" "$((ROUDR-1))" \
    | "$SUURI/emp/exec/usys20" > /dev/null
fi

if run_step 3; then
step "③ 国民年金 を実行"
cd "$SUURI/nat" && "$SUURI/nat/exec/ver0000.out" \
    "$SUURI/nat/io_file/infile.csv" "$SUURI/nat/io_file/outfile.csv" \
    "$SHISAN" "$ECON" "$WAKU" "$BIRTHFILE" "$DEATH" 0 1 "$KAKUDAI" 2027 0 2031 3 "$WAKU" \
    > /dev/null
fi

# ④ 基礎年金（引数17個。順番は原本の jikko_bas.sh と cntl.c:28-60）
#   argv: infile outfile 厚年番号 国年番号 経済前提 外枠 外枠(カット用) 予備
#         過去分 キャリーオーバー 名目下限撤廃 オプション オプション開始年度
#         引上げ間隔 調整期間一致 カット率固定 カット率一本出し
# grep をパイプに挟むと終了状態が隠れるので、ここも PIPESTATUS で見る
run_bas() {   # run_bas <予備番号> <カット率固定 0/1>
    local rc
    cd "$SUURI/bas" && set +e
    "$SUURI/bas/exec/ver0000.out" \
        "$SUURI/bas/io_file/infile.csv" "$SUURI/bas/io_file/outfile.csv" \
        "$SHISAN" "$SHISAN" "$ECON" "$WAKU" "$WAKU" "$1" \
        0 "$CARRY" "$DMACRO" 0 2031 3 "$TOUGOU" "$2" 0 \
        | grep -E "終了年度|カット率|給付率|代替率換算"
    rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" != "0" ]; then
        die "④ 基礎年金 が異常終了しました（終了コード $rc、予備番号 $1、カット率固定 $2）"
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
    printf '0\n8\n%s\n%s\n' "$KAKUDAI" "$SIGO"
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
cd "$SUURI/emp" && set +e
emp_stdin | "$SUURI/emp/exec/asys20" | grep -A 4 "最終代替率"
rc=${PIPESTATUS[1]}
set -e
if [ "$rc" != "0" ]; then
    echo
    echo "★ ⑤ 収支計算 が異常終了しました（終了コード $rc）" >&2
    exit "$rc"
fi

if [ "$TOUGOU" = 1 ] && run_step 4; then
    step "④ 基礎年金 を再実行（⑤が出した統一カット率 予備$YOBI2 を読む）"
    run_bas "$YOBI2" 1
fi
fi

echo
echo "############ 完了 ############"
printf '  番号   試算 %s / 経済前提 %s / 外枠 %s / 予備 %s' \
    "$SHISAN" "$ECON" "$WAKU" "$YOBI"
if [ "$TOUGOU" = 1 ]; then printf ' (+%s)' "$YOBI2"; fi
echo
echo "  人口   出生 $JIN / 死亡 $QX / 入国超過 $NC / 労働力率 $ROUDR"
echo "  工程   $STEPS"
echo "  レバー 適用拡大 $KAKUDAI / 45年化 $SIGO / 高在老撤廃 $KOZAX / 報酬上限 $HOUJOU"
echo "         調整期間一致 $TOUGOU / 名目下限撤廃 $DMACRO / キャリーオーバー $CARRY"
