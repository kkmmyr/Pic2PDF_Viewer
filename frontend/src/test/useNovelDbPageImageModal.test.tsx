/**
 * useNovelDbPageImageModal: 開閉 + 前後送り + キーボード操作。
 */
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { useNovelDbPageImageModal } from '../hooks/novel_db/useNovelDbPageImageModal';
import type { BookSummary } from '../features/novel_db/types';

const BOOKS: BookSummary[] = [
    {
        name: 'book-1',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: true,
        page_count: 100,
        indexed_at: null,
        ocr_done_at: null,
        thumbnail_url: null,
    },
    {
        name: 'book-2',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: true,
        page_count: 50,
        indexed_at: null,
        ocr_done_at: null,
        thumbnail_url: null,
    },
];

describe('useNovelDbPageImageModal', () => {
    it('初期状態は閉じている', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        expect(result.current.state).toBeNull();
    });

    it('open で書籍とページが設定される', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        act(() => result.current.open('book-1', 5));
        expect(result.current.state).toEqual({ book: 'book-1', pageNo: 5 });
        expect(result.current.maxPage).toBe(100);
    });

    it('nextPage は最大値で頭打ち', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        act(() => result.current.open('book-2', 50));
        act(() => result.current.nextPage());
        expect(result.current.state?.pageNo).toBe(50);
    });

    it('prevPage は 1 で頭打ち', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        act(() => result.current.open('book-1', 1));
        act(() => result.current.prevPage());
        expect(result.current.state?.pageNo).toBe(1);
    });

    it('nextPage / prevPage で前後送り', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        act(() => result.current.open('book-1', 10));
        act(() => result.current.nextPage());
        expect(result.current.state?.pageNo).toBe(11);
        act(() => result.current.prevPage());
        expect(result.current.state?.pageNo).toBe(10);
    });

    it('close で state が null に戻る', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        act(() => result.current.open('book-1', 5));
        act(() => result.current.close());
        expect(result.current.state).toBeNull();
    });

    it('左右キーで前後送り、ESC で閉じる', () => {
        const { result } = renderHook(() => useNovelDbPageImageModal(BOOKS));
        act(() => result.current.open('book-1', 5));

        act(() => {
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
        });
        expect(result.current.state?.pageNo).toBe(6);

        act(() => {
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
        });
        expect(result.current.state?.pageNo).toBe(5);

        act(() => {
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        });
        expect(result.current.state).toBeNull();
    });
});
