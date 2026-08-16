import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    commitMigration,
    createCaptureJob,
    fetchCaptureJobs,
    fetchCatalogStats,
    fetchImportRuns,
    fetchImportSources,
    fetchKindleBooks,
    fetchLinkCandidates,
    fetchUnlinkedBooks,
    importAutobuy,
    importKindleInfo,
    importOrders,
    linkKindleBook,
    previewMigration,
} from '@/features/kindle/api';
import type { KindleCatalogFilters } from '@/features/kindle/types';

const QUERY_ROOT = ['kindleCatalog'] as const;

export function useKindleBooks(filters: KindleCatalogFilters) {
    return useQuery({
        queryKey: [...QUERY_ROOT, 'books', filters],
        queryFn: () => fetchKindleBooks(filters),
        placeholderData: (previous) => previous,
    });
}

export function useKindleLinking() {
    const queryClient = useQueryClient();
    const unlinked = useQuery({
        queryKey: [...QUERY_ROOT, 'unlinked'],
        queryFn: fetchUnlinkedBooks,
    });
    const linkMutation = useMutation({
        mutationFn: (request: { source: 'comic' | 'novel'; bookId: string; asin: string }) =>
            linkKindleBook({
                source: request.source,
                book_id: request.bookId,
                asin: request.asin,
            }),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });

    return {
        unlinked: unlinked.data?.items ?? [],
        isLoading: unlinked.isLoading,
        error: unlinked.error,
        link: linkMutation.mutateAsync,
        linking: linkMutation.isPending,
    };
}

export function useKindleCaptureJobs(options: { enabled?: boolean } = {}) {
    const queryClient = useQueryClient();
    const captureJobs = useQuery({
        queryKey: [...QUERY_ROOT, 'captureJobs'],
        queryFn: fetchCaptureJobs,
        enabled: options.enabled ?? true,
        refetchInterval: 5000,
    });
    const captureJobMutation = useMutation({
        mutationFn: (request: {
            asin: string;
            source: 'comic' | 'novel';
            direction?: 'left' | 'right';
            expectedScreens?: number;
        }) =>
            createCaptureJob({
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
        jobs: captureJobs.data?.items ?? [],
        isLoading: captureJobs.isLoading,
        error: captureJobs.error,
        createCaptureJob: captureJobMutation.mutateAsync,
        creatingCaptureJob: captureJobMutation.isPending,
    };
}

export function useKindleImports() {
    const queryClient = useQueryClient();
    const stats = useQuery({
        queryKey: [...QUERY_ROOT, 'stats'],
        queryFn: fetchCatalogStats,
    });
    const sources = useQuery({
        queryKey: [...QUERY_ROOT, 'sources'],
        queryFn: fetchImportSources,
    });
    const runs = useQuery({
        queryKey: [...QUERY_ROOT, 'importRuns'],
        queryFn: fetchImportRuns,
    });
    const previewMutation = useMutation({
        mutationFn: previewMigration,
    });
    const commitMutation = useMutation({
        mutationFn: (confirmationToken: string) =>
            commitMigration({ confirmation_token: confirmationToken }),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const ordersImportMutation = useMutation({
        mutationFn: importOrders,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const kindleInfoImportMutation = useMutation({
        mutationFn: importKindleInfo,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    const autobuyImportMutation = useMutation({
        mutationFn: importAutobuy,
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: QUERY_ROOT });
        },
    });
    return {
        stats: stats.data,
        sources: sources.data,
        runs: runs.data?.items ?? [],
        loading: stats.isLoading || sources.isLoading || runs.isLoading,
        error: stats.error ?? sources.error ?? runs.error,
        preview: previewMutation.mutateAsync,
        previewing: previewMutation.isPending,
        commit: commitMutation.mutateAsync,
        committing: commitMutation.isPending,
        importOrders: ordersImportMutation.mutateAsync,
        importingOrders: ordersImportMutation.isPending,
        importKindleInfo: kindleInfoImportMutation.mutateAsync,
        importingKindleInfo: kindleInfoImportMutation.isPending,
        importAutobuy: autobuyImportMutation.mutateAsync,
        importingAutobuy: autobuyImportMutation.isPending,
    };
}

export function useKindleLinkCandidates(source: 'comic' | 'novel' | null, bookId: string | null) {
    return useQuery({
        queryKey: [...QUERY_ROOT, 'linkCandidates', source, bookId],
        queryFn: () => {
            return fetchLinkCandidates(source ?? 'comic', bookId ?? '');
        },
        enabled: source !== null && bookId !== null,
    });
}
