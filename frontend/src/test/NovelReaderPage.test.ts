import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient, { ApiError } from '@/config/api_client';
import { probePageCount } from '@/pages/NovelReaderPage';

describe('probePageCount', () => {
    afterEach(() => vi.restoreAllMocks());

    it('HEADの二分探索で最終ページを求める', async () => {
        const head = vi.spyOn(apiClient, 'head').mockImplementation(async (url) => {
            const match = String(url).match(/\/(\d+)\.png$/);
            const page = Number(match?.[1] ?? 0);
            if (page <= 37) return undefined;
            throw new ApiError('not found', 404, 'client');
        });

        await expect(probePageCount('book')).resolves.toBe(37);
        expect(head.mock.calls.length).toBeLessThanOrEqual(12);
    });
});
