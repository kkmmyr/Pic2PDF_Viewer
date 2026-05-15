import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { BulkActionsPanel } from '../components/novel_db/BulkActionsPanel';
import type { BookSummary } from '../features/novel_db/types';

const makeBook = (name: string): BookSummary => ({
    name,
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
});

const books = [makeBook('book-a'), makeBook('book-b'), makeBook('book-c')];

const defaultProps = {
    targetBooks: books,
    selectedNames: new Set<string>(),
    onToggleSelectAll: vi.fn(),
    onOpenAuthorDialog: vi.fn(),
    onOpenSeriesDialog: vi.fn(),
};

describe('BulkActionsPanel', () => {
    it('選択数を表示する', () => {
        const { getByText } = render(
            <BulkActionsPanel
                {...defaultProps}
                selectedNames={new Set(['book-a', 'book-b'])}
            />,
        );
        expect(getByText('2 冊選択中')).toBeInTheDocument();
    });

    it('全書籍未選択のとき「全選択」が表示される', () => {
        const { getByText } = render(
            <BulkActionsPanel {...defaultProps} selectedNames={new Set()} />,
        );
        expect(getByText('全選択')).toBeInTheDocument();
    });

    it('全書籍選択済みのとき「全解除」が表示される', () => {
        const { getByText } = render(
            <BulkActionsPanel
                {...defaultProps}
                selectedNames={new Set(['book-a', 'book-b', 'book-c'])}
            />,
        );
        expect(getByText('全解除')).toBeInTheDocument();
    });

    it('全選択ボタンをクリックすると onToggleSelectAll が targetBooks で呼ばれる', () => {
        const onToggleSelectAll = vi.fn();
        const { getByText } = render(
            <BulkActionsPanel {...defaultProps} onToggleSelectAll={onToggleSelectAll} />,
        );
        fireEvent.click(getByText('全選択'));
        expect(onToggleSelectAll).toHaveBeenCalledWith(books);
    });

    it('選択なしのとき「作者を設定」「シリーズに登録」が disabled', () => {
        const { getByText } = render(
            <BulkActionsPanel {...defaultProps} selectedNames={new Set()} />,
        );
        expect((getByText('作者を設定') as HTMLButtonElement).disabled).toBe(true);
        expect((getByText('シリーズに登録') as HTMLButtonElement).disabled).toBe(true);
    });

    it('選択ありのとき「作者を設定」「シリーズに登録」が有効', () => {
        const { getByText } = render(
            <BulkActionsPanel
                {...defaultProps}
                selectedNames={new Set(['book-a'])}
            />,
        );
        expect((getByText('作者を設定') as HTMLButtonElement).disabled).toBe(false);
        expect((getByText('シリーズに登録') as HTMLButtonElement).disabled).toBe(false);
    });

    it('「作者を設定」クリックで onOpenAuthorDialog が呼ばれる', () => {
        const onOpenAuthorDialog = vi.fn();
        const { getByText } = render(
            <BulkActionsPanel
                {...defaultProps}
                selectedNames={new Set(['book-a'])}
                onOpenAuthorDialog={onOpenAuthorDialog}
            />,
        );
        fireEvent.click(getByText('作者を設定'));
        expect(onOpenAuthorDialog).toHaveBeenCalledTimes(1);
    });

    it('「シリーズに登録」クリックで onOpenSeriesDialog が呼ばれる', () => {
        const onOpenSeriesDialog = vi.fn();
        const { getByText } = render(
            <BulkActionsPanel
                {...defaultProps}
                selectedNames={new Set(['book-a'])}
                onOpenSeriesDialog={onOpenSeriesDialog}
            />,
        );
        fireEvent.click(getByText('シリーズに登録'));
        expect(onOpenSeriesDialog).toHaveBeenCalledTimes(1);
    });
});
