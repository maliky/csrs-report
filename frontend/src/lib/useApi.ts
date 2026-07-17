import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "./api/client";

export function useApi<T>(path: string, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await apiFetch<T>(path));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Erreur inconnue"));
    } finally {
      setLoading(false);
    }
  }, [enabled, path]);

  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}
