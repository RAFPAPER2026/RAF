// 量规列表页：搜索、去重、分页、选择对比、删除与去重清理
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ClipboardCheck,
  Eraser,
  GitCompare,
  Pencil,
  Plus,
  Search,
  Star,
  Trash2,
  X,
} from "lucide-react";
import * as api from "../lib/api";
import { QueryRubricListItem } from "../lib/types";
import RubricTree from "../components/RubricTree";
import { collectLeafNames } from "../lib/tree";

const PAGE_SIZE = 20;

export default function RubricListPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<QueryRubricListItem[]>([]);
  const [search, setSearch] = useState("");
  const [dedup, setDedup] = useState(false);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  const flash = (msg: string) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(""), 4000);
  };

  const load = async (over: { search?: string; dedup?: boolean; page?: number } = {}) => {
    setLoading(true);
    setError("");
    const srch = (over.search ?? search).trim();
    const ddp = over.dedup ?? dedup;
    const pg = over.page ?? page;
    try {
      const params: { search?: string; dedup?: boolean; limit: number; offset: number } = {
        limit: PAGE_SIZE,
        offset: (pg - 1) * PAGE_SIZE,
      };
      if (srch) params.search = srch;
      if (ddp) params.dedup = true;
      setItems(await api.listRubrics(params));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    setPage(1);
    load({ search, page: 1 });
  };

  const handleDedup = (checked: boolean) => {
    setDedup(checked);
    setPage(1);
    load({ dedup: checked, page: 1 });
  };

  const goPage = (p: number) => {
    setPage(p);
    load({ page: p });
  };

  const toggleSelect = (id: string) => {
    if (selected.includes(id)) {
      setSelected(selected.filter((x) => x !== id));
      return;
    }
    if (selected.length >= 2) {
      flash("最多选择 2 条进行对比");
      return;
    }
    setSelected([...selected, id]);
  };

  const handleDelete = async (r: QueryRubricListItem) => {
    if (!window.confirm(`删除量规「${r.query.slice(0, 40)}${r.query.length > 40 ? "…" : ""}」？`)) return;
    try {
      await api.deleteRubric(r.id);
      setSelected((prev) => prev.filter((x) => x !== r.id));
      flash("已删除");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleCleanup = async () => {
    if (!window.confirm("确认清理全部重复量规数据？")) return;
    try {
      const res = await api.cleanupRubrics();
      flash(`已清理 ${res.removed} 条重复数据`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  // 对比的两条记录
  const selItems = items.filter((i) => selected.includes(i.id));
  const a = selItems[0];
  const b = selItems[1];

  // 叶子差异：completion 与 quality 叶子名合并后求集合差
  const onlyA: string[] = [];
  const onlyB: string[] = [];
  if (compareOpen && a && b) {
    const namesA = new Set([
      ...collectLeafNames(a.completion_rubric),
      ...collectLeafNames(a.quality_rubric.map((it) => it.node)),
    ]);
    const namesB = new Set([
      ...collectLeafNames(b.completion_rubric),
      ...collectLeafNames(b.quality_rubric.map((it) => it.node)),
    ]);
    for (const n of namesA) if (!namesB.has(n)) onlyA.push(n);
    for (const n of namesB) if (!namesA.has(n)) onlyB.push(n);
  }

  return (
    <div>
      <div className="page-title">量规列表</div>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}
      {message && (
        <div className="mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
          {message}
        </div>
      )}

      {/* 工具栏 */}
      <div className="card mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input w-72"
            value={search}
            placeholder="搜索 query…"
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <button className="btn" onClick={handleSearch}>
            <Search size={14} /> 搜索
          </button>
          <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={dedup}
              onChange={(e) => handleDedup(e.target.checked)}
            />
            去重（query + 版本）
          </label>
          <div className="flex-1" />
          <button className="btn" onClick={handleCleanup} title="按 query + 版本清理重复数据">
            <Eraser size={14} /> 去重清理
          </button>
          <button className="btn-primary" onClick={() => navigate("/builder")}>
            <Plus size={14} /> 新建量规
          </button>
          <button
            className="btn"
            disabled={selected.length !== 2}
            title={selected.length === 2 ? "对比选中的两条量规" : "请先勾选 2 条量规"}
            onClick={() => setCompareOpen(true)}
          >
            <GitCompare size={14} /> 对比
          </button>
        </div>
      </div>

      {/* 列表 */}
      <div className="card">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b border-gray-200">
              <th className="py-2 pr-2 font-medium w-8"></th>
              <th className="py-2 pr-2 font-medium">Query</th>
              <th className="py-2 pr-2 font-medium w-24">版本</th>
              <th className="py-2 pr-2 font-medium w-32">标签</th>
              <th className="py-2 pr-2 font-medium w-28">审核</th>
              <th className="py-2 font-medium w-44">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-2 pr-2">
                  <input
                    type="checkbox"
                    checked={selected.includes(r.id)}
                    onChange={() => toggleSelect(r.id)}
                  />
                </td>
                <td className="py-2 pr-2 text-gray-700 max-w-[24rem]" title={r.query}>
                  <span className="line-clamp-2">{r.query}</span>
                </td>
                <td className="py-2 pr-2">
                  <span className="tag">{r.prompt_version}</span>
                </td>
                <td className="py-2 pr-2">
                  <div className="flex gap-1 flex-wrap">
                    {r.query_tags.map((t) => (
                      <span key={t} className="tag">
                        {t}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-2 pr-2 text-xs text-gray-500">
                  {r.review_count > 0
                    ? `${r.review_count} 条 · C${r.review_avg_completion ?? 0}/Q${r.review_avg_quality ?? 0}`
                    : "—"}
                </td>
                <td className="py-2">
                  <div className="flex gap-1">
                    <button className="btn text-xs py-1" title="评分" onClick={() => navigate(`/scorer/${r.id}`)}>
                      <Star size={12} /> 评分
                    </button>
                    <button className="btn text-xs py-1" title="审核" onClick={() => navigate(`/review/${r.id}`)}>
                      <ClipboardCheck size={12} /> 审核
                    </button>
                    <button className="btn text-xs py-1" title="编辑" onClick={() => navigate(`/builder/${r.id}`)}>
                      <Pencil size={12} /> 编辑
                    </button>
                    <button className="btn-danger text-xs py-1" title="删除" onClick={() => handleDelete(r)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {loading && items.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-gray-400">
                  加载中…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-gray-400">
                  暂无量规数据
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>

        {/* 分页 */}
        <div className="flex items-center justify-end gap-2 mt-3">
          <button className="btn" disabled={page === 1} onClick={() => goPage(page - 1)}>
            上一页
          </button>
          <span className="text-sm text-gray-500">第 {page} 页</span>
          <button className="btn" disabled={items.length < PAGE_SIZE} onClick={() => goPage(page + 1)}>
            下一页
          </button>
        </div>
      </div>

      {/* 对比弹窗 */}
      {compareOpen && a && b && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setCompareOpen(false)}>
          <div
            className="bg-white rounded-lg shadow-xl w-[95%] max-w-5xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <GitCompare size={16} className="text-gray-500 shrink-0" />
                <span className="text-sm font-semibold text-gray-800 whitespace-nowrap shrink-0">版本对比</span>
                <span className="text-xs text-gray-500 max-w-[14rem] truncate shrink-0" title={a.query}>
                  {a.query}
                </span>
                <span className="tag shrink-0">{a.prompt_version}</span>
                <span className="text-xs text-gray-400 shrink-0">vs</span>
                <span className="text-xs text-gray-500 max-w-[14rem] truncate shrink-0" title={b.query}>
                  {b.query}
                </span>
                <span className="tag shrink-0">{b.prompt_version}</span>
              </div>
              <button className="btn shrink-0" onClick={() => setCompareOpen(false)} title="关闭">
                <X size={14} /> 关闭
              </button>
            </div>

            <div className="flex-1 overflow-auto p-4">
              {/* 两列并排 */}
              <div className="grid grid-cols-2 gap-4 overflow-auto">
                {[a, b].map((r, idx) => (
                  <div key={r.id} className="space-y-3">
                    <div className="text-xs text-gray-400">
                      {idx === 0 ? "A" : "B"}：{r.query}
                    </div>
                    <div className="bg-gray-50 rounded-md p-2">
                      <div className="text-xs font-semibold text-gray-600 mb-1">完成量规</div>
                      <RubricTree nodes={r.completion_rubric} mode="view" />
                    </div>
                    <div className="bg-gray-50 rounded-md p-2">
                      <div className="text-xs font-semibold text-gray-600 mb-1">质量量规</div>
                      {r.quality_rubric.map((item) => (
                        <div key={item.node.id} className="mb-2 last:mb-0">
                          <span className="tag">{`w=${item.weight}`}</span>
                          <RubricTree nodes={[item.node]} mode="view" />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* 叶子差异 */}
              <div className="mt-4 pt-3 border-t border-gray-200">
                <div className="section-title mb-1">叶子差异</div>
                {onlyA.length === 0 && onlyB.length === 0 ? (
                  <div className="text-sm text-gray-500">两棵树的叶子名称完全一致</div>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs font-medium text-red-600 mb-1">仅 A 有（{onlyA.length}）</div>
                      <ul className="text-sm text-red-600 space-y-0.5">
                        {onlyA.map((n) => (
                          <li key={n}>{n}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <div className="text-xs font-medium text-green-600 mb-1">仅 B 有（{onlyB.length}）</div>
                      <ul className="text-sm text-green-600 space-y-0.5">
                        {onlyB.map((n) => (
                          <li key={n}>{n}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
