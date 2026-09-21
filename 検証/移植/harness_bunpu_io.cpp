/* ===========================================================================
 * bunpu/prog03.py の差分テスト用ハーネス
 * ===========================================================================
 * 原本 分布推計/prog03.cpp をそのままリンクして func03a / func03b を呼び、
 * 結果を機械で読める形に出す。
 *
 * func03a は「区切り文字が1つも無い行でフィールドを2回返す」という癖が
 * あるので、そこを実測で押さえるのが主目的。
 *
 * 出力
 *   a <件数> <長さ>:<中身> …      func03a の結果（長さ付きで空文字列も区別）
 *   b <行数>                       func03b の行数
 *   br <行番号> <件数> <長さ>:<中身> …
 * ======================================================================== */
#include <cstdio>
#include <string>
#include <vector>

#include "_prototype.h"

static void dump(const std::vector<std::string>& v){
	printf(" %zu", v.size());
	for (size_t i = 0; i < v.size(); ++i)
		printf(" %zu:%s", v[i].size(), v[i].c_str());
	printf("\n");
}

int main(int ac, char **av){
	/* 1つ目の引数が "a" なら func03a、"b" なら func03b */
	if (ac >= 3 && std::string(av[1]) == "a") {
		/* 残りの引数を1つずつ func03a にかける */
		for (int i = 2; i < ac; ++i) {
			printf("a");
			dump(func_orig::func03a(std::string(av[i]), ','));
		}
	} else if (ac >= 4 && std::string(av[1]) == "b") {
		const int skip = atoi(av[3]);
		std::vector<std::vector<std::string>> t
			= func_orig::func03b(std::string(av[2]), skip);
		printf("b %zu\n", t.size());
		for (size_t r = 0; r < t.size(); ++r) {
			printf("br %zu", r);
			dump(t[r]);
		}
	} else {
		fprintf(stderr, "使い方: %s a <文字列>… | %s b <パス> <読み飛ばし行数>\n",
		        av[0], av[0]);
		return 2;
	}
	return 0;
}
