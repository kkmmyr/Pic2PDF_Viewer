import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('../config/api_client', async () => {
    const actual =
        await vi.importActual<typeof import('../config/api_client')>('../config/api_client');
    return {
        default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
        ApiError: actual.ApiError,
    };
});

import apiClient, { ApiError } from '@/config/api_client';
import { HitomiWatchlistDialog } from '@/components/hitomi/HitomiWatchlistDialog';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockedDelete = apiClient.delete as ReturnType<typeof vi.fn>;

const renderDialog = (overrides: Partial<Parameters<typeof HitomiWatchlistDialog>[0]> = {}) => {
    const props = {
        open: true,
        onClose: vi.fn(),
        onError: vi.fn(),
        onSuccess: vi.fn(),
        ...overrides,
    };
    return { props, ...render(<HitomiWatchlistDialog {...props} />) };
};

describe('HitomiWatchlistDialog', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
        mockedDelete.mockReset();
    });

    it('open=false で非表示', () => {
        mockedGet.mockResolvedValue({ artists: [] });
        const { container } = renderDialog({ open: false });
        expect(container.firstChild).toBeNull();
    });

    it('一覧 0 件で「監視対象が登録されていません」', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        const { getByText } = renderDialog();
        await waitFor(() => expect(getByText(/登録されていません/)).toBeInTheDocument());
    });

    it('artists を一覧として描画', async () => {
        mockedGet.mockResolvedValue({
            artists: [
                {
                    display_name: 'あかしお',
                    normalized: 'akashio',
                    language: 'japanese',
                    added_at: '2026-05-01',
                },
                {
                    display_name: 'foo bar',
                    normalized: 'foobar',
                    language: 'english',
                    added_at: '2026-05-02',
                },
            ],
        });
        const { getByText } = renderDialog();
        await waitFor(() => expect(getByText('あかしお')).toBeInTheDocument());
        expect(getByText('foo bar')).toBeInTheDocument();
        expect(getByText(/監視中（2 件）/)).toBeInTheDocument();
    });

    it('入力 + 追加ボタンで POST → onSuccess', async () => {
        mockedGet.mockResolvedValueOnce({ artists: [] });
        mockedPost.mockResolvedValue({ message: 'ok', normalized: 'foo' });
        mockedGet.mockResolvedValueOnce({
            artists: [
                {
                    display_name: 'foo',
                    normalized: 'foo',
                    language: 'japanese',
                    added_at: '2026-05-06',
                },
            ],
        });

        const { props, getByPlaceholderText, getByText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        fireEvent.change(getByPlaceholderText(/作者名/), { target: { value: 'foo' } });
        await act(async () => {
            fireEvent.click(getByText('追加'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() =>
            expect(props.onSuccess).toHaveBeenCalledWith('foo を監視対象に追加しました'),
        );
    });

    it('追加が空 input なら呼ばれない', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        const { getByText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        fireEvent.click(getByText('追加'));
        expect(mockedPost).not.toHaveBeenCalled();
    });

    it('追加 404 で「見つかりません」エラー', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        mockedPost.mockRejectedValue(new ApiError('not found', 404, 'client'));

        const { props, getByPlaceholderText, getByText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        fireEvent.change(getByPlaceholderText(/作者名/), { target: { value: 'unknown' } });
        await act(async () => {
            fireEvent.click(getByText('追加'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() =>
            expect(props.onError).toHaveBeenCalledWith(
                expect.stringContaining('hitomi.la に「unknown」が見つかりません'),
            ),
        );
    });

    it('追加 400 で ApiError.message がそのまま渡る', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        mockedPost.mockRejectedValue(new ApiError('既に登録済み', 400, 'client'));

        const { props, getByPlaceholderText, getByText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        fireEvent.change(getByPlaceholderText(/作者名/), { target: { value: 'dup' } });
        await act(async () => {
            fireEvent.click(getByText('追加'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() => expect(props.onError).toHaveBeenCalledWith('既に登録済み'));
    });

    it('言語セレクトの値が POST body の language に乗る', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        mockedPost.mockResolvedValue({ message: 'ok', normalized: 'x' });

        const { getByPlaceholderText, getByText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        fireEvent.change(getByPlaceholderText(/作者名/), { target: { value: 'x' } });
        const select = document.body.querySelector('select')!;
        fireEvent.change(select, { target: { value: 'english' } });

        await act(async () => {
            fireEvent.click(getByText('追加'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() =>
            expect(mockedPost).toHaveBeenCalledWith('/api/hitomi/watchlist', {
                display_name: 'x',
                language: 'english',
            }),
        );
    });

    it('Enter キーで追加', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        mockedPost.mockResolvedValue({ message: 'ok', normalized: 'y' });

        const { getByPlaceholderText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());

        const input = getByPlaceholderText(/作者名/);
        fireEvent.change(input, { target: { value: 'y' } });
        await act(async () => {
            fireEvent.keyDown(input, { key: 'Enter' });
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() => expect(mockedPost).toHaveBeenCalled());
    });

    it('閉じるボタンで onClose', async () => {
        mockedGet.mockResolvedValue({ artists: [] });
        const { props, getByText } = renderDialog();
        await waitFor(() => expect(mockedGet).toHaveBeenCalled());
        fireEvent.click(getByText('閉じる'));
        expect(props.onClose).toHaveBeenCalled();
    });
});
