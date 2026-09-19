#!/bin/sh
# 原本の 国民年金/econ.c を無修正でビルドし、指定の経済前提ファイルで走らせる。
#
# 原本は EUC-JP（丸数字が NEC特殊文字で入っているため EUCJP-MS を使う）。
# UTF-8 に変換したコピーをビルドディレクトリに作る。
# 変換は iconv による機械的なものだけで、コードには一切手を入れない。
# リポジトリ内の原本は読み取りのみ。
set -e

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SRC="$ROOT/papers/001365945/プログラム/国民年金"
BUILD="${BUILD_DIR:-$(mktemp -d)}"
ECON="${1:-$ROOT/papers/001365945/データ/suuri/rev2024/emp/data/u-rev/econ/econ-3001.csv}"

mkdir -p "$BUILD"

# 原本を UTF-8 に変換してコピー（内容の書き換えはしない）
for f in econ.c stdfm.c snaps.h mecon.h mseid.h mcntl.h mfile_open.h \
         mkisoritu.h mkisosu.h option.h; do
    iconv -f EUCJP-MS -t UTF-8 "$SRC/$f" > "$BUILD/$f"
done
cp "$(dirname "$0")/harness.cpp" "$BUILD/"

# 経済前提ファイルも UTF-8 に（数値とカンマのみなので実質そのまま）
iconv -f EUCJP-MS -t UTF-8 "$ECON" > "$BUILD/econ_input.csv"

cd "$BUILD"
# 原本の snaps.h / stdfm.c が宣言する fdiv() は、新しい glibc の C23 縮小演算
# 関数 fdiv() と名前が衝突する（原本が想定していた古いツールチェーンには
# 無かった関数）。ビルドディレクトリのコピーに対してのみ、識別子を単語単位で
# 改名して回避する。econ.c は fdiv を呼んでいないため、検証対象の計算には
# 一切触れない。リポジトリ内の原本は変更しない。
sed -i 's/\bfdiv\b/nenkin_fdiv/g' snaps.h stdfm.c

g++ -O0 -w -o econ_test harness.cpp econ.c stdfm.c
./econ_test econ_input.csv "$BUILD"

echo "$BUILD"
