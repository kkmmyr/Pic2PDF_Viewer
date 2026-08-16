import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { PdfCard, type PdfCardBadge } from '@/components/library/PdfCard';
import type { PdfFile } from '@/types';

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

    it('readState="unread" で 未読バッジを表示', () => {
        const { getByLabelText } = render(<PdfCard {...baseProps} readState="unread" />);
        expect(getByLabelText('未読')).toBeInTheDocument();
    });

    it('readState="reading" で 読書中 バッジを表示', () => {
        const { getByLabelText } = render(<PdfCard {...baseProps} readState="reading" />);
        expect(getByLabelText('読書中')).toHaveClass('bg-accent-100');
    });

    it('readState="done" で 読了 バッジを表示', () => {
        const { getByLabelText } = render(<PdfCard {...baseProps} readState="done" />);
        expect(getByLabelText('読了')).toBeInTheDocument();
    });

    it('集約カード (isGroup=true) では readState バッジは表示されない', () => {
        const badge: PdfCardBadge = { count: 3, kind: 'series', displayTitle: 'シリーズX' };
        const { queryByLabelText } = render(
            <PdfCard {...baseProps} isGroup badge={badge} readState="unread" />,
        );
        expect(queryByLabelText('未読')).toBeNull();
        expect(queryByLabelText('読書中')).toBeNull();
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

    it('登録日・読書状態・操作を折り返さない同じ行に表示する', () => {
        const pdfWithDate: PdfFile = { name: 'a.pdf', thumbnail: null, created_at: 1700000000 };
        const { getByLabelText, getByRole } = render(
            <PdfCard {...baseProps} pdf={pdfWithDate} readState="reading" onRename={vi.fn()} />,
        );

        const footerRow = getByRole('group', { name: 'a の補助情報と操作' });
        expect(footerRow.className).toContain('flex-nowrap');
        expect(footerRow.textContent).toMatch(/2023|2024/);
        expect(footerRow).toContainElement(getByLabelText('読書中'));
        expect(getByRole('button', { name: 'a の操作を開く' })).toBeInTheDocument();
    });

    it('表紙は書籍名を含むアクセシブルなボタンとして開ける', () => {
        const onPdfClick = vi.fn();
        const { getByRole } = render(<PdfCard {...baseProps} onPdfClick={onPdfClick} />);

        fireEvent.click(getByRole('button', { name: 'book を読む' }));
        expect(onPdfClick).toHaveBeenCalledWith('book.pdf');
    });

    it('その他の操作を開き、ラベル付き操作を実行できる', () => {
        const onRename = vi.fn();
        const { getByRole } = render(<PdfCard {...baseProps} onRename={onRename} />);

        const trigger = getByRole('button', { name: 'book の操作を開く' });
        fireEvent.click(trigger);
        const rename = getByRole('button', { name: 'bookの名前を変更' });
        expect(rename).toHaveFocus();
        fireEvent.click(rename);
        expect(onRename).toHaveBeenCalledWith('book.pdf');
    });

    it('その他の操作は Escape で閉じてトリガーへフォーカスを戻す', () => {
        const { getByRole, queryByRole } = render(<PdfCard {...baseProps} onRename={vi.fn()} />);

        const trigger = getByRole('button', { name: 'book の操作を開く' });
        fireEvent.click(trigger);
        fireEvent.keyDown(getByRole('button', { name: 'bookの名前を変更' }), {
            key: 'Escape',
        });

        expect(queryByRole('button', { name: 'bookの名前を変更' })).not.toBeInTheDocument();
        expect(trigger).toHaveFocus();
    });
});
