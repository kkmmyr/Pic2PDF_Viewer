import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type {
    KindleCatalogBooksResponse,
    KindleCatalogFilters,
    KindleCatalogSourceStatus,
    KindleCatalogStats,
    KindleCaptureJob,
    KindleCaptureJobsResponse,
    KindleLinkCandidatesResponse,
    KindleLinkResponse,
    KindleMigrationCommit,
    KindleMigrationPreview,
    KindleOrdersImport,
    KindleUnlinkedBooksResponse,
} from '@/types/kindleCatalog';

const QUERY_ROOT = ['kindleCatalog'] as const;

function booksEndpoint(filters: KindleCatalogFilters): string {
    const params = new URLSearchParams({
        page: String(filters.page),
        page_size: String(filters.pageSize),
    });
    if (filters.q.trim()) params.set('q', filters.q.trim());
    if (filters.bookType) params.set('book_type', filters.bookType);
    if (filters.ownership) params.set('ownership', filters.ownership);
    if (filters.captureState) params.set('capture_state', filters.captureState);
    return `${API_ENDPOINTS.KINDLE_CATALOG_BOOKS}?${params.toString()}`;
}

export function useKindleCatalog(filters: KindleCatalogFilters) {
    const queryClient = useQueryClient();
    const books = useQuery({
        queryKey: [...QUERY_ROOT, 'books', filters],
        queryFn: () => apiClient.get<unknown, KindleCatalogBooksResponse>(booksEndpoint(filters)),
        placeholderData: (previous) => previous,
    });
    const stats = useQuery({
        queryKey: [...QUERY_ROOT, 'stats'],
        queryFn: () =>
            apiClient.get<unknown, KindleCatalogStats>(API_ENDPOINTS.KINDLE_CATALOG_STATS),
    });
    const sources = useQuery({
        queryKey: [...QUERY_ROOT, 'sources'],
        queryFn: () =>
            apiClient.get<unknown, KindleCatalogSourceStatus>(
                API_ENDPOINTS.KINDLE_CATALOG_IMPORT_SOURCES,
            ),
    });
    const unlinked = useQuery({
        queryKey: [...QUERY_ROOT, 'unlinked'],
        queryFn: () =>
            apiClient.get<unknown, KindleUnlinkedBooksResponse>(
                API_ENDPOINTS.KINDLE_CATALOG_UNLINKED,
            ),
    });
    const captureJobs = useQuery({
        queryKey: [...QUERY_ROOT, 'captureJobs'],
        queryFn: () =>
            apiClient.get<unknown, KindleCaptureJobsResponse>(API_ENDPOINTS.KINDLE_CAPTURE_JOBS),
        refetchInterval: 5000,
    });
    const previewMutation = useMutation({
        mutationFn: () =>
            apiClient.post<unknown, KindleMigrationPreview>(
                API_ENDPOINTS.KINDLE_CATALOG_MIGRATION_PREVIEW,
            ),
    });
    const commitMutation = useMutation({
        mutationFn: (confirmationToken: string) =>
            apiClient.post<unknown, KindleMigrationCommit>(
                API_ENDPOINTS.KINDLE_CATALOG_MIGRATION_COMMIT,
                { confirmation_token: confirmationToken },
            ),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const linkMutation = useMutation({
        mutationFn: (request: { source: 'comic' | 'novel'; bookId: string; asin: string }) =>
            apiClient.put<unknown, KindleLinkResponse>(API_ENDPOINTS.KINDLE_CATALOG_LINKS, {
                source: request.source,
                book_id: request.bookId,
                asin: request.asin,
            }),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const ordersImportMutation = useMutation({
        mutationFn: () =>
            apiClient.post<unknown, KindleOrdersImport>(API_ENDPOINTS.KINDLE_CATALOG_IMPORT_ORDERS),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const kindleInfoImportMutation = useMutation({
        mutationFn: () =>
            apiClient.post<unknown, KindleOrdersImport>(
                API_ENDPOINTS.KINDLE_CATALOG_IMPORT_KINDLE_INFO,
            ),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const autobuyImportMutation = useMutation({
        mutationFn: () =>
            apiClient.post<unknown, KindleOrdersImport>(
                API_ENDPOINTS.KINDLE_CATALOG_IMPORT_AUTOBUY,
            ),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const captureJobMutation = useMutation({
        mutationFn: (request: {
            asin: string;
            source: 'comic' | 'novel';
            direction?: 'left' | 'right';
            expectedScreens?: number;
        }) =>
            apiClient.post<unknown, KindleCaptureJob>(API_ENDPOINTS.KINDLE_CAPTURE_JOBS, {
                asin: request.asin,
                source: request.source,
                direction: request.direction ?? 'left',
                expected_screens: request.expectedScreens ?? null,
            }),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });

    return {
        books: books.data,
        stats: stats.data,
        sources: sources.data,
        unlinked: unlinked.data?.items ?? [],
        captureJobs: captureJobs.data?.items ?? [],
        loading: books.isLoading || stats.isLoading || sources.isLoading || unlinked.isLoading,
        error: books.error ?? stats.error ?? sources.error ?? unlinked.error,
        preview: previewMutation.mutateAsync,
        previewing: previewMutation.isPending,
        commit: commitMutation.mutateAsync,
        committing: commitMutation.isPending,
        link: linkMutation.mutateAsync,
        linking: linkMutation.isPending,
        importOrders: ordersImportMutation.mutateAsync,
        importingOrders: ordersImportMutation.isPending,
        importKindleInfo: kindleInfoImportMutation.mutateAsync,
        importingKindleInfo: kindleInfoImportMutation.isPending,
        importAutobuy: autobuyImportMutation.mutateAsync,
        importingAutobuy: autobuyImportMutation.isPending,
        createCaptureJob: captureJobMutation.mutateAsync,
        creatingCaptureJob: captureJobMutation.isPending,
    };
}

export function useKindleLinkCandidates(source: 'comic' | 'novel' | null, bookId: string | null) {
    return useQuery({
        queryKey: [...QUERY_ROOT, 'linkCandidates', source, bookId],
        queryFn: () => {
            const params = new URLSearchParams({
                source: source ?? '',
                book_id: bookId ?? '',
            });
            return apiClient.get<unknown, KindleLinkCandidatesResponse>(
                `${API_ENDPOINTS.KINDLE_CATALOG_LINK_CANDIDATES}?${params.toString()}`,
            );
        },
        enabled: source !== null && bookId !== null,
    });
}
