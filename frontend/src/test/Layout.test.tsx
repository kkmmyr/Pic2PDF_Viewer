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
        expect(screen.getByRole('link', { name: 'ライブラリ' })).toHaveAttribute('href', '/doujin');
    });
});
