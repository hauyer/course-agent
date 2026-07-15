import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DependencyList,
} from "react";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "操作失败";
}

export function useAsyncData<T>(
  loader: () => Promise<T>,
  dependencies: DependencyList = [],
) {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.resolve()
      .then(() => loaderRef.current())
      .then((value) => {
        if (active) setData(value);
      })
      .catch((reason) => {
        if (active) setError(errorText(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [...dependencies, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { data, error, loading, reload, setData };
}
