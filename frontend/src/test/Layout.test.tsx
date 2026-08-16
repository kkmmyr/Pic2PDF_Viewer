import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Layout from '@/components/Layout';

const darkModeMocks = vi.hoisted(() => ({ toggle: vi.fn() }));

vi.mock('@/hooks', () => ({
    useDarkMode: () => ({ isDark: false, toggle: darkModeMocks.toggle }),
}));

describe('Layout', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        darkModeMocks.toggle.mockReset();
    });

    it('PCでは主要項目を表示し、カテゴリメニューから同人誌ライブラリへ遷移できる', () => {
        render(
            <MemoryRouter initialEntries={['/comic']}>
                <Layout />
            </MemoryRouter>,
        );

        expect(
            screen.getAllByText('Pic2PDF Viewer').every((brand) => brand.closest('a') === null),
        ).toBe(true);

        expect(screen.getByRole('link', { name: '漫画ライブラリ' })).toHaveAttribute(
            'href',
            '/comic',
        );
        expect(screen.getByRole('link', { name: '購入書籍' })).toHaveAttribute(
            'href',
            '/kindle/catalog',
        );

        const categoryButton = screen.getByRole('button', { name: '同人誌メニュー' });
        expect(categoryButton).toHaveAttribute('aria-expanded', 'false');
        fireEvent.click(categoryButton);

        const libraryLink = screen.getByRole('link', { name: '同人誌ライブラリ' });
        expect(libraryLink).toHaveAttribute('href', '/doujin');
        expect(categoryButton).toHaveAttribute('aria-expanded', 'true');
        expect(
            screen.getByRole('navigation', { name: 'グローバルナビゲーション' }),
        ).not.toHaveClass('overflow-x-auto');
    });

    it('カテゴリメニューはEscapeで閉じる', () => {
        render(
            <MemoryRouter initialEntries={['/doujin']}>
                <Layout />
            </MemoryRouter>,
        );

        const categoryButton = screen.getByRole('button', { name: '同人誌メニュー' });
        fireEvent.click(categoryButton);
        expect(screen.getByRole('link', { name: '同人誌ライブラリ' })).toHaveAttribute(
            'aria-current',
            'page',
        );

        fireEvent.keyDown(document, { key: 'Escape' });
        expect(categoryButton).toHaveAttribute('aria-expanded', 'false');
        expect(screen.queryByRole('link', { name: '同人誌ライブラリ' })).not.toBeInTheDocument();
    });

    it('モバイルメニューは現在地とカテゴリ別導線を表示し、閉じられる', () => {
        render(
            <MemoryRouter initialEntries={['/novel/discussion']}>
                <Layout />
            </MemoryRouter>,
        );

        expect(screen.getAllByText('小説').length).toBeGreaterThan(0);
        expect(screen.getAllByText('読書会').length).toBeGreaterThan(0);

        const openButton = screen.getByRole('button', { name: 'メニューを開く' });
        fireEvent.click(openButton);

        const mobileNavigation = screen.getByRole('navigation', {
            name: 'モバイルナビゲーション',
        });
        expect(mobileNavigation).toBeInTheDocument();
        expect(screen.getByRole('link', { name: '同人誌ライブラリ' })).toHaveAttribute(
            'href',
            '/doujin',
        );
        expect(screen.getByRole('link', { name: '書籍DB' })).toHaveAttribute('href', '/novel/db');
        expect(screen.getByRole('link', { name: '読書会' })).toHaveAttribute(
            'aria-current',
            'page',
        );
        const themeButton = within(mobileNavigation).getByRole('button', {
            name: 'ダークモードに切り替え',
        });
        fireEvent.click(themeButton);
        expect(darkModeMocks.toggle).toHaveBeenCalledOnce();
        expect(mobileNavigation).toBeInTheDocument();

        const drawerCloseButton = screen.getByRole('button', { name: 'メニューを閉じる' });
        expect(drawerCloseButton).toHaveFocus();
        fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
        expect(screen.getByRole('link', { name: '設計書' })).toHaveFocus();

        fireEvent.click(drawerCloseButton);
        expect(
            screen.queryByRole('navigation', { name: 'モバイルナビゲーション' }),
        ).not.toBeInTheDocument();
    });

    it('モバイルメニューはEscapeで閉じて開くボタンへフォーカスを戻す', () => {
        vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
            callback(0);
            return 1;
        });
        render(
            <MemoryRouter initialEntries={['/kindle/capture']}>
                <Layout />
            </MemoryRouter>,
        );

        const openButton = screen.getByRole('button', { name: 'メニューを開く' });
        fireEvent.click(openButton);
        fireEvent.keyDown(document, { key: 'Escape' });

        expect(
            screen.queryByRole('navigation', { name: 'モバイルナビゲーション' }),
        ).not.toBeInTheDocument();
        expect(openButton).toHaveFocus();
        expect(screen.getAllByText('キャプチャ').length).toBeGreaterThan(0);
    });
});
