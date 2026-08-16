import { useEffect, useId, useRef, useState } from 'react';
import { BookCopy, Eye, EyeOff, MoreHorizontal, Pencil, RefreshCw } from 'lucide-react';

interface PdfCardActionsMenuProps {
    name: string;
    showHidden: boolean;
    onRename?: (name: string) => void;
    onRegenThumb?: (name: string) => void;
    onToggleHidden?: (name: string) => void;
    onEditSeries?: (name: string) => void;
}

interface CardAction {
    label: string;
    icon: typeof Pencil;
    run: (name: string) => void;
}

export function PdfCardActionsMenu({
    name,
    showHidden,
    onRename,
    onRegenThumb,
    onToggleHidden,
    onEditSeries,
}: PdfCardActionsMenuProps) {
    const [open, setOpen] = useState(false);
    const panelId = useId();
    const rootRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const firstActionRef = useRef<HTMLButtonElement>(null);

    const actions: CardAction[] = [];
    if (onRename) actions.push({ label: '名前を変更', icon: Pencil, run: onRename });
    if (onRegenThumb)
        actions.push({ label: 'サムネイルを再生成', icon: RefreshCw, run: onRegenThumb });
    if (onToggleHidden) {
        actions.push({
            label: showHidden ? '再表示する' : '非表示にする',
            icon: showHidden ? Eye : EyeOff,
            run: onToggleHidden,
        });
    }
    if (onEditSeries) actions.push({ label: 'シリーズを編集', icon: BookCopy, run: onEditSeries });

    useEffect(() => {
        if (!open) return;
        firstActionRef.current?.focus();

        const closeOutside = (event: PointerEvent) => {
            if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
        };
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            setOpen(false);
            triggerRef.current?.focus();
        };
        document.addEventListener('pointerdown', closeOutside);
        document.addEventListener('keydown', closeOnEscape);
        return () => {
            document.removeEventListener('pointerdown', closeOutside);
            document.removeEventListener('keydown', closeOnEscape);
        };
    }, [open]);

    if (actions.length === 0) return null;

    return (
        <div ref={rootRef} className="relative">
            <button
                ref={triggerRef}
                type="button"
                className="flex h-11 w-11 items-center justify-center rounded-md text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white"
                aria-label={`${name.replace(/\.pdf$/i, '')} の操作を開く`}
                aria-expanded={open}
                aria-controls={panelId}
                title="書籍の操作"
                onClick={() => setOpen((current) => !current)}
            >
                <MoreHorizontal aria-hidden="true" className="h-5 w-5" />
            </button>
            {open && (
                <div
                    id={panelId}
                    aria-label={`${name.replace(/\.pdf$/i, '')} の操作`}
                    className="absolute bottom-12 right-0 z-card-badge w-52 overflow-hidden rounded-lg border border-gray-200 bg-white p-1 shadow-xl dark:border-gray-600 dark:bg-gray-800"
                >
                    {actions.map((action, index) => {
                        const Icon = action.icon;
                        return (
                            <button
                                key={action.label}
                                ref={index === 0 ? firstActionRef : undefined}
                                type="button"
                                className="flex min-h-11 w-full items-center gap-2 rounded-md px-3 text-left text-sm font-medium text-gray-700 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-500 dark:text-gray-200 dark:hover:bg-gray-700"
                                aria-label={`${name.replace(/\.pdf$/i, '')}の${action.label}`}
                                title={action.label}
                                onClick={() => {
                                    setOpen(false);
                                    action.run(name);
                                }}
                            >
                                <Icon aria-hidden="true" className="h-4 w-4" />
                                {action.label}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
