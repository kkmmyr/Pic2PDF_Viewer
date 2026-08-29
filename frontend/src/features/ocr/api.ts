import apiClient from '@/config/api_client';
import { API_ENDPOINTS } from '@/config/api';

import type {
    OcrGroundTruthListResponse,
    OcrLayoutType,
    OcrPageType,
    OcrQaRunDetail,
    OcrQaRunListResponse,
    OcrRunResponse,
    OcrSelectedEngine,
    OcrStatusResponse,
    OcrStopResponse,
} from './types';

export function fetchOcrStatus(): Promise<OcrStatusResponse> {
    return apiClient.get<unknown, OcrStatusResponse>(API_ENDPOINTS.OCR_STATUS);
}

export function startOcr(targetDir?: string): Promise<OcrRunResponse> {
    if (!targetDir) {
        return apiClient.post<unknown, OcrRunResponse>(API_ENDPOINTS.OCR_RUN);
    }
    return apiClient.post<unknown, OcrRunResponse>(API_ENDPOINTS.OCR_RUN, undefined, {
        params: { target_dir: targetDir },
    });
}

export function stopOcr(): Promise<OcrStopResponse> {
    return apiClient.post<unknown, OcrStopResponse>(API_ENDPOINTS.OCR_STOP);
}

export function fetchOcrQaRuns(): Promise<OcrQaRunListResponse> {
    return apiClient.get<unknown, OcrQaRunListResponse>(API_ENDPOINTS.OCR_QA_RUNS);
}

export function fetchOcrQaRun(runId: number): Promise<OcrQaRunDetail> {
    return apiClient.get<unknown, OcrQaRunDetail>(API_ENDPOINTS.OCR_QA_RUN(runId));
}

export function reviewOcrQaPage(
    runId: number,
    pageNo: number,
    state: 'approved' | 'rejected',
    note: string | null,
    pageType: OcrPageType,
    layoutType: OcrLayoutType,
    selectedEngine: OcrSelectedEngine,
    correctedText: string | null,
    reviewStartedAt: string | null,
    reviewDurationMs: number | null,
    correctionDurationMs: number | null,
): Promise<unknown> {
    return apiClient.patch(API_ENDPOINTS.OCR_QA_PAGE(runId, pageNo), {
        state,
        note,
        page_type: pageType,
        layout_type: layoutType,
        selected_engine: selectedEngine,
        corrected_text: correctedText,
        review_started_at: reviewStartedAt,
        review_duration_ms: reviewDurationMs,
        correction_duration_ms: correctionDurationMs,
    });
}

export function classifyOcrQaPages(runId: number): Promise<unknown> {
    return apiClient.post(API_ENDPOINTS.OCR_QA_CLASSIFY(runId));
}

export function approveOcrQaRun(
    runId: number,
    reviewer: string,
    note: string | null,
): Promise<unknown> {
    return apiClient.post(API_ENDPOINTS.OCR_QA_APPROVE(runId), { reviewer, note });
}

export function fetchOcrGroundTruth(): Promise<OcrGroundTruthListResponse> {
    return apiClient.get<unknown, OcrGroundTruthListResponse>(API_ENDPOINTS.OCR_GROUND_TRUTH);
}

export function updateOcrGroundTruth(
    entryId: number,
    input: {
        reference_text: string;
        page_type: OcrPageType;
        layout_type: OcrLayoutType;
        state: 'draft' | 'verified';
        note: string | null;
    },
): Promise<OcrGroundTruthListResponse> {
    return apiClient.patch<unknown, OcrGroundTruthListResponse>(
        API_ENDPOINTS.OCR_GROUND_TRUTH_ENTRY(entryId),
        input,
    );
}
