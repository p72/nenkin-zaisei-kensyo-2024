/* ===========================================================================
 * ⑥分布推計で使う細かい C/C++ の意味を、その場の処理系から取り出す
 * ===========================================================================
 * 3つを問い合わせる。
 *
 *   g <16進の double>   `std::setprecision(15) << v` の出力
 *                       （prog13.cpp の数値の書き方）
 *   m <a> <b>           C の `a % b`（prog09.cpp:90 の var006 % 10000）
 *   i <16進> <16進> …   `int v=0; v += double;` を並べた結果
 *                       （prog13.cpp:49 の合計）
 *
 * 引数は「種別 値…」を1組ずつ。1行に1つ答えを出す。
 * ======================================================================== */
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

int main(int ac, char **av){
	int i = 1;
	while (i < ac) {
		std::string kind(av[i++]);
		if (kind == "g") {
			double v = strtod(av[i++], NULL);
			std::ostringstream os;
			os << std::setprecision(15) << v;
			printf("%s\n", os.str().c_str());
		} else if (kind == "m") {
			int a = atoi(av[i++]);
			int b = atoi(av[i++]);
			printf("%d\n", a % b);
		} else if (kind == "i") {
			int n = atoi(av[i++]);
			int acc = 0;
			for (int k = 0; k < n; ++k) acc += strtod(av[i++], NULL);
			printf("%d\n", acc);
		} else {
			printf("?\n");
			return 1;
		}
	}
	return 0;
}
