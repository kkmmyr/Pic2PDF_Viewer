import type { ReadState } from '@/types';
import { ReadStatePill } from '@/components/ui/read-state-pill';
import { PdfCardActionsMenu } from '@/components/library/PdfCardActionsMenu';

interface PdfCardActionButtonsProps {
    name: string;
    isSelectionMode: boolean;
    showHidden: boolean;
    isGroup: boolean;
    readState?: ReadState;
    onRename?: (name: string) => void;
    onRegenThumb?: (name: string) => void;
    onToggleHidden?: (name: string) => void;
    onEditSeries?: (name: string) => void;
}

export function PdfCardActionButtons({
    name,
    isSelectionMode,
    showHidden,
    isGroup,
    readState,
    onRename,
    onRegenThumb,
    onToggleHidden,
    onEditSeries,
}: PdfCardActionButtonsProps) {
    return (
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <div>{!isGroup && readState && <ReadStatePill state={readState} />}</div>
            {!isSelectionMode && (
                <PdfCardActionsMenu
                    name={name}
                    showHidden={showHidden}
                    onRename={onRename}
                    onRegenThumb={onRegenThumb}
                    onToggleHidden={onToggleHidden}
                    onEditSeries={onEditSeries}
                />
            )}
        </div>
    );
}
