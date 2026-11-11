/**
 * 列表/详情数据拉取 hook（02 §3 状态约定）：loading / data / error / reload。
 * deps 变化自动重拉；避免快速变更时的竞态（只认最后一次请求的结果）。
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const runId = useRef(0);

  useEffect(() => {
    const id = ++runId.current;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => {
        if (id !== runId.current) return; // 过期请求丢弃
        setData(d);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (id !== runId.current) return;
        setError(e instanceof Error ? e.message : "请求失败");
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, reload };
}
