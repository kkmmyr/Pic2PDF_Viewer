import { fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import BookCard from '@/components/novel_db/BookCard';
import type { BookSummary } from '@/features/novel_db/types';

const BASE_BOOK: BookSummary = {
    name: '茉莉花官吏伝 一',
    authors: ['石田リンネ'],
    series_id: 'matsurika',
    series_title: '茉莉花官吏伝',
    is_indexed: false,
    page_count: null,
    indexed_at: null,
    thumbnail_url: null,
    ocr_done_at: null,
    volume: 1,
    publisher: null,
    asin: null,
    series_index: 1,
    read_state: 'unread',
};

describe('BookCard', () => {
    it('一覧向け短縮要約だけを短い要約として表示する', () => {
        const onOpenDetail = vi.fn();
        const catalogSummary = '茉莉花が官吏を目指して難題に挑み、周囲との関係を築く。';

        const { getByRole, getByText } = render(
            <BookCard
                book={{ ...BASE_BOOK, catalog_summary: catalogSummary }}
                onOpenDetail={onOpenDetail}
                onEdit={vi.fn()}
            />,
        );

        expect(getByText('短い要約')).toBeInTheDocument();
        expect(getByText(catalogSummary)).toBeInTheDocument();

        fireEvent.click(getByRole('button', { name: '茉莉花官吏伝 一 の詳細を開く' }));
        expect(onOpenDetail).toHaveBeenCalledWith('茉莉花官吏伝 一');
    });

    it('短縮要約が未生成なら要約欄を表示しない', () => {
        const { queryByText } = render(
            <BookCard book={BASE_BOOK} onOpenDetail={vi.fn()} onEdit={vi.fn()} />,
        );

        expect(queryByText('短い要約')).not.toBeInTheDocument();
    });

    it('読書状態を日本語で表示する', () => {
        const { getByLabelText, rerender } = render(
            <BookCard book={BASE_BOOK} onOpenDetail={vi.fn()} onEdit={vi.fn()} />,
        );
        expect(getByLabelText('未読')).toBeInTheDocument();

        rerender(
            <BookCard
                book={{ ...BASE_BOOK, read_state: 'reading' }}
                onOpenDetail={vi.fn()}
                onEdit={vi.fn()}
            />,
        );
        expect(getByLabelText('読書中')).toBeInTheDocument();
    });

    it('編集ボタンは書籍名を含む名前を持ち、クリックで対象書籍を渡す', () => {
        const onEdit = vi.fn();
        const { getByRole } = render(
            <BookCard book={BASE_BOOK} onOpenDetail={vi.fn()} onEdit={onEdit} />,
        );

        fireEvent.click(getByRole('button', { name: '茉莉花官吏伝 一 のメタデータを編集' }));
        expect(onEdit).toHaveBeenCalledWith(BASE_BOOK);
    });
});
