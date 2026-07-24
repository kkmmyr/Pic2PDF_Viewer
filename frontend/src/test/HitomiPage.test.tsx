import { fireEvent, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/useHitomiArrivals', () => ({
    useHitomiArrivals: vi.fn(),
}));

vi.mock('@/hooks/useAsyncToast', () => ({
    useAsyncToast: () => async (operation: () => Promise<unknown>) => operation(),
}));

import { useHitomiArrivals } from '@/hooks/useHitomiArrivals';
import HitomiPage from '@/pages/HitomiPage';

const mockedUseHitomiArrivals = vi.mocked(useHitomiArrivals);

describe('HitomiPage', () => {
    beforeEach(() => {
        mockedUseHitomiArrivals.mockImplementation((status) => ({
            items: [],
            total: status === 'read' ? 311 : 2,
            unreadCount: 2,
            readCount: 311,
            lastRunAt: null,
            lastRunStatus: 'ok',
            lastError: null,
            loading: false,
            running: false,
            error: null,
            refresh: vi.fn().mockResolvedValue(undefined),
            dismiss: vi.fn().mockResolvedValue(undefined),
            dismissAll: vi.fn().mockResolvedValue(undefined),
            runNow: vi.fn().mockResolvedValue(null),
        }));
    });

    it('新着と履歴を切り替えて対応するstatusを取得する', () => {
        const { getByRole } = render(<HitomiPage />);

        expect(mockedUseHitomiArrivals).toHaveBeenLastCalledWith('unread', 0, 60);
        fireEvent.click(getByRole('button', { name: /履歴 \(311\)/ }));
        expect(mockedUseHitomiArrivals).toHaveBeenLastCalledWith('read', 0, 60);
        expect(getByRole('button', { name: /履歴 \(311\)/ })).toBeInTheDocument();
    });
});
