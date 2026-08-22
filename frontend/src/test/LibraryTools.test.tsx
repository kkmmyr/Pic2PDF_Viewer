import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({
    toast: {
        error: vi.fn(),
        success: vi.fn(),
    },
}));

vi.mock('@/config/api_client', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

import { ToolsMenu } from '@/components/library/ToolsMenu';
import { AmazonImportButton } from '@/components/novel_build/AmazonImportButton';
import apiClient from '@/config/api_client';
import { toast } from 'sonner';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            mutations: { retry: false },
            queries: { retry: false },
        },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

describe('Library manual tools', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        Object.defineProperty(URL, 'createObjectURL', {
            configurable: true,
            value: vi.fn(() => 'blob:meta-export'),
        });
        Object.defineProperty(URL, 'revokeObjectURL', {
            configurable: true,
            value: vi.fn(),
        });
        vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('Amazon取込はinterceptor後の本文を集約して実件数を表示する', async () => {
        mockedPost
            .mockResolvedValueOnce({ updated: 2, skipped: 3, unmatched: 4 })
            .mockResolvedValueOnce({ updated: 5, skipped: 6, unmatched: 7 });

        render(<AmazonImportButton />, { wrapper: createWrapper() });
        fireEvent.click(screen.getByRole('button', { name: 'Amazon CSV' }));

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(
                '更新: 7 件 / スキップ: 9 件 / 未マッチ: 11 件',
            );
        });
        expect(mockedPost).toHaveBeenNthCalledWith(1, '/api/amazon/import?source=novel');
        expect(mockedPost).toHaveBeenNthCalledWith(2, '/api/amazon/import?source=comic');
    });

    it('Amazon取込は片方が失敗しても成功分に更新があれば集約結果を表示する', async () => {
        mockedPost
            .mockRejectedValueOnce(new Error('novel failed'))
            .mockResolvedValueOnce({ updated: 1, skipped: 2, unmatched: 3 });

        render(<AmazonImportButton />, { wrapper: createWrapper() });
        fireEvent.click(screen.getByRole('button', { name: 'Amazon CSV' }));

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(
                '更新: 1 件 / スキップ: 2 件 / 未マッチ: 3 件',
            );
        });
        expect(toast.error).not.toHaveBeenCalled();
    });

    it('Amazon取込は両方が失敗したとき最初のerrorを表示する', async () => {
        mockedPost
            .mockRejectedValueOnce(new Error('novel failed'))
            .mockRejectedValueOnce(new Error('comic failed'));

        render(<AmazonImportButton />, { wrapper: createWrapper() });
        fireEvent.click(screen.getByRole('button', { name: 'Amazon CSV' }));

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('インポート失敗: novel failed');
        });
        expect(toast.success).not.toHaveBeenCalled();
    });

    it('Amazon取込中はbuttonをdisabledにして二重送信を防ぐ', async () => {
        let resolveNovel!: (value: { updated: number; skipped: number; unmatched: number }) => void;
        let resolveComic!: (value: { updated: number; skipped: number; unmatched: number }) => void;
        mockedPost
            .mockReturnValueOnce(
                new Promise((resolve) => {
                    resolveNovel = resolve;
                }),
            )
            .mockReturnValueOnce(
                new Promise((resolve) => {
                    resolveComic = resolve;
                }),
            );

        render(<AmazonImportButton />, { wrapper: createWrapper() });
        const button = screen.getByRole('button', { name: 'Amazon CSV' });
        fireEvent.click(button);
        await waitFor(() => expect(button).toBeDisabled());

        resolveNovel({ updated: 0, skipped: 0, unmatched: 0 });
        resolveComic({ updated: 0, skipped: 0, unmatched: 0 });
        await waitFor(() => expect(button).not.toBeDisabled());
    });

    it('meta exportはBlobをdownloadしてobject URLを必ず解放する', async () => {
        const blob = new Blob(['{}'], { type: 'application/json' });
        mockedGet.mockResolvedValue(blob);

        render(<ToolsMenu source="doujin" />, { wrapper: createWrapper() });
        fireEvent.click(screen.getByRole('button', { name: 'ツール' }));
        fireEvent.click(screen.getByRole('button', { name: 'エクスポート' }));

        await waitFor(() => {
            expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
        });
        expect(mockedGet).toHaveBeenCalledWith('/api/meta/export?source=doujin', {
            responseType: 'blob',
        });
        expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
        expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:meta-export');
    });

    it('meta export中はbuttonをdisabledにして完了後に戻す', async () => {
        let resolveExport!: (value: Blob) => void;
        mockedGet.mockReturnValue(
            new Promise((resolve) => {
                resolveExport = resolve;
            }),
        );

        render(<ToolsMenu source="comic" />, { wrapper: createWrapper() });
        fireEvent.click(screen.getByRole('button', { name: 'ツール' }));
        const exportButton = screen.getByRole('button', { name: 'エクスポート' });
        fireEvent.click(exportButton);
        await waitFor(() => expect(exportButton).toBeDisabled());

        resolveExport(new Blob(['{}'], { type: 'application/json' }));
        await waitFor(() => expect(exportButton).not.toBeDisabled());
    });
});
