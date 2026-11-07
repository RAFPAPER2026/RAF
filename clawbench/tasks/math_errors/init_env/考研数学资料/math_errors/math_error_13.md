# 常系数线性微分方程特解形式设定
- 科目：高等数学
- 难度：较难
- 常见错误率：55%

## 题目

求微分方程 $y'' + 4y = \sin 2x$ 的一个特解。

## 常见错误

设特解形式为 $y^* = A\sin 2x + B\cos 2x$，代入方程：

$y^{*'} = 2A\cos 2x - 2B\sin 2x$

$y^{*''} = -4A\sin 2x - 4B\cos 2x$

代入：$(-4A\sin 2x - 4B\cos 2x) + 4(A\sin 2x + B\cos 2x) = \sin 2x$

得 $0 = \sin 2x$，矛盾！无法确定 $A$, $B$。

## 错误原因分析

1. 未检查右端项 $\sin 2x$ 是否是齐次方程的解：$y'' + 4y = 0$ 的特征方程 $r^2 + 4 = 0$，$r = \pm 2i$，齐次通解含 $\sin 2x$ 和 $\cos 2x$
2. 当非齐次项与齐次解重合时，特解需乘以 $x$（即提高一次幂），这是待定系数法的关键规则
3. 规则：若右端项 $e^{\alpha x}[P_m(x)\cos\beta x + Q_n(x)\sin\beta x]$ 中 $\alpha + i\beta$ 是特征方程的 $k$ 重根，则特解设为 $x^k e^{\alpha x}[R_l(x)\cos\beta x + S_l(x)\sin\beta x]$

## 正确解法

特征方程 $r^2 + 4 = 0$，$r = \pm 2i$。

右端项 $\sin 2x$ 对应 $\alpha = 0$，$\beta = 2$，$\alpha + i\beta = 2i$ 是特征方程的单根（$k = 1$）。

特解应设为：

$$y^* = x(A\sin 2x + B\cos 2x)$$

求导：

$$y^{*'} = A\sin 2x + B\cos 2x + x(2A\cos 2x - 2B\sin 2x)$$

$$y^{*''} = 2A\cos 2x - 2B\sin 2x + (2A\cos 2x - 2B\sin 2x) + x(-4A\sin 2x - 4B\cos 2x)$$

$$= 4A\cos 2x - 4B\sin 2x - 4x(A\sin 2x + B\cos 2x)$$

代入方程：

$$4A\cos 2x - 4B\sin 2x - 4x(A\sin 2x + B\cos 2x) + 4x(A\sin 2x + B\cos 2x) = \sin 2x$$

$$4A\cos 2x - 4B\sin 2x = \sin 2x$$

比较系数：$4A = 0$，$-4B = 1$，得 $A = 0$，$B = -\frac{1}{4}$。

$$y^* = -\frac{x}{4}\cos 2x$$

## 易错点总结

设特解前必须检查右端项是否与齐次解重合，若重合则特解需乘以 $x^k$（$k$ 为特征根重数）。