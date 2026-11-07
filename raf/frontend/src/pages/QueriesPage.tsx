// Query 管理：CRUD、标签、批量导入导出
import { useEffect, useRef, useState } from "react";
import { Database, Download, FileUp, Plus, RefreshCw, Trash2 } from "lucide-react";
import * as api from "../lib/api";
import { QueryItem } from "../lib/types";

export default function QueriesPage() {
  const [queries, setQueries] = useState<QueryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [newText, setNewText] = useState("");
  const [batchText, setBatchText] = useState("");
  const [importJson, setImportJson] = useState("");
  const [editing, setEditing] = useState<QueryItem | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const flash = (msg: string) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(""), 4000);
  };

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setQueries(await api.listQueries());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    if (!newText.trim()) return;
    try {
      await api.createQuery(newText.trim());
      setNewText("");
      flash("已创建 query");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleBatch = async () => {
    const texts = batchText.split("\n").map((t) => t.trim()).filter(Boolean);
    if (!texts.length) return;
    try {
      const res = await api.batchCreateQueries(texts);
      setBatchText("");
      flash(`批量创建完成：新增 ${res.created} 条（共 ${res.total} 条，按 text 去重）`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleDelete = async (q: QueryItem) => {
    if (!window.confirm(`删除 query「${q.text.slice(0, 40)}…」？（被 rubric 引用时无法删除）`)) return;
    try {
      await api.deleteQuery(q.id);
      flash("已删除");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSave = async () => {
    if (!editing) return;
    try {
      await api.updateQuery(editing.id, {
        text: editing.text,
        tags: editing.tags,
      });
      setEditing(null);
      flash("已保存");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleImportJson = async () => {
    try {
      const items = JSON.parse(importJson);
      if (!Array.isArray(items)) throw new Error("JSON 需为数组");
      const payload = items.map((it) => ({
        text: String(it.text ?? it),
        tags: Array.isArray(it.tags) ? it.tags : [],
      }));
      const res = await api.importQueriesJson(payload);
      setImportJson("");
      flash(`JSON 导入完成：新增 ${res.created} 条（按 text 去重）`);
      await load();
    } catch (e) {
      setError(`JSON 解析失败：${e}`);
    }
  };

  const handleImportExcel = async (file: File) => {
    try {
      const res = await api.importQueriesExcel(file);
      flash(`Excel 导入完成：新增 ${res.created} 条`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleMigrate = async () => {
    try {
      const res = await api.migrateQueries();
      flash(`迁移完成：共 ${res.query_count} 条 query，回填 ${res.updated_rubrics} 条 rubric`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <div className="page-title flex items-center gap-2">
        <Database size={20} /> Query 管理
      </div>

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

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* 左：添加与批量 */}
        <div className="space-y-4">
          <div className="card">
            <div className="section-title">添加 query</div>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                value={newText}
                placeholder="输入单条 query 文本"
                onChange={(e) => setNewText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
              <button className="btn-primary" onClick={handleCreate}>
                <Plus size={14} /> 添加
              </button>
            </div>
          </div>

          <div className="card">
            <div className="section-title">批量添加（每行一条，按 text 去重）</div>
            <textarea
              className="input w-full h-28 font-mono text-xs"
              value={batchText}
              placeholder={"帮我安排一次北京到上海的出差行程\n整理本周会议纪要"}
              onChange={(e) => setBatchText(e.target.value)}
            />
            <div className="mt-2 flex justify-end">
              <button className="btn-primary" onClick={handleBatch}>
                批量创建
              </button>
            </div>
          </div>

          <div className="card">
            <div className="section-title">导入 / 导出 / 迁移</div>
            <div className="space-y-2">
              <textarea
                className="input w-full h-24 font-mono text-xs"
                value={importJson}
                placeholder='[{"text": "query 文本", "tags": ["标签"]}]'
                onChange={(e) => setImportJson(e.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                <button className="btn" onClick={handleImportJson}>
                  JSON 导入
                </button>
                <button className="btn" onClick={() => fileRef.current?.click()}>
                  <FileUp size={14} /> Excel 导入
                </button>
                <a className="btn" href={api.exportQueriesUrl} download>
                  <Download size={14} /> 导出 Excel
                </a>
                <button className="btn" onClick={handleMigrate} title="从 rubrics.json 提取唯一 query 建 QueryItem 并回填 query_id">
                  从 rubrics 迁移
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleImportExcel(f);
                    e.target.value = "";
                  }}
                />
              </div>
              <div className="text-xs text-gray-400">Excel 列格式：id / text / tags（表头可省略，text 列必填）</div>
            </div>
          </div>
        </div>

        {/* 右：列表 */}
        <div className="card xl:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <div className="section-title mb-0">全部 query（{queries.length}）</div>
            <button className="btn" disabled={loading} onClick={load}>
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> 刷新
            </button>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-200">
                <th className="py-2 pr-2 font-medium">文本</th>
                <th className="py-2 pr-2 font-medium w-28">标签</th>
                <th className="py-2 pr-2 font-medium w-16">rubric</th>
                <th className="py-2 pr-2 font-medium w-32">更新时间</th>
                <th className="py-2 font-medium w-20">操作</th>
              </tr>
            </thead>
            <tbody>
              {queries.map((q) =>
                editing?.id === q.id ? (
                  <tr key={q.id} className="border-b border-gray-100">
                    <td className="py-2 pr-2" colSpan={2}>
                      <input
                        className="input w-full"
                        value={editing.text}
                        onChange={(e) => setEditing({ ...editing, text: e.target.value })}
                      />
                    </td>
                    <td className="py-2 pr-2" colSpan={3}>
                      <div className="flex gap-2 items-center">
                        <input
                          className="input flex-1"
                          value={editing.tags.join(",")}
                          placeholder="逗号分隔"
                          onChange={(e) =>
                            setEditing({
                              ...editing,
                              tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean),
                            })
                          }
                        />
                        <button className="btn-primary py-1" onClick={handleSave}>
                          保存
                        </button>
                        <button className="btn py-1" onClick={() => setEditing(null)}>
                          取消
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  <tr key={q.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 pr-2 text-gray-700" title={q.id}>
                      <span className="line-clamp-2">{q.text}</span>
                    </td>
                    <td className="py-2 pr-2">
                      <div className="flex gap-1 flex-wrap">
                        {q.tags.map((t) => (
                          <span key={t} className="tag">
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-2 text-gray-500">{q.rubric_count ?? 0}</td>
                    <td className="py-2 pr-2 text-xs text-gray-400">{q.updated_at.slice(0, 16)}</td>
                    <td className="py-2">
                      <div className="flex gap-1">
                        <button className="btn text-xs py-1" onClick={() => setEditing(q)}>
                          编辑
                        </button>
                        <button className="btn-danger text-xs py-1" onClick={() => handleDelete(q)}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              )}
              {queries.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-gray-400">
                    暂无 query，从左侧添加或导入
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
