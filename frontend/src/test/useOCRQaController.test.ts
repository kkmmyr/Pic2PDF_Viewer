import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OcrQaRunDetail, OcrQaRunListResponse } from '@/features/ocr/types';
import { useOCRQaController } from '@/features/ocr/useOCRQaController';
import { createQueryWrapper } from '@/test/queryTestUtils';

const fetchOcrQaRuns = vi.fn();
const fetchOcrQaRun = vi.fn();

vi.mock('@/features/ocr/api', () => ({
    fetchOcrQaRuns: () => fetchOcrQaRuns(),
    fetchOcrQaRun: (runId: number) => fetchOcrQaRun(runId),
    reviewOcrQaPage: vi.fn(),
    classifyOcrQaPages: vi.fn(),
    approveOcrQaRun: vi.fn(),
}));

const runList: OcrQaRunListResponse = {
    runs: [
        {
            id: 7,
            book_name: 'QA対象書籍',
            engine: 'surya2',
            model: 'model-sha',
            source_page_count: 1,
            state: 'awaiting_qa',
            qa_state: 'pending',
            required_pages: 1,
            approved_pages: 0,
            rejected_pages: 0,
            started_at: null,
        },
    ],
};

const runDetail: OcrQaRunDetail = {
    ...runList.runs[0],
    qa_reviewer: null,
    qa_reviewed_at: null,
    qa_note: null,
    pages: [
        {
            page_no: 1,
            state: 'passed',
            qa_state: 'required',
            full_text: '本文',
            char_count: 2,
            quality_flags: [],
            ink_coverage: 1,
            attempt_count: 1,
            error_message: null,
            qa_note: '確認メモ',
            reviewed_at: null,
            page_type: 'narrative',
            layout_type: 'normal_prose',
            primary_text: '本文',
            external_text: '',
            selected_engine: 'primary',
            corrected_text: null,
            index_eligible: true,
            image_url: '/image',
        },
    ],
};

describe('useOCRQaController', () => {
    beforeEach(() => {
        fetchOcrQaRuns.mockReset();
        fetchOcrQaRun.mockReset();
        fetchOcrQaRuns.mockResolvedValue(runList);
        fetchOcrQaRun.mockResolvedValue(runDetail);
    });

    it('selects the first awaiting run and synchronizes its required page review state', async () => {
        const { result } = renderHook(() => useOCRQaController(), {
            wrapper: createQueryWrapper(),
        });

        await waitFor(() => expect(result.current.selectedRunId).toBe(7));
        await waitFor(() => expect(result.current.selectedPageNo).toBe(1));

        expect(fetchOcrQaRun).toHaveBeenCalledWith(7);
        expect(result.current.selectedPage?.primary_text).toBe('本文');
        expect(result.current.pageType).toBe('narrative');
        expect(result.current.layoutType).toBe('normal_prose');
        expect(result.current.note).toBe('確認メモ');
        expect(result.current.canApproveRun).toBe(false);
    });
});
