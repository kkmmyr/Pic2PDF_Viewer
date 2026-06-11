import axios, { type AxiosInstance, AxiosError } from 'axios';
import { API_CONFIG as API_URL_CONFIG } from './api';
import { API_CONFIG } from '@/constants';

/** API エラーの種別 */
type ApiErrorKind = 'network' | 'timeout' | 'server' | 'client' | 'unknown';

/**
 * API 呼び出し失敗時にスローされる型付きエラー。
 * catch した側で `error instanceof ApiError` で判定できる。
 */
export class ApiError extends Error {
    constructor(
        message: string,
        public readonly status: number | undefined,
        public readonly kind: ApiErrorKind,
    ) {
        super(message);
        this.name = 'ApiError';
    }
}

/**
 * 共通レスポンス interceptor を指定の AxiosInstance に適用する。
 * generate_api_client など複数クライアントで同じハンドリングを再利用する。
 */
export function createResponseInterceptor(client: AxiosInstance): void {
    client.interceptors.response.use(
        (response) => response.data,
        (error: AxiosError) => {
            if (!error.response) {
                const isTimeout = error.code === 'ECONNABORTED';
                const kind: ApiErrorKind = isTimeout ? 'timeout' : 'network';
                const message = isTimeout
                    ? 'リクエストがタイムアウトしました。再試行してください。'
                    : 'ネットワークエラーが発生しました。接続を確認してください。';
                return Promise.reject(new ApiError(message, undefined, kind));
            }

            const status = error.response.status;
            const detail =
                (error.response.data as { detail?: string } | undefined)?.detail ??
                error.message ??
                '予期しないエラーが発生しました。';
            const kind: ApiErrorKind = status >= 500 ? 'server' : 'client';

            console.error(`API Error [${status}]:`, detail);
            return Promise.reject(new ApiError(detail, status, kind));
        },
    );
}

const apiClient = axios.create({
    baseURL: API_URL_CONFIG.BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    timeout: API_CONFIG.TIMEOUT_MS,
});

createResponseInterceptor(apiClient);

export default apiClient;
