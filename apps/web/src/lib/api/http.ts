import axios, { type AxiosRequestConfig } from "axios";

// Axios instance duy nhất cho FE Miro. Mặc định gọi fixture/mock nội bộ
// (/api/...) theo contract BE; sau nối runtime thật qua env NEXT_PUBLIC_API_BASE.
export const http = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE ?? "",
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

type Envelope<T> = { success: boolean; result: T };

export async function request<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.request({ url: path, ...config });
  const data = res.data as Envelope<T> | T;
  if (typeof data === "object" && data !== null && "success" in data && "result" in data) {
    return (data as Envelope<T>).result;
  }
  return data as T;
}

export const api = {
  get<T>(path: string, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "GET" });
  },
  post<T>(path: string, body?: unknown, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "POST", data: body });
  },
  put<T>(path: string, body?: unknown, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "PUT", data: body });
  },
  delete<T>(path: string, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "DELETE" });
  },
};
