import { describe, expect, it } from 'vitest';

import {
    compactTextLength,
    formatDurationMs,
    qaDecisionLabel,
    qualityFlagLabel,
    runtimeManifestLabel,
} from '@/features/ocr/ocrQaPresentation';

describe('OCRQaPanel presentation helpers', () => {
    it('translates operational QA decisions', () => {
        expect(qaDecisionLabel('required', 'primary')).toBe('未確認');
        expect(qaDecisionLabel('approved', 'primary')).toBe('OK');
        expect(qaDecisionLabel('approved', 'codex')).toBe('修正');
        expect(qaDecisionLabel('rejected', 'external')).toBe('保留');
    });

    it('shows Japanese review reasons and preserves unknown flags', () => {
        expect(qualityFlagLabel('candidate_content_conflict')).toBe('空本文と長文候補が矛盾');
        expect(qualityFlagLabel('future_flag')).toBe('future_flag');
    });

    it('counts candidate characters without layout whitespace', () => {
        expect(compactTextLength('縦 書き\n本文')).toBe(5);
    });

    it('formats persisted phase timing and runtime provenance', () => {
        expect(formatDurationMs(1250)).toBe('1.25 秒');
        expect(formatDurationMs(null)).toBe('未記録');
        expect(
            runtimeManifestLabel({
                platform: 'Windows-11',
                device: { backend: 'cuda' },
                package_versions: { yomitoku: '0.12.0' },
            }),
        ).toBe('Windows-11 / cuda / YomiToku 0.12.0');
    });
});
