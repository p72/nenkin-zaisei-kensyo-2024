/* ===========================================================================
 * cppstd.py の差分テスト用ハーネス
 * ===========================================================================
 * ⑥分布推計が使う `std::mt19937(0)` と `std::shuffle` のふるまいを、
 * **その場の libstdc++ から**取り出す。値を埋め込まずに毎回コンパイルして
 * 問い合わせるので、標準ライブラリが変わったら気付ける。
 *
 * 出力
 *   raw <32bit値> …            mt19937(0) の生の列
 *   shuf <n> <並び> | <次の値>  n 要素をシャッフルした結果と、消費後の次の乱数
 *   rep <回数> <並び>           同じ生成器で続けてシャッフルした結果
 *   ver <gcc> <libstdc++>      版
 * ======================================================================== */
#include <algorithm>
#include <cstdio>
#include <numeric>
#include <random>
#include <vector>

int main(void){
	/* 生の列 */
	{
		std::mt19937 g(0);
		printf("raw");
		for (int i = 0; i < 16; ++i) printf(" %lu", (unsigned long)g());
		printf("\n");
	}

	/* いろいろな要素数。小さい所と、Lemire 法で差が出る所を混ぜる */
	const int ns[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16, 17,
	                  31, 32, 33, 63, 64, 65, 99, 100, 101, 127, 128,
	                  255, 256, 257, 275, 511, 512, 1000, 1001, 4095, 5000};
	const int nn = (int)(sizeof ns / sizeof ns[0]);
	for (int t = 0; t < nn; ++t) {
		const int n = ns[t];
		std::mt19937 g(0);
		std::vector<int> v(n);
		std::iota(v.begin(), v.end(), 0);
		std::shuffle(v.begin(), v.end(), g);
		printf("shuf %d", n);
		for (int i = 0; i < n; ++i) printf(" %d", v[i]);
		printf(" | %lu\n", (unsigned long)g());
	}

	/* 同じ生成器で続けてシャッフル（原本は毎年呼ぶ） */
	{
		std::mt19937 g(0);
		std::vector<int> v(137);
		std::iota(v.begin(), v.end(), 0);
		for (int r = 0; r < 10; ++r) {
			std::shuffle(v.begin(), v.end(), g);
			printf("rep %d", r);
			for (int i = 0; i < 137; ++i) printf(" %d", v[i]);
			printf("\n");
		}
	}

	printf("ver %d.%d.%d %d\n", __GNUC__, __GNUC_MINOR__, __GNUC_PATCHLEVEL__,
	       __GLIBCXX__);
	return 0;
}
