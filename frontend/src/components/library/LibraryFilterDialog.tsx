import { Eye, EyeOff, ListChecks } from 'lucide-react';
import type { LibrarySource, ReadState } from '@/types';
import type { GroupMode } from '@/hooks/library/useLibraryGrouping';
import { Button } from '@/components/ui/button';
import { Dialog, DialogBody, DialogCancelButton, DialogFooter } from '@/components/ui/dialog';
import { LibraryDetailFilters } from '@/components/library/LibraryDetailFilters';

type ReadStateFilter = '' | ReadState;

interface LibraryFilterDialogProps {
    open: boolean;
    activeFilterCount: number;
    authorFilter: string;
    allAuthors: string[];
    groupMode: GroupMode;
    readStateFilter: ReadStateFilter;
    showHidden: boolean;
    currentSource: LibrarySource;
    hideAuthorSelect: boolean;
    isSelectionMode: boolean;
    onAuthorFilterChange: (author: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
    onReadStateFilterChange: (value: ReadStateFilter) => void;
    onToggleShowHidden: () => void;
    onToggleSelectionMode: () => void;
    onClearFilters: () => void;
    onClose: () => void;
}

export function LibraryFilterDialog({
    open,
    activeFilterCount,
    authorFilter,
    allAuthors,
    groupMode,
    readStateFilter,
    showHidden,
    currentSource,
    hideAuthorSelect,
    isSelectionMode,
    onAuthorFilterChange,
    onGroupModeChange,
    onReadStateFilterChange,
    onToggleShowHidden,
    onToggleSelectionMode,
    onClearFilters,
    onClose,
}: LibraryFilterDialogProps) {
    return (
        <Dialog
            open={open}
            title="絞り込み"
            subtitle={activeFilterCount > 0 ? `${activeFilterCount}件の条件を適用中` : '条件なし'}
            maxWidth="md"
            className="max-h-[calc(100dvh-2rem)] overflow-hidden"
            onClose={onClose}
        >
            <DialogBody className="max-h-[calc(100dvh-12rem)] overflow-y-auto">
                <LibraryDetailFilters
                    authorFilter={authorFilter}
                    allAuthors={allAuthors}
                    groupMode={groupMode}
                    readStateFilter={readStateFilter}
                    hideAuthorSelect={hideAuthorSelect}
                    layout="stacked"
                    onAuthorFilterChange={onAuthorFilterChange}
                    onGroupModeChange={onGroupModeChange}
                    onReadStateFilterChange={onReadStateFilterChange}
                />

                <div className="mt-6 border-t border-gray-200 pt-5 dark:border-gray-700">
                    <p className="mb-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                        その他の操作
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2">
                        <Button
                            variant="secondary"
                            active={showHidden}
                            className="min-h-11 justify-start px-4"
                            aria-pressed={showHidden}
                            onClick={onToggleShowHidden}
                        >
                            {showHidden ? (
                                <Eye className="h-4 w-4" />
                            ) : (
                                <EyeOff className="h-4 w-4" />
                            )}
                            {showHidden ? '通常の書籍を表示' : '非表示の書籍を表示'}
                        </Button>
                        <Button
                            variant="secondary"
                            className="min-h-11 justify-start px-4"
                            onClick={() => {
                                onToggleSelectionMode();
                                onClose();
                            }}
                        >
                            <ListChecks className="h-4 w-4" />
                            {isSelectionMode ? '選択を終了' : '書籍を選択'}
                        </Button>
                    </div>
                    {currentSource === 'novel' && (
                        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                            小説ライブラリの詳細管理は「小説 › 管理」から行えます。
                        </p>
                    )}
                </div>
            </DialogBody>
            <DialogFooter>
                <Button
                    variant="secondary"
                    disabled={activeFilterCount === 0}
                    className="mr-auto min-h-11 px-4"
                    onClick={onClearFilters}
                >
                    条件をクリア
                </Button>
                <DialogCancelButton onClick={onClose}>閉じる</DialogCancelButton>
            </DialogFooter>
        </Dialog>
    );
}
