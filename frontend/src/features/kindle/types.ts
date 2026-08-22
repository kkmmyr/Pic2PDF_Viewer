import type { components } from '@/types/api';

export type KindleCatalogBook = components['schemas']['KindleCatalogBookOut'];
export type KindleCatalogBooksResponse = components['schemas']['KindleCatalogBooksResponse'];
export type KindleCatalogStats = components['schemas']['KindleCatalogStatsResponse'];
export type KindleCatalogSourceStatus = components['schemas']['KindleCatalogSourceStatusResponse'];
export type KindleMigrationPreview = components['schemas']['KindleMigrationPreviewResponse'];
export type KindleMigrationCommit = components['schemas']['KindleMigrationCommitResponse'];
export type KindleUnlinkedBook = components['schemas']['KindleUnlinkedBookOut'];
export type KindleUnlinkedBooksResponse = components['schemas']['KindleUnlinkedBooksResponse'];
export type KindleLinkCandidate = components['schemas']['KindleLinkCandidateOut'];
export type KindleLinkCandidatesResponse = components['schemas']['KindleLinkCandidatesResponse'];
export type KindleLinkResponse = components['schemas']['KindleLinkResponse'];
export type KindleOrdersImport = components['schemas']['KindleOrdersImportResponse'];
export type KindleImportRun = components['schemas']['KindleImportRunOut'];
export type KindleImportRunsResponse = components['schemas']['KindleImportRunsResponse'];
export type KindleCaptureJob = components['schemas']['KindleCaptureJobOut'];
export type KindleCaptureJobsResponse = components['schemas']['KindleCaptureJobsResponse'];
export type KindleCaptureQualityWarning = components['schemas']['KindleCaptureQualityWarningOut'];
export type KindleCaptureQualityWarningsResponse =
    components['schemas']['KindleCaptureQualityWarningsResponse'];
export type KindleCaptureQualityWarningReadRequest =
    components['schemas']['CaptureQualityWarningReadRequest'];
export type KindleLinkRequest = components['schemas']['LinkRequest'];
export type KindleCaptureJobCreateRequest = components['schemas']['CaptureJobCreateRequest'];
export type KindleMigrationCommitRequest = components['schemas']['MigrationCommitRequest'];

export type KindleBookType = 'comic' | 'novel' | 'other' | 'unknown' | '';
export type KindleOwnership =
    'purchased' | 'borrowed_active' | 'borrowed_ended' | 'returned' | 'unknown' | '';
export type KindleCaptureState =
    'not_captured' | 'captured' | 'multiple_links' | 'capture_pending' | '';
export type KindleCaptureWarningStatus = 'unread' | 'read' | 'all';

export interface KindleCatalogFilters {
    q: string;
    bookType: KindleBookType;
    ownership: KindleOwnership;
    captureState: KindleCaptureState;
    page: number;
    pageSize: number;
}
