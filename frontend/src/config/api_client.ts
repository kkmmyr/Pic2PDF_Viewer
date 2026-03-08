import axios from 'axios';
import { API_CONFIG } from './api';

const apiClient = axios.create({
    baseURL: API_CONFIG.BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

apiClient.interceptors.response.use(
    (response) => response.data,
    (error) => {
        const message = error.response?.data?.detail || error.message || 'An unexpected error occurred';
        console.error('API Error:', message);
        return Promise.reject(new Error(message));
    }
);

export default apiClient;
