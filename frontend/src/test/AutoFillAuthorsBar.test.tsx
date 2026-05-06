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
import { AutoFillAuthorsBar } from '../components/viewer/AutoFillAuthorsBar';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('AutoFillAuthorsBar', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    it('idle 状態でメインボタンと mode ラジオが表示される', async () => {
        mockedGet.mockResolvedValue({
            status: 'idle',
            total: 0,
            done: 0,
            skipped: 0,
            current: '',
            results: [],
            error: '',
        });
        const { getByText, getByLabelText } = render(
            <AutoFillAuthorsBar source="generated" onComplete={vi.fn()} />,
        );

        expect(getByText('サークル名自動登録')).toBeInTheDocument();
        expect(getByLabelText('未登録のみ')).toBeInTheDocument();
        expect(getByLabelText('作者不明のみ')).toBeInTheDocument();
        expect(getByLabelText('全件上書き')).toBeInTheDocument();

        // 既定では「作者不明のみ」が checked
        expect((getByLabelText('作者不明のみ') as HTMLInputElement).checked).toBe(true);
    });

    it('ボタンクリックで POST /api/meta/auto-fill が呼ばれ、選択中 mode が params に乗る', async () => {
        mockedGet.mockResolvedValue({
            status: 'idle',
            total: 0,
            done: 0,
            skipped: 0,
            current: '',
            results: [],
            error: '',
        });
        mockedPost.mockResolvedValue(undefined);

        const { getByText, getByLabelText } = render(
            <AutoFillAuthorsBar source="generated" onComplete={vi.fn()} />,
        );

        // mode を「全件上書き」に変更
        fireEvent.click(getByLabelText('全件上書き'));

        await act(async () => {
            fireEvent.click(getByText('サークル名自動登録'));
            await Promise.resolve();
            await Promise.resolve();
        });

        await waitFor(() => expect(mockedPost).toHaveBeenCalled());
        expect(mockedPost).toHaveBeenCalledWith('/api/meta/auto-fill', null, {
            params: { source: 'generated', mode: 'overwrite_all' },
        });
    });

    it('running 状態では進捗バーが表示され、メインボタンは消える', async () => {
        mockedGet.mockResolvedValue({
            status: 'running',
            total: 100,
            done: 30,
            skipped: 0,
            current: 'book.pdf',
            results: [],
            error: '',
        });

        const { queryByText, getByText } = render(
            <AutoFillAuthorsBar source="generated" onComplete={vi.fn()} />,
        );

        await waitFor(() => expect(getByText(/30 \/ 100 件/)).toBeInTheDocument());
        // 起動ボタンは消える
        expect(queryByText('サークル名自動登録')).toBeNull();
        // 現在処理中ファイル名が含まれる
        expect(getByText(/book\.pdf/)).toBeInTheDocument();
    });

    it('done 状態で完了メッセージが表示される', async () => {
        mockedGet.mockResolvedValue({
            status: 'done',
            total: 50,
            done: 48,
            skipped: 2,
            current: '',
            results: [],
            error: '',
        });

        const { getByText } = render(
            <AutoFillAuthorsBar source="generated" onComplete={vi.fn()} />,
        );

        await waitFor(() =>
            expect(getByText(/完了 — 48 件登録、2 件スキップ/)).toBeInTheDocument(),
        );
    });

    it('error 状態でエラーメッセージが表示される', async () => {
        mockedGet.mockResolvedValue({
            status: 'error',
            total: 0,
            done: 0,
            skipped: 0,
            current: '',
            results: [],
            error: 'Ollama 起動失敗',
        });

        const { getByText } = render(
            <AutoFillAuthorsBar source="generated" onComplete={vi.fn()} />,
        );

        await waitFor(() => expect(getByText(/エラー: Ollama 起動失敗/)).toBeInTheDocument());
    });
});
