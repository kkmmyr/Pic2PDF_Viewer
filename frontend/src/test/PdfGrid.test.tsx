import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { PdfGrid } from '../components/library/PdfGrid';
import type { PdfFile } from '../types';

const pdf = (name: string): PdfFile => ({ name, thumbnail: null, created_at: 0 });

describe('PdfGrid', () => {
    it('pdfs が空なら "No PDFs found." が表示される', () => {
        const { getByText } = render(<PdfGrid pdfs={[]} onPdfClick={vi.fn()} />);
        expect(getByText('No PDFs found.')).toBeInTheDocument();
    });

    it('見出し "PDFs" は常に表示される', () => {
        const { getByText } = render(<PdfGrid pdfs={[pdf('a.pdf')]} onPdfClick={vi.fn()} />);
        expect(getByText('PDFs')).toBeInTheDocument();
    });

    it('各 pdf がカードとして描画される（タイトルから .pdf を除いた名前）', () => {
        const pdfs = [pdf('a.pdf'), pdf('b.pdf'), pdf('c.pdf')];
        const { getByText } = render(<PdfGrid pdfs={pdfs} onPdfClick={vi.fn()} />);
        expect(getByText('a')).toBeInTheDocument();
        expect(getByText('b')).toBeInTheDocument();
        expect(getByText('c')).toBeInTheDocument();
    });

    it('dndEnabled=true でも render 自体は成功する', () => {
        const pdfs = [pdf('a.pdf'), pdf('b.pdf')];
        const { getByText } = render(
            <PdfGrid pdfs={pdfs} onPdfClick={vi.fn()} dndEnabled onReorder={vi.fn()} />,
        );
        expect(getByText('a')).toBeInTheDocument();
        expect(getByText('b')).toBeInTheDocument();
    });

    it('isSelectionMode=true のときは dndEnabled=true でも DnD は無効（通常レンダー経路）', () => {
        const pdfs = [pdf('a.pdf')];
        const onReorder = vi.fn();
        const { getByText } = render(
            <PdfGrid
                pdfs={pdfs}
                onPdfClick={vi.fn()}
                isSelectionMode
                dndEnabled
                onReorder={onReorder}
            />,
        );
        // 描画自体は成功
        expect(getByText('a')).toBeInTheDocument();
    });

    it('getBadge で badge を返した場合、集約モードでタイトルが上書きされる', () => {
        const pdfs = [pdf('rep.pdf')];
        const getBadge = () => ({
            count: 5,
            kind: 'series' as const,
            displayTitle: 'シリーズ X',
        });
        const { getByText } = render(
            <PdfGrid pdfs={pdfs} onPdfClick={vi.fn()} getBadge={getBadge} onGroupClick={vi.fn()} />,
        );
        expect(getByText('シリーズ X')).toBeInTheDocument();
    });

    it('getAuthors が指定されると chip が表示される', () => {
        const pdfs = [pdf('a.pdf')];
        const { getByText } = render(
            <PdfGrid pdfs={pdfs} onPdfClick={vi.fn()} getAuthors={() => ['作者A']} />,
        );
        expect(getByText('作者A')).toBeInTheDocument();
    });
});
