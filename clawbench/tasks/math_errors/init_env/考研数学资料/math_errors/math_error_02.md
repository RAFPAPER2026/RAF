# 等价无穷小替换的适用条件
- 科目：高等数学
- 章节：第一章 函数与极限
- 难度：较难
- 常见错误率：62%

## 题目

求极限 $\lim_{x \to 0} \frac{\tan x - \sin x}{x^3}$。

## 常见错误

直接对分子中的 $\tan x$ 和 $\sin x$ 分别用等价无穷小替换：

$$\lim_{x \to 0} \frac{\tan x - \sin x}{x^3} = \lim_{x \to 0} \frac{x - x}{x^3} = 0$$

这是**错误**的！等价无穷小替换不能在加减法中随意使用。

## 错误原因分析

1. 等价无穷小替换的核心规则：**乘除法中可以替换，加减法中一般不能替换**
2. 当 $\tan x \sim x$，$\sin x \sim x$ 时，$\tan x - \sin x$ 是两个等价无穷小之差，差的阶数比各自都高，直接替换会丢失高阶信息
3. 本质原因：$\tan x - \sin x = \frac{\sin x(1 - \cos x)}{\cos x}$，其中 $1 - \cos x \sim \frac{x^2}{2}$ 是二阶无穷小，直接替换 $x - x = 0$ 丢失了这一关键信息

## 正确解法

**方法一：先化简再替换**

$$\tan x - \sin x = \frac{\sin x}{\cos x} - \sin x = \sin x \cdot \frac{1 - \cos x}{\cos x}$$

$$\lim_{x \to 0} \frac{\sin x \cdot \frac{1 - \cos x}{\cos x}}{x^3} = \lim_{x \to 0} \frac{\sin x}{x} \cdot \frac{1 - \cos x}{x^2} \cdot \frac{1}{\cos x} = 1 \cdot \frac{1}{2} \cdot 1 = \frac{1}{2}$$

**方法二：泰勒展开**

$$\tan x = x + \frac{x^3}{3} + o(x^3), \quad \sin x = x - \frac{x^3}{6} + o(x^3)$$

$$\tan x - \sin x = \frac{x^3}{2} + o(x^3)$$

$$\lim_{x \to 0} \frac{\frac{x^3}{2} + o(x^3)}{x^3} = \frac{1}{2}$$

## 易错点总结

等价无穷小替换只适用于乘除因子，加减法中的等价无穷小替换可能丢失高阶信息导致错误。