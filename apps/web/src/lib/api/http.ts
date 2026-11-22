import axios, { type AxiosRequestConfig } from "axios";

// Axios instance duy nhất cho FE Miro. Luôn gọi tương đối /api/... để
// Next rewrite quyết định đích: fixture nội bộ (không env) hoặc proxy sang
// BE thật (khi có NEXT_PUBLIC_API_BASE). Không gắn baseURL tuyệt đối ở đây
// để request đi qua rewrite (giữ strip prefix /api → BE).
export const http = axios.create({
  baseURL: "",
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
