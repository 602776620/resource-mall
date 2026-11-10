/**
 * 时间展示工具（07 §1 lib/）。后端一律 UTC ISO-8601（07 §3 红线 6），展示层转本地。
 */

/** ISO-8601 → 本地 "YYYY-MM-DD HH:mm:ss"。无效输入返回 "—"。 */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n: number): string => n.toString().padStart(2, "0");
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
    `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  );
}

/** 剩余毫秒数 → "HH:MM:SS" 倒计时文案。非正数返回 "已结束"。 */
export function formatCountdown(ms: number): string {
  if (ms <= 0) return "已结束";
  const totalSec = Math.floor(ms / 1000);
  const p = (n: number): string => n.toString().padStart(2, "0");
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${p(h)}:${p(m)}:${p(s)}`;
}
