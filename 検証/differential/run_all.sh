#!/bin/sh
# 同梱8ケースすべてで差分テストを回す
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$DIR/../.." && pwd)
ECONDIR="$ROOT/papers/001365945/データ/suuri/rev2024/emp/data/u-rev/econ"
FAIL=0
for f in "$ECONDIR"/econ-*.csv; do
    name=$(basename "$f")
    BUILD=$(mktemp -d)
    BUILD_DIR="$BUILD" "$DIR/build_and_run.sh" "$f" > /dev/null
    echo "--- $name ---"
    if python3 "$DIR/compare.py" "$BUILD" | tail -3 | head -2; then :; else FAIL=1; fi
    rm -rf "$BUILD"
done
exit $FAIL
