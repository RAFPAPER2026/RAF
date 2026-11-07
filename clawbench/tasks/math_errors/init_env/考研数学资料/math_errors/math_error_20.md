# 最大似然估计中似然函数构造错误
- 科目：概率论与数理统计
- 难度：中等
- 常见错误率：49%

## 题目

设总体 $X \sim N(\mu, \sigma^2)$，其中 $\mu$ 和 $\sigma^2$ 均未知，$x_1, x_2, \ldots, x_n$ 为样本观测值，求 $\mu$ 和 $\sigma^2$ 的最大似然估计。

## 常见错误

**错误一**：似然函数写成样本的联合概率密度，但把 $\sigma^2$ 和 $\sigma$ 混淆，写成：

$$L = \prod_{i=1}^n \frac{1}{\sqrt{2\pi}\sigma^2} e^{-\frac{(x_i - \mu)^2}{2\sigma^4}}$$

分母应为 $\sigma$ 而非 $\sigma^2$，指数分母应为 $2\sigma^2$ 而非 $2\sigma^4$。

**错误二**：对对数似然函数求导时，对 $\sigma^2$ 求导而非对 $\sigma$ 求导，但未使用链式法则，导致导数计算错误。

**错误三**：求 $\sigma^2$ 的估计时，令 $\frac{\partial \ln L}{\partial \sigma} = 0$ 解出 $\hat{\sigma}$，然后直接写 $\hat{\sigma}^2$ 为 $\sigma^2$ 的估计，但计算过程出错。

## 错误原因分析

1. 正态分布密度函数公式记忆不牢：$f(x) = \frac{1}{\sqrt{2\pi}\sigma} e^{-\frac{(x-\mu)^2}{2\sigma^2}}$
2. 似然函数是样本联合密度（连续型）或联合概率（离散型），构造时需注意每个观测值的贡献
3. 对 $\sigma^2$ 求最大似然估计时，可以直接对 $\sigma^2$ 求导（令 $\theta = \sigma^2$），避免链式法则的复杂性

## 正确解法

**第一步：构造似然函数**

$$L(\mu, \sigma^2) = \prod_{i=1}^n \frac{1}{\sqrt{2\pi}\sigma} e^{-\frac{(x_i-\mu)^2}{2\sigma^2}} = (2\pi)^{-n/2} (\sigma^2)^{-n/2} e^{-\frac{1}{2\sigma^2}\sum_{i=1}^n(x_i-\mu)^2}$$

**第二步：对数似然函数**

$$\ln L = -\frac{n}{2}\ln(2\pi) - \frac{n}{2}\ln(\sigma^2) - \frac{1}{2\sigma^2}\sum_{i=1}^n(x_i-\mu)^2$$

**第三步：对 $\mu$ 求偏导**

$$\frac{\partial \ln L}{\partial \mu} = \frac{1}{\sigma^2}\sum_{i=1}^n(x_i - \mu) = 0$$

$$\Rightarrow \sum_{i=1}^n x_i = n\mu \Rightarrow \hat{\mu} = \bar{x} = \frac{1}{n}\sum_{i=1}^n x_i$$

**第四步：对 $\sigma^2$ 求偏导**

令 $\theta = \sigma^2$：

$$\frac{\partial \ln L}{\partial \theta} = -\frac{n}{2\theta} + \frac{1}{2\theta^2}\sum_{i=1}^n(x_i - \mu)^2 = 0$$

$$\Rightarrow n\theta = \sum_{i=1}^n(x_i - \mu)^2 \Rightarrow \hat{\sigma}^2 = \frac{1}{n}\sum_{i=1}^n(x_i - \bar{x})^2$$

## 易错点总结

构造似然函数时密度函数公式要准确；对 $\sigma^2$ 求导时建议令 $\theta = \sigma^2$ 直接对 $\theta$ 求导，避免链式法则出错。