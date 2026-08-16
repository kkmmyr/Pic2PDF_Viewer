import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { SeriesDrilldownPanel } from '@/components/novel_db/SeriesDrilldownPanel';
import type { BookSummary } from '@/features/novel_db/types';

// SeriesDrilldownView は DnD 依存のため stub
vi.mock('../components/novel_db/SeriesDrilldownView', () => ({
    default: () => <div data-testid="series-drilldown-view" />,
}));

const makeBook = (name: string): BookSummary => ({
    name,
    authors: [],
    series_id: 's1',
    series_title: 'テストシリーズ',
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
});

const drilldown = {
    seriesId: 's1',
    label: 'テストシリーズ',
    books: [makeBook('book-a'), makeBook('book-b')],
};

const defaultProps = {
    drilldown,
    isSelecting: false,
    selectedNames: new Set<string>(),
    renderCard: (book: BookSummary) => <div key={book.name} data-testid={`card-${book.name}`} />,
    onBack: vi.fn(),
    onToggleSelecting: vi.fn(),
    onToggleSelectAll: vi.fn(),
    onOpenAuthorDialog: vi.fn(),
    onOpenSeriesDialog: vi.fn(),
    onOpenDetailBook: vi.fn(),
    onEditBook: vi.fn(),
    onReordered: vi.fn(),
};

describe('SeriesDrilldownPanel', () => {
    it('パンくずにシリーズ名と件数を表示する', () => {
        const { getByText } = render(<SeriesDrilldownPanel {...defaultProps} />);
        expect(getByText('テストシリーズ')).toBeInTheDocument();
        expect(getByText('(2 冊)')).toBeInTheDocument();
    });

    it('「ライブラリ」ボタンをクリックすると onBack が呼ばれる', () => {
        const onBack = vi.fn();
        const { getByText } = render(<SeriesDrilldownPanel {...defaultProps} onBack={onBack} />);
        fireEvent.click(getByText('ライブラリ'));
        expect(onBack).toHaveBeenCalledTimes(1);
    });

    it('非選択時に SeriesDrilldownView が表示される', () => {
        const { getByTestId, queryByTestId } = render(
            <SeriesDrilldownPanel {...defaultProps} isSelecting={false} />,
        );
        expect(getByTestId('series-drilldown-view')).toBeInTheDocument();
        expect(queryByTestId('card-book-a')).toBeNull();
    });

    it('選択中は renderCard が呼ばれ SeriesDrilldownView が非表示', () => {
        const { getByTestId, queryByTestId } = render(
            <SeriesDrilldownPanel {...defaultProps} isSelecting={true} />,
        );
        expect(getByTestId('card-book-a')).toBeInTheDocument();
        expect(queryByTestId('series-drilldown-view')).toBeNull();
    });

    it('選択中はアクションバー（BulkActionsPanel）が表示される', () => {
        const { getByText } = render(<SeriesDrilldownPanel {...defaultProps} isSelecting={true} />);
        expect(getByText('0 冊選択中')).toBeInTheDocument();
    });

    it('非選択中はアクションバーが非表示', () => {
        const { queryByText } = render(
            <SeriesDrilldownPanel {...defaultProps} isSelecting={false} />,
        );
        expect(queryByText('0 冊選択中')).toBeNull();
    });

    it('「選択」ボタンをクリックすると onToggleSelecting が呼ばれる', () => {
        const onToggleSelecting = vi.fn();
        const { getByText } = render(
            <SeriesDrilldownPanel {...defaultProps} onToggleSelecting={onToggleSelecting} />,
        );
        fireEvent.click(getByText('選択'));
        expect(onToggleSelecting).toHaveBeenCalledTimes(1);
    });
});
