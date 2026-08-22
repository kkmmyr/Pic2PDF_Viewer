import { useMutation } from '@tanstack/react-query';

import { fetchMetaExport } from '@/features/library/api';
import type { LibrarySource } from '@/types';

function exportFilename(source: LibrarySource, now: Date): string {
    const date =
        now.getFullYear().toString() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0');
    return `meta_${source}_${date}.json`;
}

function downloadMetaExport(blob: Blob, source: LibrarySource): void {
    const objectUrl = URL.createObjectURL(blob);
    try {
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = exportFilename(source, new Date());
        anchor.click();
    } finally {
        URL.revokeObjectURL(objectUrl);
    }
}

export function useMetaExport(source: LibrarySource) {
    const mutation = useMutation({
        mutationFn: async () => {
            const blob = await fetchMetaExport(source);
            downloadMetaExport(blob, source);
        },
    });

    return {
        exportMeta: mutation.mutate,
        isExporting: mutation.isPending,
    };
}
