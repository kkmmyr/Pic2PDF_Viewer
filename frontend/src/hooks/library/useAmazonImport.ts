import { useMutation } from '@tanstack/react-query';

import {
    importAmazonMetadata,
    type AmazonImportResponse,
    type AmazonImportSource,
} from '@/features/library/api';

const IMPORT_SOURCES: readonly AmazonImportSource[] = ['novel', 'comic'];

export interface AmazonImportSummary extends AmazonImportResponse {
    errorMessage: string | null;
    hasError: boolean;
}

function errorMessage(reason: unknown): string {
    return reason instanceof Error ? reason.message : '不明なエラー';
}

async function importAllAmazonMetadata(): Promise<AmazonImportSummary> {
    const settled = await Promise.allSettled(
        IMPORT_SOURCES.map((source) => importAmazonMetadata(source)),
    );
    const fulfilled = settled.flatMap((result) =>
        result.status === 'fulfilled' ? [result.value] : [],
    );
    const firstFailure = settled.find(
        (result): result is PromiseRejectedResult => result.status === 'rejected',
    );

    return {
        updated: fulfilled.reduce((total, result) => total + result.updated, 0),
        skipped: fulfilled.reduce((total, result) => total + result.skipped, 0),
        unmatched: fulfilled.reduce((total, result) => total + result.unmatched, 0),
        hasError: firstFailure !== undefined,
        errorMessage: firstFailure ? errorMessage(firstFailure.reason) : null,
    };
}

export function useAmazonImport() {
    const mutation = useMutation({ mutationFn: importAllAmazonMetadata });

    return {
        importAmazon: mutation.mutateAsync,
        isImporting: mutation.isPending,
    };
}
