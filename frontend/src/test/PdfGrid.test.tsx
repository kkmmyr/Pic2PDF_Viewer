import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { PdfGrid } from '@/components/library/PdfGrid';
import type { PdfFile } from '@/types';

const pdf = (name: string): PdfFile => ({ name, thumbnail: null, created_at: 0 });

describe('PdfGrid', () => {
    it('読み込み中はスケルトン用の案内を表示し、空状態を表示しない', () => {
        const { getByText, queryByText } = render(
            <PdfGrid pdfs={[]} onPdfClick={vi.fn()} isLoading />,
        );
        expect(getByText('ライブラリを読み込み中…')).toBeInTheDocument();
        expect(getByText('初回の読み込みには時間がかかる場合があります')).toBeInTheDocument();
        expect(queryByText('書籍がありません')).not.toBeInTheDocument();
    });

    it('取得完了後に pdfs が空なら日本語の空状態を表示する', () => {
        const { getByText, queryByText } = render(<PdfGrid pdfs={[]} onPdfClick={vi.fn()} />);
        expect(getByText('書籍がありません')).toBeInTheDocument();
        expect(getByText('取り込み画面から書籍を追加できます')).toBeInTheDocument();
        expect(queryByText('ライブラリを読み込み中…')).not.toBeInTheDocument();
    });

    it('登録書籍があり filter 結果だけが空なら条件不一致と解除操作を表示する', () => {
        const onClearFilters = vi.fn();
        const { getByRole, getByText, queryByText } = render(
            <PdfGrid
                pdfs={[]}
                onPdfClick={vi.fn()}
                isLibraryEmpty={false}
                onClearFilters={onClearFilters}
            />,
        );

        expect(getByText('条件に一致する書籍がありません')).toBeInTheDocument();
        expect(getByText('検索条件や絞り込みを変更してください')).toBeInTheDocument();
        expect(queryByText('書籍がありません')).not.toBeInTheDocument();

        fireEvent.click(getByRole('button', { name: '条件をクリア' }));
        expect(onClearFilters).toHaveBeenCalledTimes(1);
    });

    it('一覧取得失敗は空状態を表示せず再試行できる', () => {
        const onRetry = vi.fn();
        const { getByRole, getByText, queryByText } = render(
            <PdfGrid pdfs={[]} onPdfClick={vi.fn()} isError onRetry={onRetry} />,
        );

        expect(getByText('ライブラリ情報を取得できませんでした')).toBeInTheDocument();
        expect(queryByText('書籍がありません')).not.toBeInTheDocument();
        expect(queryByText('条件に一致する書籍がありません')).not.toBeInTheDocument();

        fireEvent.click(getByRole('button', { name: '再試行' }));
        expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('読み込み中は取得失敗より優先して表示する', () => {
        const { getByText, queryByText } = render(
            <PdfGrid pdfs={[]} onPdfClick={vi.fn()} isLoading isError />,
        );
        expect(getByText('ライブラリを読み込み中…')).toBeInTheDocument();
        expect(queryByText('ライブラリ情報を取得できませんでした')).not.toBeInTheDocument();
    });

    it('見出し "書籍" は常に表示される', () => {
        const { getByText } = render(<PdfGrid pdfs={[pdf('a.pdf')]} onPdfClick={vi.fn()} />);
        expect(getByText('書籍')).toBeInTheDocument();
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
