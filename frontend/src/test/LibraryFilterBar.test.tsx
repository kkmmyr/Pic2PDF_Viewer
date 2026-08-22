import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LibraryFilterBar } from '@/components/library/LibraryFilterBar';

const baseProps: Parameters<typeof LibraryFilterBar>[0] = {
    searchText: '',
    authorFilter: '',
    allAuthors: ['作者A', '作者B'],
    groupMode: 'none',
    readStateFilter: '',
    showHidden: false,
    sortOrder: 'name_asc',
    currentSource: 'doujin',
    hideAuthorSelect: false,
    isSelectionMode: false,
    isLoading: false,
    activeFilterCount: 0,
    resultBookCount: 5,
    totalBookCount: 10,
    onSearchChange: vi.fn(),
    onAuthorFilterChange: vi.fn(),
    onGroupModeChange: vi.fn(),
    onReadStateFilterChange: vi.fn(),
    onToggleShowHidden: vi.fn(),
    onSortChange: vi.fn(),
    onToggleSelectionMode: vi.fn(),
    onClearFilters: vi.fn(),
};

function renderFilterBar(overrides: Partial<Parameters<typeof LibraryFilterBar>[0]> = {}) {
    const props = { ...baseProps, ...overrides };
    const queryClient = new QueryClient({
        defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    return {
        props,
        ...render(
            <QueryClientProvider client={queryClient}>
                <LibraryFilterBar {...props} />
            </QueryClientProvider>,
        ),
    };
}

describe('LibraryFilterBar', () => {
    it('モバイルは全幅検索、絞り込み、並び替え、件数を主要操作として表示する', () => {
        renderFilterBar();
        const mobile = screen.getByTestId('mobile-library-controls');

        expect(within(mobile).getByRole('searchbox', { name: '書籍を検索' })).toBeInTheDocument();
        expect(within(mobile).getByRole('button', { name: '絞り込み' })).toBeInTheDocument();
        expect(within(mobile).getByLabelText('並び替え')).toBeInTheDocument();
        expect(within(mobile).getByText('5 / 10冊')).toBeInTheDocument();
    });

    it('適用中条件数をボタンbadgeと状態表示へ反映する', () => {
        renderFilterBar({ activeFilterCount: 2, resultBookCount: 3 });
        const mobile = screen.getByTestId('mobile-library-controls');

        expect(
            within(mobile).getByRole('button', { name: '絞り込み、2件の条件を適用中' }),
        ).toBeInTheDocument();
        expect(within(mobile).getByText('2条件')).toBeInTheDocument();
        expect(within(mobile).getByText('3 / 10冊')).toBeInTheDocument();
    });

    it('絞り込みダイアログから詳細条件と二次操作へ到達できる', () => {
        const onToggleShowHidden = vi.fn();
        renderFilterBar({ onToggleShowHidden });

        fireEvent.click(
            within(screen.getByTestId('mobile-library-controls')).getByRole('button', {
                name: '絞り込み',
            }),
        );

        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByText('絞り込み')).toBeInTheDocument();
        expect(within(dialog).getByLabelText('表示方法')).toBeInTheDocument();
        expect(within(dialog).getByLabelText('読書状態')).toBeInTheDocument();
        expect(within(dialog).getByPlaceholderText('作者: すべて')).toBeInTheDocument();

        fireEvent.click(within(dialog).getByRole('button', { name: '非表示の書籍を表示' }));
        expect(onToggleShowHidden).toHaveBeenCalledTimes(1);
    });

    it('絞り込みダイアログから条件を一括解除できる', () => {
        const onClearFilters = vi.fn();
        renderFilterBar({ activeFilterCount: 3, onClearFilters });

        fireEvent.click(
            within(screen.getByTestId('mobile-library-controls')).getByRole('button', {
                name: '絞り込み、3件の条件を適用中',
            }),
        );
        fireEvent.click(
            within(screen.getByRole('dialog')).getByRole('button', { name: '条件をクリア' }),
        );

        expect(onClearFilters).toHaveBeenCalledTimes(1);
    });

    it('絞り込みダイアログから選択モードを開始して閉じる', () => {
        const onToggleSelectionMode = vi.fn();
        renderFilterBar({ onToggleSelectionMode });

        fireEvent.click(
            within(screen.getByTestId('mobile-library-controls')).getByRole('button', {
                name: '絞り込み',
            }),
        );
        fireEvent.click(
            within(screen.getByRole('dialog')).getByRole('button', { name: '書籍を選択' }),
        );

        expect(onToggleSelectionMode).toHaveBeenCalledTimes(1);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('PCは主要条件と二次操作を分け、選択・非表示一覧・ツールを表示する', () => {
        renderFilterBar();
        const desktop = screen.getByTestId('desktop-library-controls');

        expect(within(desktop).getByLabelText('表示方法')).toBeInTheDocument();
        expect(within(desktop).getByLabelText('読書状態')).toBeInTheDocument();
        expect(within(desktop).getByRole('button', { name: '選択' })).toBeInTheDocument();
        expect(within(desktop).getByRole('button', { name: '非表示一覧' })).toBeInTheDocument();
        expect(within(desktop).getByRole('button', { name: 'ツール' })).toBeInTheDocument();
    });
});
