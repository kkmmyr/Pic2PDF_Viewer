import apiClient from '@/config/api_client';
import { API_ENDPOINTS } from '@/config/api';

import type {
    OcrGroundTruthListResponse,
    OcrPageType,
    OcrQaRunDetail,
    OcrQaRunListResponse,
} from './types';

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
): Promise<unknown> {
    return apiClient.patch(API_ENDPOINTS.OCR_QA_PAGE(runId, pageNo), {
        state,
        note,
        page_type: pageType,
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
        state: 'draft' | 'verified';
        note: string | null;
    },
): Promise<OcrGroundTruthListResponse> {
    return apiClient.patch<unknown, OcrGroundTruthListResponse>(
        API_ENDPOINTS.OCR_GROUND_TRUTH_ENTRY(entryId),
        input,
    );
}
