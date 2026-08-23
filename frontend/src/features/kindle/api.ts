import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type {
    KindleCaptureJob,
    KindleCaptureJobCreateRequest,
    KindleCaptureJobsResponse,
    KindleCaptureQualityWarning,
    KindleCaptureQualityWarningReadRequest,
    KindleCaptureQualityWarningsResponse,
    KindleCaptureWarningStatus,
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
    KindlePriceHistoryResponse,
    KindlePriceObservationResponse,
    KindlePriceWatch,
    KindlePriceWatchCreateRequest,
    KindlePriceWatchListResponse,
    KindlePriceWatchUpdateRequest,
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

export function fetchCaptureQualityWarnings(
    status: KindleCaptureWarningStatus,
): Promise<KindleCaptureQualityWarningsResponse> {
    return apiClient.get(API_ENDPOINTS.KINDLE_CAPTURE_QUALITY_WARNINGS(status));
}

export function updateCaptureQualityWarning(
    warningId: number,
    request: KindleCaptureQualityWarningReadRequest,
): Promise<KindleCaptureQualityWarning> {
    return apiClient.patch(API_ENDPOINTS.KINDLE_CAPTURE_QUALITY_WARNING(warningId), request);
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

export function fetchKindlePriceWatches(): Promise<KindlePriceWatchListResponse> {
    return apiClient.get(API_ENDPOINTS.KINDLE_PRICE_WATCHES);
}

export function fetchKindlePriceHistory(watchId: number): Promise<KindlePriceHistoryResponse> {
    return apiClient.get(API_ENDPOINTS.KINDLE_PRICE_WATCH_HISTORY(watchId));
}

export function createKindlePriceWatch(
    request: KindlePriceWatchCreateRequest,
): Promise<KindlePriceWatch> {
    return apiClient.post(API_ENDPOINTS.KINDLE_PRICE_WATCHES, request);
}

export function updateKindlePriceWatch(
    watchId: number,
    request: KindlePriceWatchUpdateRequest,
): Promise<KindlePriceWatch> {
    return apiClient.patch(API_ENDPOINTS.KINDLE_PRICE_WATCH(watchId), request);
}

export function deleteKindlePriceWatch(watchId: number): Promise<{ id: number; deleted: boolean }> {
    return apiClient.delete(API_ENDPOINTS.KINDLE_PRICE_WATCH(watchId));
}

export function recordKindlePriceObservation(
    watchId: number,
    request: {
        current_price?: number | null;
        list_price?: number | null;
        status?: 'ok' | 'partial' | 'failed';
        error_message?: string | null;
        source?: 'codex_browser' | 'manual';
        title?: string | null;
    },
): Promise<KindlePriceObservationResponse> {
    return apiClient.post(API_ENDPOINTS.KINDLE_PRICE_WATCH_OBSERVATIONS(watchId), request);
}
