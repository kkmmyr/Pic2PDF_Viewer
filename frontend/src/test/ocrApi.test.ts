import { beforeEach, describe, expect, it, vi } from 'vitest';

import { API_ENDPOINTS } from '@/config/api';
import { reviewOcrQaPage } from '@/features/ocr/api';
import type { OcrQaActionResponse, OcrQaPageReviewRequest } from '@/features/ocr/types';

const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));

vi.mock('@/config/api_client', () => ({
    default: { patch },
}));

describe('reviewOcrQaPage', () => {
    beforeEach(() => {
        patch.mockReset();
    });

    it('null を含むQAレビューの全項目をAPIへそのまま渡し、型付き応答を返す', async () => {
        const response: OcrQaActionResponse = { status: 'updated', run_id: 7 };
        const request: OcrQaPageReviewRequest = {
            state: 'approved',
            note: null,
            page_type: 'narrative',
            layout_type: 'normal_prose',
            selected_engine: 'primary',
            corrected_text: null,
            review_started_at: '2026-09-05T01:02:03.000Z',
            review_duration_ms: 1234,
            correction_duration_ms: null,
        };
        patch.mockResolvedValue(response);

        await expect(reviewOcrQaPage(7, 3, request)).resolves.toEqual(response);
        expect(patch).toHaveBeenCalledWith(API_ENDPOINTS.OCR_QA_PAGE(7, 3), request);
    });

    it('未指定の任意項目を追加せずにAPIへ渡す', async () => {
        const request: OcrQaPageReviewRequest = {
            state: 'rejected',
            page_type: 'illustration',
            layout_type: 'image_only',
            selected_engine: 'external',
        };
        patch.mockResolvedValue({ status: 'updated', run_id: 8 });

        await reviewOcrQaPage(8, 4, request);

        expect(patch).toHaveBeenCalledWith(API_ENDPOINTS.OCR_QA_PAGE(8, 4), request);
        expect(Object.keys(patch.mock.calls[0][1])).toEqual([
            'state',
            'page_type',
            'layout_type',
            'selected_engine',
        ]);
    });
});
