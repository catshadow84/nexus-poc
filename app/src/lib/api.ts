import { API_URL } from '@/config';
import { clearToken, getToken } from '@/lib/session';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Options = { method?: string; body?: unknown };

export async function api<T = any>(path: string, options: Options = {}): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (e: any) {
    throw new ApiError(
      0,
      e?.name === 'AbortError'
        ? 'The server did not answer in time. Is the backend running?'
        : 'Cannot reach the server. Is the backend running?',
    );
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    if (res.status === 401) await clearToken();
    let detail = data && typeof data === 'object' && 'detail' in data ? data.detail : text;
    if (typeof detail !== 'string') detail = JSON.stringify(detail);
    throw new ApiError(res.status, String(detail).slice(0, 240) || `HTTP ${res.status}`);
  }
  return data as T;
}