import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type { LibrarySource } from '@/types';
import type { components } from '@/types/api';

export type AmazonImportResponse = components['schemas']['AmazonImportResponse'];
export type AmazonImportSource = 'novel' | 'comic';

export function importAmazonMetadata(source: AmazonImportSource): Promise<AmazonImportResponse> {
    return apiClient.post<unknown, AmazonImportResponse>(API_ENDPOINTS.AMAZON_IMPORT(source));
}

export function fetchMetaExport(source: LibrarySource): Promise<Blob> {
    return apiClient.get<unknown, Blob>(API_ENDPOINTS.META_EXPORT(source), {
        responseType: 'blob',
    });
}
