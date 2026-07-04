import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../config/generate_api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
    toast: { error: vi.fn(), success: vi.fn() },
}));

import generateApiClient from '@/config/generate_api_client';
import { ApiError } from '@/config/api_client';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/config/api';
import GeneratorPage from '@/pages/GeneratorPage';
import type { DoujinWatcherStatus, GenerateJob } from '@/types';

const mockedGet = generateApiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = generateApiClient.post as ReturnType<typeof vi.fn>;

const buildWatcher = (overrides: Partial<DoujinWatcherStatus> = {}): DoujinWatcherStatus => ({
    enabled: true,
    state: 'idle',
    interval_sec: 15,
    last_scan_at: null,
    pending_items: [],
    active_job_id: null,
    last_auto_job: null,
    retry_blocked: false,
    ...overrides,
});

const buildJob = (overrides: Partial<GenerateJob> = {}): GenerateJob => ({
    job_id: 'jid-1',
    status: 'pending',
    current_item: null,
    files: [],
    failed_items: [],
    message: '',
    error: null,
    ...overrides,
});

/** watcher / job のスタブを URL 引数で切り替える generateApiClient.get モックを構築する */
function mockGetByUrl(opts: { watcher?: DoujinWatcherStatus; jobs?: Record<string, GenerateJob> }) {
    const watcher = opts.watcher ?? buildWatcher();
    const jobs = opts.jobs ?? {};
    mockedGet.mockImplementation((url: string) => {
        if (url === API_ENDPOINTS.GENERATE_WATCHER) return Promise.resolve(watcher);
        for (const [jobId, job] of Object.entries(jobs)) {
            if (url === API_ENDPOINTS.GENERATE_JOB(jobId)) return Promise.resolve(job);
        }
        return Promise.reject(new ApiError('not found', 404, 'client'));
    });
}

function renderPage() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 30_000 } },
    });
    return render(
        React.createElement(QueryClientProvider, { client: queryClient }, <GeneratorPage />),
    );
}

describe('GeneratorPage', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
        vi.mocked(toast.error).mockReset();
        localStorage.clear();
    });

    it.each([
        ['idle', '監視中（新着なし）'],
        ['waiting_stable', 'コピー完了待ち'],
        ['running', '取り込み実行中'],
        ['input_missing', '入力フォルダに接続できません'],
        ['disabled', '自動取り込み無効'],
    ] as const)('watcher state=%s のラベルが表示される', async (state, label) => {
        mockGetByUrl({ watcher: buildWatcher({ state }) });
        renderPage();
        await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
    });

    it('pending_items が表示される', async () => {
        mockGetByUrl({
            watcher: buildWatcher({
                pending_items: [
                    { name: 'sample.zip', kind: 'zip' },
                    { name: 'sample_folder', kind: 'folder' },
                ],
            }),
        });
        renderPage();
        await waitFor(() => expect(screen.getByText('sample.zip')).toBeInTheDocument());
        expect(screen.getByText('sample_folder')).toBeInTheDocument();
    });

    it('retry_blocked の警告が表示される', async () => {
        mockGetByUrl({ watcher: buildWatcher({ retry_blocked: true }) });
        renderPage();
        await waitFor(() =>
            expect(
                screen.getByText(
                    '前回失敗したアイテムが残っています。『今すぐスキャン』で再試行できます',
                ),
            ).toBeInTheDocument(),
        );
    });

    it('今すぐスキャン クリックで POST が 409 の場合、toast.error が呼ばれ、抽出した job_id の進捗が取得される', async () => {
        mockGetByUrl({
            watcher: buildWatcher(),
            jobs: { 'abc-123': buildJob({ job_id: 'abc-123', status: 'running' }) },
        });
        mockedPost.mockRejectedValue(
            new ApiError('Generation already running (job_id=abc-123)', 409, 'client'),
        );

        renderPage();
        await waitFor(() => expect(screen.getByText('監視中（新着なし）')).toBeInTheDocument());

        fireEvent.click(screen.getByText('今すぐスキャン'));

        await waitFor(() => expect(toast.error).toHaveBeenCalledWith('取り込みは既に実行中です'));
        await waitFor(() =>
            expect(mockedGet).toHaveBeenCalledWith(API_ENDPOINTS.GENERATE_JOB('abc-123')),
        );
    });

    it('watcher.active_job_id が未追跡の新しい id の場合、そのジョブ進捗が取得される', async () => {
        mockGetByUrl({
            watcher: buildWatcher({ active_job_id: 'auto-999' }),
            jobs: { 'auto-999': buildJob({ job_id: 'auto-999', status: 'running' }) },
        });

        renderPage();

        await waitFor(() =>
            expect(mockedGet).toHaveBeenCalledWith(API_ENDPOINTS.GENERATE_JOB('auto-999')),
        );
    });
});
