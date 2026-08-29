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

export const ENGINE_LABELS: Record<OcrSelectedEngine, string> = {
    primary: 'Surya候補',
    external: 'yomitoku候補',
    codex: 'Codex確認済み補正',
};

const QUALITY_FLAG_LABELS: Record<string, string> = {
    candidate_content_conflict: '空本文と長文候補が矛盾',
    page_type_text_conflict: 'ページ種別と本文量が矛盾',
    cross_engine_disagreement: 'OCR候補が不一致',
    external_crosscheck_unavailable: 'yomitoku照合を採用不可',
    unselected_external_candidate_more_complete: 'yomitoku候補の方が大幅に長い',
    external_ocr_low_confidence: 'yomitoku信頼度不足',
    external_text_repetition: 'yomitoku候補に反復',
    primary_text_repetition: 'Surya候補に反復',
    selected_text_repetition: '採用候補に反復',
    non_text_page: '画像ページ判定',
    low_ink_coverage: '文字領域の検出不足',
    named_entity_candidate_disagreement: '固有名詞候補が不一致',
    ui_overlay_text_detected: '画面UI文字の混入疑い',
    sample_content_boundary: '試し読み境界',
    sample_content_excluded: '試し読み範囲',
    cross_engine_consensus: 'OCR候補が概ね一致',
};

export function qualityFlagLabel(flag: string): string {
    return QUALITY_FLAG_LABELS[flag] ?? flag;
}

export function compactTextLength(text: string): number {
    return text.replace(/\s/g, '').length;
}

export function qaDecisionLabel(qaState: string, selectedEngine: OcrSelectedEngine): string {
    if (qaState === 'approved') return selectedEngine === 'codex' ? '修正' : 'OK';
    if (qaState === 'rejected') return '保留';
    if (qaState === 'required') return '未確認';
    return qaState;
}

export function formatDurationMs(durationMs: number | null | undefined): string {
    if (durationMs === null || durationMs === undefined) return '未記録';
    if (durationMs < 1000) return `${durationMs} ms`;
    return `${(durationMs / 1000).toFixed(2)} 秒`;
}

export function runtimeManifestLabel(manifest: Record<string, unknown>): string {
    const packages = manifest.package_versions;
    const device = manifest.device;
    const yomitoku =
        packages && typeof packages === 'object' && 'yomitoku' in packages
            ? String(packages.yomitoku)
            : '不明';
    const backend =
        device && typeof device === 'object' && 'backend' in device
            ? String(device.backend)
            : '不明';
    return `${String(manifest.platform ?? '実行環境不明')} / ${backend} / YomiToku ${yomitoku}`;
}
