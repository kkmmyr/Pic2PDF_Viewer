import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { PageGridOverlay } from '../components/reader/PageGridOverlay';

const renderOverlay = (overrides: Partial<React.ComponentProps<typeof PageGridOverlay>> = {}) => {
    const props = {
        open: true,
        selectedPdf: 'book.pdf',
        currentPath: '',
        currentSource: 'generated' as const,
        numPages: 10,
        pdfVersion: 0,
        selectedPages: new Set<number>(),
        onClose: vi.fn(),
        onTogglePage: vi.fn(),
        onSelectRange: vi.fn(),
        onRequestDelete: vi.fn(),
        ...overrides,
    };
    return { props, ...render(<PageGridOverlay {...props} />) };
};

describe('PageGridOverlay', () => {
    it('open=false なら何も描画しない', () => {
        const { container } = renderOverlay({ open: false });
        expect(container.firstChild).toBeNull();
    });

    it('numPages 件分のページボタンを描画する', () => {
        const { getAllByRole } = renderOverlay({ numPages: 5 });
        // ヘッダーの「閉じる」+ フッターの「削除実行」+ ページ数 の合計
        const buttons = getAllByRole('button');
        expect(buttons.length).toBe(5 + 2);
    });

    it('サムネイル URL に pdfVersion が含まれる（キャッシュ無効化）', () => {
        const { container } = renderOverlay({ pdfVersion: 7, numPages: 1 });
        const img = container.querySelector('img');
        expect(img?.getAttribute('src')).toContain('v=7');
    });

    it('ページボタンのクリックで onTogglePage が呼ばれる', () => {
        const onTogglePage = vi.fn();
        const { getByAltText } = renderOverlay({ onTogglePage, numPages: 3 });
        const page2Btn = getByAltText('Page 2').closest('button')!;
        fireEvent.click(page2Btn);
        expect(onTogglePage).toHaveBeenCalledWith(2, expect.anything());
    });

    it('Shift+クリックは初回クリック後に onSelectRange を呼ぶ', () => {
        const onTogglePage = vi.fn();
        const onSelectRange = vi.fn();
        const { getByAltText } = renderOverlay({ onTogglePage, onSelectRange, numPages: 8 });

        // 1 回目（通常クリック）
        fireEvent.click(getByAltText('Page 2').closest('button')!);
        expect(onTogglePage).toHaveBeenCalledWith(2, expect.anything());
        expect(onSelectRange).not.toHaveBeenCalled();

        // 2 回目（Shift クリック）
        fireEvent.click(getByAltText('Page 6').closest('button')!, { shiftKey: true });
        expect(onSelectRange).toHaveBeenCalledWith(2, 6);
    });

    it('lastClickedPage が無い状態で Shift+クリックしても onSelectRange は呼ばれない', () => {
        const onTogglePage = vi.fn();
        const onSelectRange = vi.fn();
        const { getByAltText } = renderOverlay({ onTogglePage, onSelectRange, numPages: 3 });

        fireEvent.click(getByAltText('Page 2').closest('button')!, { shiftKey: true });
        expect(onSelectRange).not.toHaveBeenCalled();
        expect(onTogglePage).toHaveBeenCalledWith(2, expect.anything());
    });

    it('Esc キーで onClose が呼ばれる', () => {
        const onClose = vi.fn();
        renderOverlay({ onClose });
        fireEvent.keyDown(window, { key: 'Escape' });
        expect(onClose).toHaveBeenCalled();
    });

    it('選択 0 件のとき「削除実行」ボタンは disabled', () => {
        const { getByText } = renderOverlay({ selectedPages: new Set() });
        const deleteBtn = getByText(/削除実行/).closest('button') as HTMLButtonElement;
        expect(deleteBtn.disabled).toBe(true);
    });

    it('選択ありで「削除実行」ボタンを押すと onRequestDelete が呼ばれる', () => {
        const onRequestDelete = vi.fn();
        const { getByText } = renderOverlay({
            selectedPages: new Set([1, 2]),
            onRequestDelete,
        });
        const deleteBtn = getByText(/削除実行/).closest('button') as HTMLButtonElement;
        expect(deleteBtn.disabled).toBe(false);
        fireEvent.click(deleteBtn);
        expect(onRequestDelete).toHaveBeenCalled();
    });

    it('ヘッダーの選択件数と総ページ数を表示する', () => {
        const { getByText } = renderOverlay({
            numPages: 12,
            selectedPages: new Set([1, 3, 5]),
        });
        expect(getByText(/全 12 ページ \/ 3 件選択中/)).toBeInTheDocument();
    });
});
