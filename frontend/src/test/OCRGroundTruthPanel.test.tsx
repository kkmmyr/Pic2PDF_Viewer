import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OCRGroundTruthPanel } from '@/features/ocr/OCRGroundTruthPanel';
import type { OcrGroundTruthListResponse } from '@/features/ocr/types';

const fetchOcrGroundTruth = vi.fn();
const updateOcrGroundTruth = vi.fn();

vi.mock('@/features/ocr/api', () => ({
    fetchOcrGroundTruth: () => fetchOcrGroundTruth(),
    updateOcrGroundTruth: (...args: unknown[]) => updateOcrGroundTruth(...args),
}));

function renderPanel() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
        <QueryClientProvider client={queryClient}>
            <OCRGroundTruthPanel />
        </QueryClientProvider>,
    );
}

const corpus: OcrGroundTruthListResponse = {
    total_count: 1,
    verified_count: 0,
    total_edit_distance: 0,
    total_reference_chars: 0,
    aggregate_cer: null,
    metrics_by_page_type: [
        {
            page_type: 'unknown',
            total_count: 1,
            verified_count: 0,
            total_edit_distance: 0,
            total_reference_chars: 0,
            aggregate_cer: null,
        },
    ],
    entries: [
        {
            id: 1,
            run_id: 7,
            page_no: 4,
            image_sha256: 'hash',
            page_type: 'unknown',
            reference_text: '',
            state: 'draft',
            note: null,
            created_at: null,
            updated_at: null,
            verified_at: null,
            book_name: '評価対象書籍',
            ocr_text: 'OCR本文',
            edit_distance: null,
            reference_chars: null,
            cer: null,
            image_url: '/api/ocr/ground-truth/1/image',
        },
    ],
};

describe('OCRGroundTruthPanel', () => {
    it('未検証コーパスの件数と評価対象を表示する', async () => {
        fetchOcrGroundTruth.mockResolvedValue(corpus);
        renderPanel();

        expect(await screen.findByText('評価対象書籍')).toBeInTheDocument();
        expect(screen.getAllByText('検証済み 0 / 1')).toHaveLength(2);
        expect(screen.getAllByText('CER —')).toHaveLength(2);
        expect(screen.getByLabelText('ページ種別ごとのOCR品質')).toHaveTextContent('未分類');
        expect(screen.getByText('OCR本文')).toBeInTheDocument();
    });

    it('未分類または正解本文なしでは検証済みにできない', async () => {
        fetchOcrGroundTruth.mockResolvedValue(corpus);
        renderPanel();
        await screen.findByText('評価対象書籍');

        const verifyButton = screen.getByRole('button', { name: '検証済みにする' });
        expect(verifyButton).toBeDisabled();

        fireEvent.change(screen.getByLabelText('ページ種別'), {
            target: { value: 'narrative' },
        });
        expect(verifyButton).toBeDisabled();

        fireEvent.change(screen.getByLabelText('正解本文'), {
            target: { value: '正しい本文' },
        });
        await waitFor(() => expect(verifyButton).toBeEnabled());
    });
});
