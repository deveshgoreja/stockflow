import { useCallback, useEffect, useState } from "react";

/** Load data with `loader`, re-running whenever `deps` change or `reload()` is called. */
export function useApi(loader, deps, onError) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loader()
      .then((result) => !cancelled && setData(result))
      .catch((error) => !cancelled && onError?.(error))
      .finally(() => !cancelled && setLoading(false));
    // Ignore responses that arrive after the inputs changed, so stale data never wins.
    return () => {
      cancelled = true;
    };
  }, [...deps, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, loading, reload };
}
