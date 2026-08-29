import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/features/kindle/queries', () => ({
    useKindlePriceHistory: vi.fn(),
    useKindlePriceWatches: vi.fn(),
}));

import KindlePriceWatchPage from '@/pages/KindlePriceWatchPage';
import { useKindlePriceHistory, useKindlePriceWatches } from '@/features/kindle/queries';

const mockedUseKindlePriceHistory = vi.mocked(useKindlePriceHistory);
const mockedUseKindlePriceWatches = vi.mocked(useKindlePriceWatches);
const create = vi.fn();
const update = vi.fn();
const remove = vi.fn();

const watch = {
    id: 1,
    url: 'https://www.amazon.co.jp/dp/B012345678',
    asin: 'B012345678',
    title: 'テスト本',
    threshold_percent: 50,
    notify_on_drop: true,
    notify_below_threshold: true,
    enabled: true,
    created_at: '2026-08-23T10:00:00+09:00',
    updated_at: '2026-08-23T10:00:00+09:00',
    last_checked_at: null,
    last_status: 'never' as const,
    last_error: null,
    last_current_price: null,
    last_list_price: null,
    last_ratio_percent: null,
};

function renderPage() {
    return render(
        <MemoryRouter initialEntries={['/kindle/price-watch']}>
            <KindlePriceWatchPage />
        </MemoryRouter>,
    );
}

describe('KindlePriceWatchPage', () => {
    beforeEach(() => {
        mockedUseKindlePriceHistory.mockReturnValue({
            data: { items: [] },
            isLoading: false,
            error: null,
        } as unknown as ReturnType<typeof useKindlePriceHistory>);
        create.mockReset().mockResolvedValue(watch);
        update.mockReset().mockResolvedValue(watch);
        remove.mockReset().mockResolvedValue({ id: 1, deleted: true });
        mockedUseKindlePriceWatches.mockReturnValue({
            watches: [watch],
            isLoading: false,
            error: null,
            create,
            creating: false,
            update,
            updating: false,
            remove,
            removing: false,
        } as ReturnType<typeof useKindlePriceWatches>);
    });

    it('監視対象を追加できる', async () => {
        renderPage();

        fireEvent.change(screen.getByLabelText(/Amazon商品URL/), {
            target: { value: 'https://www.amazon.co.jp/dp/B098765432' },
        });
        fireEvent.change(screen.getByLabelText('表示名（任意）'), {
            target: { value: '追加する本' },
        });
        fireEvent.click(screen.getByRole('button', { name: '監視対象を追加' }));

        await waitFor(() => {
            expect(create).toHaveBeenCalledWith({
                url: 'https://www.amazon.co.jp/dp/B098765432',
                title: '追加する本',
                threshold_percent: 50,
                notify_on_drop: true,
                notify_below_threshold: true,
                enabled: true,
            });
        });
    });

    it('停止と削除を確認ダイアログ経由で行える', async () => {
        renderPage();

        fireEvent.click(screen.getByRole('button', { name: 'テスト本を停止' }));
        await waitFor(() => {
            expect(update).toHaveBeenCalledWith({ watchId: 1, request: { enabled: false } });
        });

        fireEvent.click(screen.getByRole('button', { name: 'テスト本を削除' }));
        expect(screen.getByRole('alertdialog')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: '削除' }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(1));
    });
});
