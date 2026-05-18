/**
 * Generator 専用 API クライアント。
 *
 * VITE_GENERATE_API_URL が設定されている場合（Linux 環境から Windows バックエンドを
 * 呼び出す場合など）はそちらを使用し、未設定時は通常の同一オリジン API に fallback する。
 */
import axios, { AxiosError } from 'axios';
import { API_CONFIG as API_TIMEOUT } from '../constants';
import { ApiError } from './api_client';

const GENERATE_BASE_URL: string = import.meta.env.VITE_GENERATE_API_URL ?? '';

const generateApiClient = axios.create({
    baseURL: GENERATE_BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    timeout: API_TIMEOUT.TIMEOUT_MS,
});

generateApiClient.interceptors.response.use(
    (response) => response.data,
    (error: AxiosError) => {
        if (!error.response) {
            const isTimeout = error.code === 'ECONNABORTED';
            const kind = isTimeout ? 'timeout' : 'network';
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
        const kind = status >= 500 ? 'server' : 'client';
        console.error(`Generate API Error [${status}]:`, detail);
        return Promise.reject(new ApiError(detail, status, kind));
    },
);

export default generateApiClient;
