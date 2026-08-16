import {
    DndContext,
    PointerSensor,
    KeyboardSensor,
    useSensor,
    useSensors,
    closestCenter,
    type DragEndEvent,
} from '@dnd-kit/core';
import {
    SortableContext,
    rectSortingStrategy,
    arrayMove,
    sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import type { PdfFile, ReadState } from '@/types';
import { BookOpen, Loader2 } from 'lucide-react';
import { PdfCard, type PdfCardProps, type PdfCardBadge } from './PdfCard';
import { SortablePdfCard } from './SortablePdfCard';

const GRID_CLASS = 'grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4';
const SKELETON_VISIBILITY = [
    '',
    '',
    'hidden md:block',
    'hidden md:block',
    'hidden lg:block',
    'hidden lg:block',
];

interface PdfGridProps {
    pdfs: PdfFile[];
    onPdfClick: (pdfName: string) => void;
    isSelectionMode?: boolean;
    selectedItems?: Set<string>;
    onToggleSelect?: (name: string) => void;
    favorites?: Set<string>;
    onToggleFavorite?: (name: string) => void;
    onRename?: (name: string) => void;
    onRegenThumb?: (name: string) => void;
    /** 書籍名 → 作者名リスト のマップ（カード下部に表示） */
    getAuthors?: (name: string) => string[];
    /** 作者ラベルクリック時に絞り込みを行うコールバック */
    onAuthorClick?: (author: string) => void;
    /**
     * 集約カードのバッジ情報。null なら通常の書籍カード。
     * シリーズ・作者どちらの集約も同じ仕組みで扱う。
     */
    getBadge?: (name: string) => PdfCardBadge | null;
    /**
     * 集約カードをクリックしたときのハンドラ。指定されると onPdfClick より優先される。
     */
    onGroupClick?: (representativeName: string) => void;
    /** 「非表示にする」「再表示する」ボタンのハンドラ。 */
    onToggleHidden?: (name: string) => void;
    /** ゴミ箱モード（true なら Eye アイコン、false なら EyeOff アイコンを表示） */
    showHidden?: boolean;
    /** 「シリーズ編集」ボタンのハンドラ。指定されるとカード右下にアイコンが出る */
    onEditSeries?: (name: string) => void;
    /** 各書籍の読書状態を返す関数。返り値に応じて NEW / 📖 / ✓ バッジを表示 */
    getReadState?: (name: string) => ReadState;
    /**
     * DnD 並べ替えモード。`true` のとき各カードがドラッグ可能になり、
     * 並べ替え確定時に `onReorder(newOrder)` が呼ばれる。
     */
    dndEnabled?: boolean;
    /** DnD ドロップ時に呼ばれる。`newOrder` は並べ替え後の `pdf.name` 配列。 */
    onReorder?: (newOrder: string[]) => void;
    /** PDF 一覧の初回取得中。空状態と区別してスケルトンを表示する。 */
    isLoading?: boolean;
}

function LibraryLoadingState() {
    return (
        <div aria-busy="true">
            <h2 className="mb-4 text-lg font-semibold text-gray-700 dark:text-gray-300">書籍</h2>
            <div className={GRID_CLASS} aria-hidden="true">
                {SKELETON_VISIBILITY.map((visibility, index) => (
                    <div
                        key={index}
                        className={`${visibility} animate-pulse overflow-hidden rounded-lg border-2 border-transparent bg-white shadow-md dark:bg-gray-800`}
                    >
                        <div className="aspect-[3/4] bg-gray-200 dark:bg-gray-700" />
                        <div className="space-y-2 p-3">
                            <div className="h-4 w-4/5 rounded bg-gray-200 dark:bg-gray-700" />
                            <div className="h-3 w-2/5 rounded bg-gray-100 dark:bg-gray-700/70" />
                        </div>
                    </div>
                ))}
            </div>
            <div
                role="status"
                aria-live="polite"
                className="mt-6 flex flex-col items-center justify-center text-center"
            >
                <div className="flex items-center gap-2 font-medium text-gray-700 dark:text-gray-300">
                    <Loader2 className="h-5 w-5 animate-spin text-primary-500" />
                    ライブラリを読み込み中…
                </div>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    初回の読み込みには時間がかかる場合があります
                </p>
            </div>
        </div>
    );
}

function LibraryEmptyState() {
    return (
        <div>
            <h2 className="mb-4 text-lg font-semibold text-gray-700 dark:text-gray-300">書籍</h2>
            <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white/60 px-6 text-center dark:border-gray-700 dark:bg-gray-900/60">
                <BookOpen className="h-9 w-9 text-gray-400 dark:text-gray-500" />
                <p className="mt-3 font-medium text-gray-700 dark:text-gray-300">
                    書籍がありません
                </p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    取り込み画面から書籍を追加できます
                </p>
            </div>
        </div>
    );
}

/**
 * PDF一覧のグリッド表示コンポーネント。
 * - サムネイルは LazyThumbnail により Intersection Observer で遅延読み込み
 * - dark: クラスによるダークモード対応
 * - dndEnabled=true でドラッグ&ドロップ並べ替えに対応
 */
export function PdfGrid({
    pdfs,
    onPdfClick,
    isSelectionMode = false,
    selectedItems = new Set(),
    onToggleSelect,
    favorites = new Set(),
    onToggleFavorite,
    onRename,
    onRegenThumb,
    getAuthors,
    onAuthorClick,
    getBadge,
    onGroupClick,
    onToggleHidden,
    showHidden = false,
    onEditSeries,
    dndEnabled = false,
    onReorder,
    getReadState,
    isLoading = false,
}: PdfGridProps) {
    const sensors = useSensors(
        // 8px 以上ドラッグしないと開始しない（ボタンクリックの誤検知を防ぐ）
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    if (isLoading) return <LibraryLoadingState />;

    if (pdfs.length === 0) return <LibraryEmptyState />;

    const buildCardProps = (pdf: PdfFile): PdfCardProps => {
        const isFav = favorites.has(pdf.name);
        const isSelected = isSelectionMode && selectedItems.has(pdf.name);
        const badge = getBadge?.(pdf.name) ?? null;
        const isGroup = badge !== null && !!onGroupClick;
        return {
            pdf,
            isFav,
            isSelected,
            isGroup,
            badge,
            isSelectionMode,
            showHidden,
            readState: getReadState?.(pdf.name),
            onToggleSelect,
            onToggleFavorite,
            onPdfClick,
            onGroupClick,
            onRename,
            onRegenThumb,
            onToggleHidden,
            onEditSeries,
            getAuthors,
            onAuthorClick,
        };
    };

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id || !onReorder) return;
        const oldIndex = pdfs.findIndex((p) => p.name === active.id);
        const newIndex = pdfs.findIndex((p) => p.name === over.id);
        if (oldIndex < 0 || newIndex < 0) return;
        const reordered = arrayMove(pdfs, oldIndex, newIndex);
        onReorder(reordered.map((p) => p.name));
    };

    const useDnd = dndEnabled && !isSelectionMode;

    if (useDnd) {
        return (
            <div>
                <h2 className="mb-4 text-lg font-semibold text-gray-700 dark:text-gray-300">
                    書籍
                </h2>
                <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragEnd={handleDragEnd}
                >
                    <SortableContext items={pdfs.map((p) => p.name)} strategy={rectSortingStrategy}>
                        <div className={GRID_CLASS}>
                            {pdfs.map((pdf) => (
                                <SortablePdfCard key={pdf.name} {...buildCardProps(pdf)} />
                            ))}
                        </div>
                    </SortableContext>
                </DndContext>
            </div>
        );
    }

    return (
        <div>
            <h2 className="mb-4 text-lg font-semibold text-gray-700 dark:text-gray-300">書籍</h2>
            <div className={GRID_CLASS}>
                {pdfs.map((pdf) => (
                    <div key={pdf.name}>
                        <PdfCard {...buildCardProps(pdf)} />
                    </div>
                ))}
            </div>
        </div>
    );
}
