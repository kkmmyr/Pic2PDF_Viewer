import type { components } from '@/types/api';

export type OcrStatusResponse = components['schemas']['StatusResponse'];
export type OcrRunResponse = components['schemas']['OcrRunResponse'];
export type OcrStopResponse = components['schemas']['OcrStopResponse'];
export type OcrQaRunSummary = components['schemas']['OcrQaRunSummary'];
export type OcrQaPage = components['schemas']['OcrQaPageOut'];
export type OcrQaRunDetail = components['schemas']['OcrQaRunDetail'];
export type OcrQaRunListResponse = components['schemas']['OcrQaRunListResponse'];
export type OcrGroundTruthEntry = components['schemas']['OcrGroundTruthEntryOut'];
export type OcrGroundTruthListResponse = components['schemas']['OcrGroundTruthListResponse'];
export type OcrPageType = OcrQaPage['page_type'];
export type OcrLayoutType = OcrQaPage['layout_type'];
export type OcrSelectedEngine = OcrQaPage['selected_engine'];
