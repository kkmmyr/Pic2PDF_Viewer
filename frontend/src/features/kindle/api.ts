import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type {
    KindleCaptureJob,
    KindleCaptureJobCreateRequest,
    KindleCaptureJobsResponse,
    KindleCatalogBooksResponse,
    KindleCatalogFilters,
    KindleCatalogSourceStatus,
    KindleCatalogStats,
    KindleImportRunsResponse,
    KindleLinkCandidatesResponse,
    KindleLinkRequest,
    KindleLinkResponse,
    KindleMigrationCommit,
    KindleMigrationCommitRequest,
    KindleMigrationPreview,
    KindleOrdersImport,
    KindleUnlinkedBooksResponse,
} from '@/features/kindle/types';

export function fetchKindleBooks(
    filters: KindleCatalogFilters,
): Promise<KindleCatalogBooksResponse> {
    const params = new URLSearchParams({
        page: String(filters.page),
        page_size: String(filters.pageSize),
    });
    if (filters.q.trim()) params.set('q', filters.q.trim());
    if (filters.bookType) params.set('book_type', filters.bookType);
    if (filters.ownership) params.set('ownership', filters.ownership);
    if (filters.captureState) params.set('capture_state', filters.captureState);
    return apiClient.get(`${API_ENDPOINTS.KINDLE_CATALOG_BOOKS}?${params.toString()}`);
}

export function fetchUnlinkedBooks(): Promise<KindleUnlinkedBooksResponse> {
    return apiClient.get(API_ENDPOINTS.KINDLE_CATALOG_UNLINKED);
}

export function linkKindleBook(request: KindleLinkRequest): Promise<KindleLinkResponse> {
    return apiClient.put(API_ENDPOINTS.KINDLE_CATALOG_LINKS, request);
}

export function fetchCaptureJobs(): Promise<KindleCaptureJobsResponse> {
    return apiClient.get(API_ENDPOINTS.KINDLE_CAPTURE_JOBS);
}

export function createCaptureJob(
    request: KindleCaptureJobCreateRequest,
): Promise<KindleCaptureJob> {
    return apiClient.post(API_ENDPOINTS.KINDLE_CAPTURE_JOBS, request);
}

export function fetchCatalogStats(): Promise<KindleCatalogStats> {
    return apiClient.get(API_ENDPOINTS.KINDLE_CATALOG_STATS);
}

export function fetchImportSources(): Promise<KindleCatalogSourceStatus> {
    return apiClient.get(API_ENDPOINTS.KINDLE_CATALOG_IMPORT_SOURCES);
}

export function fetchImportRuns(): Promise<KindleImportRunsResponse> {
    return apiClient.get(`${API_ENDPOINTS.KINDLE_CATALOG_IMPORT_RUNS}?limit=10`);
}

export function previewMigration(): Promise<KindleMigrationPreview> {
    return apiClient.post(API_ENDPOINTS.KINDLE_CATALOG_MIGRATION_PREVIEW);
}

export function commitMigration(
    request: KindleMigrationCommitRequest,
): Promise<KindleMigrationCommit> {
    return apiClient.post(API_ENDPOINTS.KINDLE_CATALOG_MIGRATION_COMMIT, request);
}

export function importOrders(): Promise<KindleOrdersImport> {
    return apiClient.post(API_ENDPOINTS.KINDLE_CATALOG_IMPORT_ORDERS);
}

export function importKindleInfo(): Promise<KindleOrdersImport> {
    return apiClient.post(API_ENDPOINTS.KINDLE_CATALOG_IMPORT_KINDLE_INFO);
}

export function importAutobuy(): Promise<KindleOrdersImport> {
    return apiClient.post(API_ENDPOINTS.KINDLE_CATALOG_IMPORT_AUTOBUY);
}

export function fetchLinkCandidates(
    source: 'comic' | 'novel',
    bookId: string,
): Promise<KindleLinkCandidatesResponse> {
    const params = new URLSearchParams({ source, book_id: bookId });
    return apiClient.get(`${API_ENDPOINTS.KINDLE_CATALOG_LINK_CANDIDATES}?${params.toString()}`);
}
