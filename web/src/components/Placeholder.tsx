/** 路由占位页（T02 骨架用；各任务实现真实交互后替换内部）。 */
export function Placeholder({ title, note }: { title: string; note?: string }) {
  return (
    <section className="page-placeholder">
      <h1>{title}</h1>
      <p className="muted">{note ?? "页面建设中（T02 骨架占位）。"}</p>
    </section>
  );
}
