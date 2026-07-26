import apiClient, { ApiError } from '@/config/api_client';

export function novelImageUrl(bookName: string, pageNo: number, version?: string | null): string {
    const versionParam = version ? `?v=${encodeURIComponent(version)}` : '';
    return `/kindle_novel/images/${encodeURIComponent(bookName)}/${String(pageNo).padStart(3, '0')}.png${versionParam}`;
}

export function imageVersionFromThumbnailUrl(thumbnailUrl?: string | null): string | null {
    if (!thumbnailUrl) return null;
    const query = thumbnailUrl.split('?', 2)[1];
    return query ? new URLSearchParams(query).get('v') : null;
}

export function shouldProbePageCount(
    isPending: boolean,
    data?: { pageCount: number | null },
): boolean {
    return !isPending && (data === undefined || data.pageCount === null);
}

export async function probePageCount(bookName: string): Promise<number> {
    const imageExists = async (pageNo: number): Promise<boolean> => {
        try {
            await apiClient.head<unknown, unknown>(novelImageUrl(bookName, pageNo));
            return true;
        } catch (error) {
            if (error instanceof ApiError && error.status === 404) return false;
            throw error;
        }
    };

    if (!(await imageExists(1))) return 0;
    let lo = 1;
    let hi = 1500;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (await imageExists(mid)) lo = mid;
        else hi = mid - 1;
    }
    return lo;
}
