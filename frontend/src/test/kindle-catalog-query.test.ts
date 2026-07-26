import { describe, expect, it } from 'vitest';

import {
    clearKindleCatalogFilters,
    parseKindleCatalogQuery,
    replaceKindleCatalogParam,
} from '@/features/kindle/catalog-query';

describe('parseKindleCatalogQuery', () => {
    it('restores valid search, filters, paging, and page size', () => {
        const parsed = parseKindleCatalogQuery(
            new URLSearchParams(
                'q=%E4%BD%9C%E5%93%81&book_type=comic&ownership=purchased&capture_state=captured&page=2&page_size=50',
            ),
        );

        expect(parsed).toEqual({
            q: '作品',
            bookType: 'comic',
            ownership: 'purchased',
            captureState: 'captured',
            page: 2,
            pageSize: 50,
        });
    });

    it('normalizes invalid enum and paging values to safe defaults', () => {
        const parsed = parseKindleCatalogQuery(
            new URLSearchParams(
                'book_type=invalid&ownership=invalid&capture_state=invalid&page=-1&page_size=30',
            ),
        );

        expect(parsed).toEqual({
            q: '',
            bookType: '',
            ownership: '',
            captureState: '',
            page: 1,
            pageSize: 25,
        });
    });
});

describe('Kindle catalog query updates', () => {
    it('resets page when a search condition changes without mutating the input', () => {
        const current = new URLSearchParams('page=3&page_size=50');
        const next = replaceKindleCatalogParam(current, 'q', '新刊');

        expect(current.toString()).toBe('page=3&page_size=50');
        expect(next.get('q')).toBe('新刊');
        expect(next.has('page')).toBe(false);
        expect(next.get('page_size')).toBe('50');
    });

    it('clears filters while preserving the selected page size', () => {
        const cleared = clearKindleCatalogFilters(
            new URLSearchParams('q=x&book_type=novel&page=2&page_size=100'),
        );

        expect(cleared.toString()).toBe('page_size=100');
    });
});
