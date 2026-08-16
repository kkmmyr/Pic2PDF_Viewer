import type { ReadState } from '@/types';
import { ReadStatePill } from '@/components/ui/read-state-pill';
import { PdfCardActionsMenu } from '@/components/library/PdfCardActionsMenu';

interface PdfCardActionButtonsProps {
    name: string;
    createdAtLabel: string;
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
    createdAtLabel,
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
        <div
            role="group"
            aria-label={`${name.replace(/\.pdf$/i, '')} の補助情報と操作`}
            className="flex w-full min-w-0 flex-nowrap items-center gap-1.5"
        >
            <span className="min-w-0 flex-1 truncate text-[11px] text-gray-500 dark:text-gray-400">
                {createdAtLabel}
            </span>
            {!isGroup && readState && <ReadStatePill state={readState} />}
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
