import type { components } from '@/types/api';

export type OcrQaRunSummary = components['schemas']['OcrQaRunSummary'];
export type OcrQaPage = components['schemas']['OcrQaPageOut'];
export type OcrQaRunDetail = components['schemas']['OcrQaRunDetail'];
export type OcrQaRunListResponse = components['schemas']['OcrQaRunListResponse'];
export type OcrGroundTruthEntry = components['schemas']['OcrGroundTruthEntryOut'];
export type OcrGroundTruthListResponse = components['schemas']['OcrGroundTruthListResponse'];
export type OcrPageType = OcrQaPage['page_type'];
