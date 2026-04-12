import type { PdfFile, LibrarySource } from '../../types';
import {
    LibraryHeader,
    FolderGrid,
    PdfGrid,
    MoveDialog,
} from '../reader';

interface LibraryPanelProps {
    pdfs: PdfFile[];
    directories: string[];
    currentPath: string;
    currentSource: LibrarySource;
    // 選択モード
    isSelectionMode: boolean;
    selectedItems: Set<string>;
    // 移動ダイアログ
    isMoveDialogOpen: boolean;
    // コールバック
    onPdfClick: (name: string) => void;
    onFolderClick: (name: string) => void;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onToggleSelect: (item: string) => void;
    onCreateFolder: () => void;
    onMoveSelected: () => void;
    onCloseMoveDialog: () => void;
    onMoveItems: (destination: string) => Promise<void>;
}

/**
 * ライブラリ一覧ビュー。
 * フォルダ/PDF グリッド・ヘッダー・移動ダイアログをまとめて管理する。
 */
export function LibraryPanel({
    pdfs,
    directories,
    currentPath,
    currentSource,
    isSelectionMode,
    selectedItems,
    isMoveDialogOpen,
    onPdfClick,
    onFolderClick,
    onUpClick,
    onSourceChange,
    onToggleSelectionMode,
    onToggleSelect,
    onCreateFolder,
    onMoveSelected,
    onCloseMoveDialog,
    onMoveItems,
}: LibraryPanelProps) {
    return (
        <>
            <LibraryHeader
                currentPath={currentPath}
                currentSource={currentSource}
                isSelectionMode={isSelectionMode}
                selectedCount={selectedItems.size}
                onUpClick={onUpClick}
                onSourceChange={onSourceChange}
                onToggleSelectionMode={onToggleSelectionMode}
                onCreateFolder={onCreateFolder}
                onMoveSelected={onMoveSelected}
            />

            <MoveDialog
                open={isMoveDialogOpen}
                onClose={onCloseMoveDialog}
                onMove={onMoveItems}
                currentSource={currentSource}
                sourcePath={currentPath}
            />

            <div className="flex-1 bg-gray-100 overflow-auto">
                <div className="w-full h-full p-6 overflow-y-auto">
                    <FolderGrid
                        directories={directories}
                        onFolderClick={onFolderClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                    />
                    <PdfGrid
                        pdfs={pdfs}
                        onPdfClick={onPdfClick}
                        isSelectionMode={isSelectionMode}
                        selectedItems={selectedItems}
                        onToggleSelect={onToggleSelect}
                    />
                </div>
            </div>
        </>
    );
}
