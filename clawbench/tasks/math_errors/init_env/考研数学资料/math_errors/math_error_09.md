# 实对称矩阵正交对角化步骤遗漏
- 科目：线性代数
- 章节：第五章 特征值与特征向量
- 难度：较难
- 常见错误率：52%

## 题目

将实对称矩阵 $A = \begin{pmatrix} 2 & -2 \\ -2 & 5 \end{pmatrix}$ 正交对角化，即求正交矩阵 $Q$，使 $Q^{-1}AQ = \Lambda$。

## 常见错误

**错误一**：求出特征向量后直接作为 $Q$ 的列向量，未进行正交化和单位化。

**错误二**：对不同特征值对应的特征向量进行了施密特正交化（实际上不同特征值对应的特征向量已经正交，只需单位化）。

**错误三**：对同一特征值对应的多个线性无关特征向量忘记进行施密特正交化。

## 错误原因分析

1. 混淆"对角化"和"正交对角化"：对角化只需 $P^{-1}AP = \Lambda$，正交对角化要求 $Q$ 是正交矩阵
2. 正交矩阵要求列向量两两正交且单位化，这两个步骤缺一不可
3. 对"不同特征值的特征向量自动正交"这一性质不熟悉，导致多做或漏做正交化

## 正确解法

**第一步：求特征值**

$$|A - \lambda I| = \begin{vmatrix} 2-\lambda & -2 \\ -2 & 5-\lambda \end{vmatrix} = (2-\lambda)(5-\lambda) - 4 = \lambda^2 - 7\lambda + 6 = (\lambda - 1)(\lambda - 6) = 0$$

$\lambda_1 = 1$，$\lambda_2 = 6$。

**第二步：求特征向量**

$\lambda_1 = 1$：$(A - I)x = 0$，即 $\begin{pmatrix} 1 & -2 \\ -2 & 4 \end{pmatrix}x = 0$，得 $\alpha_1 = (2, 1)^T$。

$\lambda_2 = 6$：$(A - 6I)x = 0$，即 $\begin{pmatrix} -4 & -2 \\ -2 & -1 \end{pmatrix}x = 0$，得 $\alpha_2 = (1, -2)^T$。

**第三步：单位化**

不同特征值对应的特征向量已自动正交（验证：$\alpha_1 \cdot \alpha_2 = 2 - 2 = 0$ ✓），只需单位化：

$$q_1 = \frac{\alpha_1}{|\alpha_1|} = \frac{1}{\sqrt{5}}\begin{pmatrix} 2 \\ 1 \end{pmatrix}, \quad q_2 = \frac{\alpha_2}{|\alpha_2|} = \frac{1}{\sqrt{5}}\begin{pmatrix} 1 \\ -2 \end{pmatrix}$$

**第四步：写出结果**

$$Q = \frac{1}{\sqrt{5}}\begin{pmatrix} 2 & 1 \\ 1 & -2 \end{pmatrix}, \quad Q^{-1}AQ = Q^TAQ = \begin{pmatrix} 1 & 0 \\ 0 & 6 \end{pmatrix}$$

## 易错点总结

正交对角化要求 $Q$ 为正交矩阵：不同特征值的特征向量自动正交只需单位化，同一特征值的多个特征向量需先施密特正交化再单位化。