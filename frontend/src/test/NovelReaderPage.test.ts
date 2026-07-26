import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient, { ApiError } from '@/config/api_client';
import {
    imageVersionFromThumbnailUrl,
    novelImageUrl,
    probePageCount,
    shouldProbePageCount,
} from '@/features/novel_db/reader';

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

describe('novel image cache version', () => {
    it('thumbnail URLの版を本文画像URLへ引き継ぐ', () => {
        const version = imageVersionFromThumbnailUrl(
            '/kindle_novel/images/book/001.png?v=123456789',
        );

        expect(version).toBe('123456789');
        expect(novelImageUrl('book', 9, version)).toBe(
            '/kindle_novel/images/book/009.png?v=123456789',
        );
    });

    it('版がない既存URLも扱える', () => {
        expect(imageVersionFromThumbnailUrl('/kindle_novel/images/book/001.png')).toBeNull();
        expect(novelImageUrl('book', 9)).toBe('/kindle_novel/images/book/009.png');
    });

    it('未OCR書籍のpage_countがnullなら画像列からページ数を検出する', () => {
        expect(shouldProbePageCount(false, { pageCount: null })).toBe(true);
        expect(shouldProbePageCount(false, { pageCount: 92 })).toBe(false);
        expect(shouldProbePageCount(true, undefined)).toBe(false);
    });
});
