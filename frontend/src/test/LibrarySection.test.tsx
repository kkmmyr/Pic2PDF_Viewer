import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import LibrarySection from '@/components/novel_db/LibrarySection';
import type { BookSummary } from '@/features/novel_db/types';

const fetchNovelAuthors = vi.fn();
const fetchSeries = vi.fn();
const patchNovelBookMeta = vi.fn();

vi.mock('@/features/novel_db/api', () => ({
    fetchNovelAuthors: () => fetchNovelAuthors(),
    fetchSeries: () => fetchSeries(),
    patchNovelBookMeta: (...args: unknown[]) => patchNovelBookMeta(...args),
}));

const books: BookSummary[] = [
    {
        name: '書籍A',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: false,
        page_count: null,
        indexed_at: null,
        thumbnail_url: null,
        ocr_done_at: null,
        volume: null,
        publisher: null,
        asin: null,
        series_index: null,
        read_state: 'unread',
    },
    {
        name: '書籍B',
        authors: [],
        series_id: null,
        series_title: null,
        is_indexed: false,
        page_count: null,
        indexed_at: null,
        thumbnail_url: null,
        ocr_done_at: null,
        volume: null,
        publisher: null,
        asin: null,
        series_index: null,
        read_state: 'unread',
    },
];

function renderLibrary(onMetaRefetch = vi.fn()) {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    function Wrapper({ children }: { children: ReactNode }) {
        return (
            <QueryClientProvider client={queryClient}>
                <MemoryRouter initialEntries={['/novel/db']}>{children}</MemoryRouter>
            </QueryClientProvider>
        );
    }

    render(
        <LibrarySection
            books={books}
            isLoading={false}
            onOpenDetailBook={() => {}}
            onEditBook={() => {}}
            onMetaRefetch={onMetaRefetch}
        />,
        { wrapper: Wrapper },
    );
    return onMetaRefetch;
}

async function openAuthorDialogForAllBooks() {
    fireEvent.click(screen.getByRole('button', { name: '選択' }));
    fireEvent.click(screen.getByRole('button', { name: '全選択' }));
    fireEvent.click(screen.getByRole('button', { name: '作者を設定' }));
    await screen.findByRole('dialog', { name: '作者名を一括設定' });
}

async function selectExistingAuthor() {
    fireEvent.focus(screen.getByRole('textbox'));
    fireEvent.mouseDown(await screen.findByText('既存作者'));
}

describe('LibrarySection の小説一括操作', () => {
    beforeEach(() => {
        Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
            configurable: true,
            value: vi.fn(),
        });
        fetchNovelAuthors.mockReset();
        fetchSeries.mockReset();
        patchNovelBookMeta.mockReset();
        fetchNovelAuthors.mockResolvedValue(['既存作者']);
        fetchSeries.mockResolvedValue([]);
        patchNovelBookMeta.mockResolvedValue(undefined);
    });

    it('作者を明示選択すると書籍順に更新し、全件成功後だけ再取得して選択を解除する', async () => {
        const onMetaRefetch = renderLibrary();

        await openAuthorDialogForAllBooks();
        await selectExistingAuthor();
        fireEvent.click(screen.getByRole('button', { name: '一括適用' }));

        await waitFor(() => expect(patchNovelBookMeta).toHaveBeenCalledTimes(2));
        expect(patchNovelBookMeta.mock.calls).toEqual([
            ['書籍A.pdf', { authors: ['既存作者'] }],
            ['書籍B.pdf', { authors: ['既存作者'] }],
        ]);
        expect(onMetaRefetch).toHaveBeenCalledOnce();
        expect(screen.getByRole('button', { name: '選択' })).toBeInTheDocument();
        expect(screen.queryByRole('dialog', { name: '作者名を一括設定' })).not.toBeInTheDocument();
    });

    it('途中の更新が失敗すると以降を更新せず、再取得も選択解除もしない', async () => {
        patchNovelBookMeta.mockRejectedValueOnce(new Error('更新失敗'));
        const onMetaRefetch = renderLibrary();

        await openAuthorDialogForAllBooks();
        await selectExistingAuthor();
        fireEvent.click(screen.getByRole('button', { name: '一括適用' }));

        await waitFor(() => expect(patchNovelBookMeta).toHaveBeenCalledOnce());
        expect(patchNovelBookMeta).toHaveBeenCalledWith('書籍A.pdf', { authors: ['既存作者'] });
        expect(onMetaRefetch).not.toHaveBeenCalled();
        expect(screen.getByText('2 冊選択中')).toBeInTheDocument();
        expect(screen.getByRole('dialog', { name: '作者名を一括設定' })).toBeInTheDocument();
    });
});
