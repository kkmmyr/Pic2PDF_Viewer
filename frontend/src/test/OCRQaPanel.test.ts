import { describe, expect, it } from 'vitest';

import { getOcrEngineLabels } from '@/features/ocr/OCRQaPanel';

describe('getOcrEngineLabels', () => {
    it('review-assisted engineをQwenとdotsとして表示する', () => {
        expect(getOcrEngineLabels('qwen35_dots_review_v1')).toEqual({
            primary: 'Qwen3.5候補',
            external: 'dots.mocr候補',
            codex: '人手確認済み補正',
        });
    });

    it('既存engineの表示名を維持する', () => {
        expect(getOcrEngineLabels('surya2')).toEqual({
            primary: 'Surya候補',
            external: 'yomitoku候補',
            codex: '人手確認済み補正',
        });
    });
});
