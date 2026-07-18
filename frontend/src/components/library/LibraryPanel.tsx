import { LibraryPanelProvider, useLibraryPanelContext } from '@/contexts/LibraryPanelContext';
import { PdfGrid } from './PdfGrid';
import { LibraryHeader } from './LibraryHeader';
import { GenreFilterBar } from './GenreFilterBar';
import { LibraryDialogs } from './LibraryDialogs';
import { SeriesEditDialog } from './SeriesEditDialog';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';

interface LibraryPanelProps {
    onPdfClick: (name: string) => void;
    onUpClick: () => void;
}

export function LibraryPanel({ onPdfClick, onUpClick }: LibraryPanelProps) {
    return (
        <LibraryPanelProvider onPdfClick={onPdfClick} onUpClick={onUpClick}>
            <LibraryPanelContent />
        </LibraryPanelProvider>
    );
}

function LibraryPdfGrid() {
    const {
        displayPdfs,
        handlePdfClick,
        isSelectionMode,
        selectedItems,
        handleToggleSelect,
        contextualFavorites,
        handleTogglePin,
        authorFilter,
        seriesFilter,
        setAuthorFilter,
        setSeriesFilter,
        openRenameDialog,
        handleRegenThumb,
        grouped,
        getAuthors,
        currentPath,
        bulkActions,
        seriesEdit,
        showHidden,
        getReadState,
    } = useLibraryPanelContext();

    return (
        <PdfGrid
            pdfs={displayPdfs}
            onPdfClick={handlePdfClick}
            isSelectionMode={isSelectionMode}
            selectedItems={selectedItems}
            onToggleSelect={handleToggleSelect}
            favorites={contextualFavorites}
            onToggleFavorite={authorFilter || seriesFilter ? handleTogglePin : undefined}
            onRename={openRenameDialog}
            onRegenThumb={handleRegenThumb}
            getAuthors={(name) => getAuthors(currentPath, name)}
            onAuthorClick={setAuthorFilter}
            getBadge={(name) => grouped.badgeByRepresentativeName.get(name) ?? null}
            onGroupClick={(name) => {
                const badge = grouped.badgeByRepresentativeName.get(name);
                if (!badge) return;
                if (badge.kind === 'series') setSeriesFilter(badge.groupId);
                else setAuthorFilter(badge.groupId.split('\n')[0]);
            }}
            onToggleHidden={bulkActions.handleToggleHiddenOne}
            showHidden={showHidden}
            getReadState={(name) => getReadState(currentPath, name)}
            onEditSeries={seriesEdit.open}
            dndEnabled={!!seriesFilter}
            onReorder={bulkActions.handleSeriesReorder}
        />
    );
}

function LibraryPanelContent() {
    const { hasLibraryLoadError, retryLibraryData } = useLibraryPanelContext();

    return (
        <>
            <LibraryHeader />
            <LibraryDialogs />
            <GenreFilterBar />
            <div className="flex-1 bg-gray-100 dark:bg-gray-950 overflow-auto">
                <div className="w-full h-full p-6 overflow-y-auto">
                    {hasLibraryLoadError && (
                        <Alert variant="error" className="mb-4">
                            <div className="flex items-center justify-between gap-4">
                                <span>ライブラリ情報の取得に失敗しました。</span>
                                <Button size="sm" onClick={() => void retryLibraryData()}>
                                    再試行
                                </Button>
                            </div>
                        </Alert>
                    )}
                    <LibraryPdfGrid />
                </div>
            </div>
            <SeriesEditDialog />
        </>
    );
}
