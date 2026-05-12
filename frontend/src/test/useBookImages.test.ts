import { renderHook, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn() },
}));

import apiClient from '../config/api_client';
import { useBookImages } from '../hooks/useBookImages';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;

describe('useBookImages', () => {
    beforeEach(() => {
        mockedGet.mockReset();
    });

    it('selectedPdf=null では fetch せず imageUrls=null', () => {
        const { result } = renderHook(() => useBookImages(null, '', 'generated'));
        expect(mockedGet).not.toHaveBeenCalled();
        expect(result.current.imageUrls).toBeNull();
        expect(result.current.numPages).toBe(0);
        expect(result.current.isImageMode).toBe(false);
    });


    it('通常パスで images を取得し imageUrls / numPages が設定される', async () => {
        mockedGet.mockResolvedValue({
            images: ['/img/1.webp', '/img/2.webp', '/img/3.webp'],
        });
        const { result } = renderHook(() => useBookImages('book.pdf', '', 'generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        await waitFor(() => expect(result.current.numPages).toBe(3));
        expect(result.current.imageUrls).toEqual(['/img/1.webp', '/img/2.webp', '/img/3.webp']);
        expect(result.current.isImageMode).toBe(true);
    });

    it('currentPath が指定されると bookPath が path/bookName になる', async () => {
        mockedGet.mockResolvedValue({ images: ['/img/1.webp'] });
        renderHook(() => useBookImages('book.pdf', 'sub', 'generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        // BOOK_IMAGES('sub/book', 'generated') が呼ばれる
        const calledUrl = mockedGet.mock.calls[0][0] as string;
        expect(calledUrl).toContain(encodeURIComponent('sub/book'));
        expect(calledUrl).toContain('source=generated');
    });

    it('.pdf 拡張子は bookName から除去される', async () => {
        mockedGet.mockResolvedValue({ images: [] });
        renderHook(() => useBookImages('book.PDF', '', 'generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        const calledUrl = mockedGet.mock.calls[0][0] as string;
        expect(calledUrl).toContain(encodeURIComponent('book'));
        expect(calledUrl).not.toContain('.PDF');
    });

    it('images が空配列なら imageUrls は null のまま（PDF モードへフォールバック）', async () => {
        mockedGet.mockResolvedValue({ images: [] });
        const { result } = renderHook(() => useBookImages('book.pdf', '', 'generated'));

        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.imageUrls).toBeNull();
        expect(result.current.numPages).toBe(0);
    });

    it('GET 失敗時は imageUrls=null のまま（PDF モードへフォールバック）', async () => {
        mockedGet.mockRejectedValue(new Error('not found'));
        const { result } = renderHook(() => useBookImages('book.pdf', '', 'generated'));

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.imageUrls).toBeNull();
        expect(result.current.isImageMode).toBe(false);
    });

    it('selectedPdf 切替で再フェッチされる', async () => {
        mockedGet.mockResolvedValueOnce({ images: ['/a.webp'] });
        const { rerender, result } = renderHook(
            ({ pdf }: { pdf: string }) => useBookImages(pdf, '', 'generated'),
            { initialProps: { pdf: 'a.pdf' } },
        );
        await waitFor(() => expect(result.current.numPages).toBe(1));

        mockedGet.mockResolvedValueOnce({ images: ['/b.webp', '/b2.webp'] });
        rerender({ pdf: 'b.pdf' });
        await waitFor(() => expect(result.current.numPages).toBe(2));
    });

    it('version 変化で再フェッチされ、新しい imageUrls / numPages に置き換わる', async () => {
        mockedGet.mockResolvedValueOnce({ images: ['/a.webp', '/b.webp', '/c.webp'] });
        const { rerender, result } = renderHook(
            ({ v }: { v: number }) => useBookImages('book.pdf', '', 'generated', v),
            { initialProps: { v: 0 } },
        );
        await waitFor(() => expect(result.current.numPages).toBe(3));

        mockedGet.mockResolvedValueOnce({ images: ['/a.webp', '/c.webp'] });
        rerender({ v: 1 });

        await waitFor(() => expect(result.current.numPages).toBe(2));
        expect(result.current.imageUrls).toEqual(['/a.webp', '/c.webp']);
    });

    it('version 変化中は imageUrls=null を経由しない（古い画像を保持しつつ再フェッチ）', async () => {
        // 1st fetch
        mockedGet.mockResolvedValueOnce({ images: ['/a.webp', '/b.webp', '/c.webp'] });
        const { rerender, result } = renderHook(
            ({ v }: { v: number }) => useBookImages('book.pdf', '', 'generated', v),
            { initialProps: { v: 0 } },
        );
        await waitFor(() => expect(result.current.numPages).toBe(3));

        // 2nd fetch を遅延させて「version 変化直後」の状態を観察できるようにする
        let resolveSecond!: (value: unknown) => void;
        mockedGet.mockReturnValueOnce(
            new Promise((resolve) => {
                resolveSecond = resolve;
            }),
        );
        rerender({ v: 1 });

        // version 変化した直後、まだ fetch が解決していない時点で
        // imageUrls は古いまま（null になっていない）であることが重要。
        // null になると isImageMode=false に倒れて <Document> が PDF を取りに行ってしまう。
        expect(result.current.imageUrls).toEqual(['/a.webp', '/b.webp', '/c.webp']);
        expect(result.current.isImageMode).toBe(true);

        // 解決させて新データに切り替わるのを確認
        resolveSecond({ images: ['/a.webp', '/c.webp'] });
        await waitFor(() => expect(result.current.numPages).toBe(2));
    });

    it('selectedPdf 切替時は古い imageUrls をクリアしてから新しいリクエストを投げる', async () => {
        mockedGet.mockResolvedValueOnce({ images: ['/a.webp'] });
        const { rerender, result } = renderHook(
            ({ pdf }: { pdf: string }) => useBookImages(pdf, '', 'generated'),
            { initialProps: { pdf: 'a.pdf' } },
        );
        await waitFor(() => expect(result.current.numPages).toBe(1));

        // 別書籍に切り替えると一旦リセットされる（fetch 完了前は null）
        let resolveSecond!: (value: unknown) => void;
        mockedGet.mockReturnValueOnce(
            new Promise((resolve) => {
                resolveSecond = resolve;
            }),
        );
        rerender({ pdf: 'b.pdf' });

        expect(result.current.imageUrls).toBeNull();
        expect(result.current.numPages).toBe(0);

        resolveSecond({ images: ['/b.webp'] });
        await waitFor(() => expect(result.current.numPages).toBe(1));
    });
});
