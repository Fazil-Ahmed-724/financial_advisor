const apiUrl = process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function errorMessage(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item
            ? String(item.msg)
            : 'Invalid value',
        )
        .join('\n');
    }
  }
  return 'The request could not be completed.';
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  if (!apiUrl) throw new ApiError('EXPO_PUBLIC_API_URL is not configured.', 0);
  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(body), response.status);
  return body as T;
}

export function newIdempotencyKey(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}
