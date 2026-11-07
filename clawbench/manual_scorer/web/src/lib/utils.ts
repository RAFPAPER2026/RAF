/** URL 路径段编码（任务名可能含特殊字符） */
export function enc(s: string): string {
  return encodeURIComponent(s);
}

/** 文件大小格式化 */
export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** 分数（0-1）转百分比文本 */
export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-';
  return `${(v * 100).toFixed(digits)}%`;
}

/** 后端已是百分数（0-100）的比率 → 百分比字符串（pass_rate 等） */
export function pctRate(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-';
  return `${v.toFixed(digits)}%`;
}

/** 触发浏览器下载 Blob */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/** 友好错误文本 */
export function errText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}
