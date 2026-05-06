import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { PdfCard, type PdfCardBadge } from '../components/reader/PdfCard';
import type { PdfFile } from '../types';

const pdf: PdfFile = { name: 'book.pdf', thumbnail: null, created_at: 0 };

const baseProps: Parameters<typeof PdfCard>[0] = {
    pdf,
    isFav: false,
    isSelected: false,
    isGroup: false,
    badge: null,
    isSelectionMode: false,
    showHidden: false,
    onPdfClick: vi.fn(),
};

describe('PdfCard', () => {
    it('PDF タイトルから .pdf を除いた表示が出る', () => {
        const { getByText } = render(<PdfCard {...baseProps} />);
        expect(getByText('book')).toBeInTheDocument();
    });

    it('集約モード（isGroup=true）では badge.displayTitle が表示される', () => {
        const badge: PdfCardBadge = {
            count: 3,
            kind: 'series',
            displayTitle: '鬼滅の刃',
        };
        const { getByText } = render(<PdfCard {...baseProps} isGroup badge={badge} />);
        expect(getByText('鬼滅の刃')).toBeInTheDocument();
    });

    it('getAuthors が値を返すと chip が表示される', () => {
        const getAuthors = (_name: string) => ['作者A', '作者B'];
        const { getByText } = render(<PdfCard {...baseProps} getAuthors={getAuthors} />);
        expect(getByText('作者A')).toBeInTheDocument();
        expect(getByText('作者B')).toBeInTheDocument();
    });

    it('getAuthors が空配列なら chip 領域は描画されない', () => {
        const getAuthors = (_name: string) => [];
        const { container } = render(<PdfCard {...baseProps} getAuthors={getAuthors} />);
        // primary-50 chip class を持つ要素はない
        expect(container.querySelector('.bg-primary-50')).toBeNull();
    });

    it('作者 chip クリックで onAuthorClick が呼ばれ、stopPropagation でカードクリックが起きない', () => {
        const onAuthorClick = vi.fn();
        const onPdfClick = vi.fn();
        const { getByText } = render(
            <PdfCard
                {...baseProps}
                onPdfClick={onPdfClick}
                getAuthors={() => ['X']}
                onAuthorClick={onAuthorClick}
            />,
        );
        fireEvent.click(getByText('X'));
        expect(onAuthorClick).toHaveBeenCalledWith('X');
        // カード本体のクリックハンドラは別経路（PdfCardThumbnail）。chip クリックでは呼ばれない
        expect(onPdfClick).not.toHaveBeenCalled();
    });

    it('getTags 値が返ると # 付き chip が表示される', () => {
        const { getByText } = render(<PdfCard {...baseProps} getTags={() => ['アクション']} />);
        expect(getByText('#アクション')).toBeInTheDocument();
    });

    it('タグ chip クリックで onTagClick が呼ばれる', () => {
        const onTagClick = vi.fn();
        const { getByText } = render(
            <PdfCard {...baseProps} getTags={() => ['t1']} onTagClick={onTagClick} />,
        );
        fireEvent.click(getByText('#t1'));
        expect(onTagClick).toHaveBeenCalledWith('t1');
    });

    it('isSelected で amber の枠線スタイルが付く', () => {
        const { container } = render(<PdfCard {...baseProps} isSelected />);
        const root = container.firstChild as HTMLElement;
        expect(root.className).toContain('border-amber-400');
    });

    it('isGroup（badge あり）で accent ボーダーが付く', () => {
        const { container } = render(
            <PdfCard
                {...baseProps}
                isGroup
                badge={{ count: 3, kind: 'series', displayTitle: 'X' }}
            />,
        );
        expect((container.firstChild as HTMLElement).className).toContain('border-accent-300');
    });

    it('created_at から日付文字列が表示される（非空）', () => {
        // 1700000000 = 2023 年付近
        const pdfWithDate: PdfFile = { name: 'a.pdf', thumbnail: null, created_at: 1700000000 };
        const { container } = render(<PdfCard {...baseProps} pdf={pdfWithDate} />);
        // formatTimestampJa の出力は OS ロケール依存だが、'2023' を含む可能性が高い
        expect(container.textContent).toMatch(/2023|2024/);
    });
});
