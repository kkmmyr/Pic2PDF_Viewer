import type { OcrLayoutType, OcrPageType, OcrSelectedEngine } from '@/features/ocr/types';

export const PAGE_TYPE_LABELS: Record<OcrPageType, string> = {
    unknown: '未分類',
    narrative: '本文',
    toc: '目次',
    illustration: '挿絵・表紙',
    colophon_or_ad: '奥付・広告',
};

export const LAYOUT_TYPE_LABELS: Record<OcrLayoutType, string> = {
    unknown: '未判定',
    normal_prose: '通常散文',
    full_width: '全幅本文・要約',
    mixed_illustration: '本文＋挿絵',
    structured: '構造化（目次・漢文等）',
    image_only: '画像のみ',
};

const LEGACY_ENGINE_LABELS: Record<OcrSelectedEngine, string> = {
    primary: 'Surya候補',
    external: 'yomitoku候補',
    codex: '人手確認済み補正',
};

const QWEN_DOTS_ENGINE_LABELS: Record<OcrSelectedEngine, string> = {
    primary: 'Qwen3.5候補',
    external: 'dots.mocr候補',
    codex: '人手確認済み補正',
};

export function getOcrEngineLabels(engine: string | undefined): Record<OcrSelectedEngine, string> {
    return engine === 'qwen35_dots_review_v1' ? QWEN_DOTS_ENGINE_LABELS : LEGACY_ENGINE_LABELS;
}

export function getSelectionReasonLabel(reason: string): string {
    const labels: Record<string, string> = {
        qwen_clean: 'Qwen候補に機械的な注意信号なし',
        dots_materially_more_complete: 'dots.mocr候補の方が明確に情報量が多い',
        dots_image_only_review_required: '両候補に本文なし（dots.mocrが画像のみと判定）',
        qwen_clean_dots_candidate_error: 'Qwen候補を採用（dots.mocr候補の解析に失敗）',
        qwen_flagged_dots_candidate_error: 'Qwen候補に注意信号あり・dots.mocr候補の解析に失敗',
        qwen_flagged_dots_empty_review_required: 'Qwen候補に注意信号あり・dots.mocr候補に本文なし',
    };
    return labels[reason] ?? `Qwen候補の注意信号によりdots.mocr候補を採用: ${reason}`;
}
