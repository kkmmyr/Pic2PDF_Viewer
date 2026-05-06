import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor, act } from '@testing-library/react';

// ToastContainer の barrel import 経由で PageRenderer → react-pdf が読み込まれ、
// jsdom に DOMMatrix が無いため evaluation で落ちる → ここでモックする。
vi.mock('react-pdf', () => ({
    Page: () => null,
    Document: () => null,
    pdfjs: { GlobalWorkerOptions: { workerSrc: '' } },
}));

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { SeriesResolveBar } from '../components/viewer/SeriesResolveBar';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

const IDLE = {
    status: 'idle' as const,
    total: 0,
    done: 0,
    created: 0,
    current: '',
    error: '',
};

describe('SeriesResolveBar', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('idle 状態で実行ボタンと Gemma 補助チェックボックスが表示される', async () => {
        mockedGet.mockResolvedValue(IDLE);
        const { getByText, getByLabelText } = render(
            <SeriesResolveBar source="generated" onComplete={vi.fn()} />,
        );
        expect(getByText('シリーズ判定実行')).toBeInTheDocument();
        expect(getByLabelText(/Gemma 補助も併用/)).toBeInTheDocument();
        expect((getByLabelText(/Gemma 補助も併用/) as HTMLInputElement).checked).toBe(false);
    });

    it('ボタンクリックで POST /api/series/resolve が呼ばれる（既定は use_gemma=false）', async () => {
        mockedGet.mockResolvedValue(IDLE);
        mockedPost.mockResolvedValue(undefined);

        const { getByText } = render(<SeriesResolveBar source="generated" onComplete={vi.fn()} />);

        await act(async () => {
            fireEvent.click(getByText('シリーズ判定実行'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() => expect(mockedPost).toHaveBeenCalled());
        expect(mockedPost).toHaveBeenCalledWith('/api/series/resolve', null, {
            params: { source: 'generated', use_gemma: false },
        });
    });

    it('Gemma 補助チェック後にボタンを押すと use_gemma=true で送られる', async () => {
        mockedGet.mockResolvedValue(IDLE);
        mockedPost.mockResolvedValue(undefined);

        const { getByText, getByLabelText } = render(
            <SeriesResolveBar source="generated" onComplete={vi.fn()} />,
        );

        fireEvent.click(getByLabelText(/Gemma 補助も併用/));

        await act(async () => {
            fireEvent.click(getByText('シリーズ判定実行'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() => expect(mockedPost.mock.calls[0][2].params.use_gemma).toBe(true));
    });

    it('running 状態で進捗バーが表示され、実行ボタンは消える', async () => {
        mockedGet.mockResolvedValue({
            ...IDLE,
            status: 'running',
            total: 50,
            done: 12,
            current: 'x.pdf',
        });

        const { queryByText, getByText } = render(
            <SeriesResolveBar source="generated" onComplete={vi.fn()} />,
        );

        await waitFor(() => expect(getByText(/12 \/ 50 件/)).toBeInTheDocument());
        expect(queryByText('シリーズ判定実行')).toBeNull();
    });

    it('done 状態で完了メッセージ "{created} シリーズを作成" が表示される', async () => {
        mockedGet.mockResolvedValue({ ...IDLE, status: 'done', created: 7 });

        const { getByText } = render(<SeriesResolveBar source="generated" onComplete={vi.fn()} />);

        await waitFor(() => expect(getByText(/完了 — 7 シリーズを作成/)).toBeInTheDocument());
    });

    it('error 状態でエラーメッセージが表示される', async () => {
        mockedGet.mockResolvedValue({ ...IDLE, status: 'error', error: '判定失敗' });

        const { getByText } = render(<SeriesResolveBar source="generated" onComplete={vi.fn()} />);

        await waitFor(() => expect(getByText(/エラー: 判定失敗/)).toBeInTheDocument());
    });
});
