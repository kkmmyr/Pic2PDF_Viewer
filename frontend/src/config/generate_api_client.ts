/**
 * Generator 専用 API クライアント。同一オリジンの backend へ送信する。
 */
import axios from 'axios';
import { API_CONFIG as API_TIMEOUT } from '@/constants';
import { createResponseInterceptor } from './api_client';

const GENERATE_BASE_URL: string = '';

const generateApiClient = axios.create({
    baseURL: GENERATE_BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    timeout: API_TIMEOUT.TIMEOUT_MS,
});

createResponseInterceptor(generateApiClient);

export default generateApiClient;
