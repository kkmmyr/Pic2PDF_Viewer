import { getSelectionReasonLabel } from '@/features/ocr/ocrQaLabels';

export function OCRQaSelectionReason({ reason }: { reason: string | null }) {
    if (!reason) return null;
    return (
        <p className="mb-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200">
            初期候補の選択理由: {getSelectionReasonLabel(reason)}
            <span className="ml-1 font-mono text-[11px] opacity-75">({reason})</span>
        </p>
    );
}
