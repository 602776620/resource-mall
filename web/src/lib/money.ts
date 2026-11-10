/**
 * 金额工具（07 §4 红线 2：金额分↔元只走本文件，页面禁止散落换算）。
 * 后端金额一律以「分」存储（int，03 铁律 4），前端展示为「元」。
 * 全程整数运算，避免 float 误差。
 */

/** 分 → 元字符串（不带货币符号）。12345 → "123.45"，负数保留符号。 */
export function fenToYuan(fen: number): string {
  const neg = fen < 0;
  const abs = Math.abs(Math.trunc(fen));
  const yuan = Math.floor(abs / 100);
  const cent = abs % 100;
  const body = `${yuan}.${cent.toString().padStart(2, "0")}`;
  return neg ? `-${body}` : body;
}

/** 带货币符号的金额展示。formatFen(12345) → "¥123.45"。 */
export function formatFen(fen: number, symbol = "¥"): string {
  return `${symbol}${fenToYuan(fen)}`;
}

/**
 * 元（用户输入字符串/数字，允许 1~2 位小数）→ 分（int）。
 * 非法输入抛 RangeError。
 */
export function yuanToFen(input: string | number): number {
  const s = String(input).trim().replace(/^¥\s*/, "");
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(s)) {
    throw new RangeError(`invalid amount: ${input}`);
  }
  const [whole, frac = ""] = s.split(".");
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  if (!Number.isSafeInteger(cents)) throw new RangeError(`amount too large: ${input}`);
  return cents;
}
