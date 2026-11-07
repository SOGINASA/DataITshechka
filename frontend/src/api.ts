import { API_BASE_URL } from "./config.js";

export class ApiError extends Error {
  constructor(message: string, public status = 0, public code = "network_error") {
    super(message);
    this.name = "ApiError";
  }
}

export function createApiClient(base = API_BASE_URL, transport: typeof fetch = (...args) => fetch(...args)) {
  const pending = new Map<string, Promise<unknown>>();
  function request<T>(path: string, body?: unknown, timeout = 45000): Promise<T> {
    if (body !== undefined) return send<T>(path, body, timeout).finally(() => pending.clear());
    const key = `${timeout}:${path}`;
    const existing = pending.get(key);
    if (existing) return existing as Promise<T>;
    const promise = send<T>(path, body, timeout).finally(() => {
      if (pending.get(key) === promise) pending.delete(key);
    });
    pending.set(key, promise);
    return promise;
  }
  async function send<T>(path: string, body?: unknown, timeout = 45000): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await transport(`${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`, {
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.headers.get("content-type")?.includes("application/json"))
        throw new ApiError("Сервер вернул неожиданный ответ. Попробуйте обновить данные.", response.status, "invalid_response");
      const data = await response.json();
      if (!response.ok)
        throw new ApiError(data.error?.message || `Ошибка сервера (${response.status}).`, response.status, data.error?.code);
      return data as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      const message = controller.signal.aborted ? "Сервер не ответил вовремя." : "Не удалось связаться с сервером. Проверьте подключение.";
      throw new ApiError(message + (body === undefined ? "" : " Результат операции неизвестен; обновите данные перед повторной отправкой."));
    } finally { clearTimeout(timer); }
  }
  async function list<T>(path: string): Promise<T[]> {
    const items: T[] = [];
    for (let page = 1; ; page++) {
      const data = await request<{items: T[]; pagination: {pages: number}}>(`${path}${path.includes("?") ? "&" : "?"}per_page=100&page=${page}`);
      if (!Array.isArray(data.items) || !Number.isInteger(data.pagination?.pages))
        throw new ApiError("Некорректный список в ответе сервера.", 200, "invalid_response");
      items.push(...data.items);
      if (page >= data.pagination.pages) return items;
    }
  }
  return { request, list };
}
export const api = createApiClient();
export const apiId = encodeURIComponent;
