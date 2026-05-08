import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../config/api_client', () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from '../config/api_client';
import { UnresolvedSeriesDialog } from '../components/viewer/UnresolvedSeriesDialog';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('UnresolvedSeriesDialog', () => {
    beforeEach(() => {
        mockedGet.mockReset();
        mockedPost.mockReset();
    });

    const sampleCandidates = {
        candidates: [
            {
                reason: 'short_prefix',
                score: 0.75,
                common_prefix: 'ABC',
                books: [
                    { path: '', name: 'ABC1.pdf', title: 'ABC1' },
                    { path: '', name: 'ABC2.pdf', title: 'ABC2' },
                ],
            },
        ],
    };

    it('open=true 時に refresh が走り候補が表示される', async () => {
        mockedGet.mockResolvedValue(sampleCandidates);
        const { findByText } = render(
            <UnresolvedSeriesDialog
                open
                source="generated"
                onClose={vi.fn()}
                onComplete={vi.fn()}
            />,
        );
        expect(await findByText('プレフィックスが短い')).toBeInTheDocument();
        expect(await findByText('ABC1')).toBeInTheDocument();
        expect(await findByText('ABC2')).toBeInTheDocument();
    });

    it('「シリーズ化」クリックで POST /api/series/assign が呼ばれる', async () => {
        mockedGet.mockResolvedValue(sampleCandidates);
        mockedPost.mockResolvedValue({});
        const onComplete = vi.fn();
        const { findByText } = render(
            <UnresolvedSeriesDialog
                open
                source="generated"
                onClose={vi.fn()}
                onComplete={onComplete}
            />,
        );
        const button = await findByText('シリーズ化');
        fireEvent.click(button);
        await waitFor(() => {
            expect(mockedPost).toHaveBeenCalledWith('/api/series/assign', {
                path: '',
                names: ['ABC1.pdf', 'ABC2.pdf'],
                title: 'ABC',
                index: [1, 2],
                source: 'generated',
            });
        });
        await waitFor(() => expect(onComplete).toHaveBeenCalled());
    });

    it('候補 0 件で「未分類の候補はありません」を表示', async () => {
        mockedGet.mockResolvedValue({ candidates: [] });
        const { findByText } = render(
            <UnresolvedSeriesDialog
                open
                source="generated"
                onClose={vi.fn()}
                onComplete={vi.fn()}
            />,
        );
        expect(await findByText('未分類の候補はありません。')).toBeInTheDocument();
    });

    it('GET 失敗時にエラー表示', async () => {
        mockedGet.mockRejectedValue(new Error('network'));
        const { findByText } = render(
            <UnresolvedSeriesDialog
                open
                source="generated"
                onClose={vi.fn()}
                onComplete={vi.fn()}
            />,
        );
        expect(await findByText('network')).toBeInTheDocument();
    });

    it('タイトル空文字でシリーズ化を押すとエラーが行ごとに表示され API は呼ばれない', async () => {
        mockedGet.mockResolvedValue(sampleCandidates);
        const { findByText, findByDisplayValue } = render(
            <UnresolvedSeriesDialog
                open
                source="generated"
                onClose={vi.fn()}
                onComplete={vi.fn()}
            />,
        );
        const titleInput = (await findByDisplayValue('ABC')) as HTMLInputElement;
        fireEvent.change(titleInput, { target: { value: '   ' } });
        const button = await findByText('シリーズ化');
        fireEvent.click(button);
        expect(await findByText('シリーズタイトルを入力してください。')).toBeInTheDocument();
        expect(mockedPost).not.toHaveBeenCalled();
    });
});
