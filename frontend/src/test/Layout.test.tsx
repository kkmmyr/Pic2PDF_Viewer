import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Layout from '@/components/Layout';

vi.mock('@/hooks', () => ({
    useDarkMode: () => ({ isDark: false, toggle: vi.fn() }),
}));

describe('Layout', () => {
    it('製品名はブランド表示とし、同人誌ライブラリは通常リンクで案内する', () => {
        render(
            <MemoryRouter initialEntries={['/comic']}>
                <Layout />
            </MemoryRouter>,
        );

        expect(screen.getByText('Pic2PDF Viewer').closest('a')).toBeNull();

        const libraryLink = screen.getByRole('link', { name: '同人誌ライブラリ' });
        expect(libraryLink).toHaveAttribute('href', '/doujin');
        expect(libraryLink.closest('nav')).toHaveClass('justify-start', 'overflow-x-auto');
        expect(libraryLink.closest('nav')).not.toHaveClass('justify-end', 'xl:justify-end');
        expect(screen.getByRole('link', { name: '漫画ライブラリ' })).toHaveAttribute(
            'href',
            '/comic',
        );
    });
});
