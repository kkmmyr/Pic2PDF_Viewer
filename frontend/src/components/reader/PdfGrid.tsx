import { CheckSquare, Square, Star, Pencil, RefreshCw, Library, EyeOff, Eye, BookCopy, Users, GripVertical } from 'lucide-react';
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
    useSortable,
    sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { CSSProperties } from 'react';
import type { PdfFile } from '../../types';
import { LazyThumbnail } from './LazyThumbnail';

/** 集約カードのバッジ情報（PdfGrid から PdfFile.name で引く想定） */
export interface PdfCardBadge {
    /** 集約メンバー数 */
    count: number;
    /** 集約種別: シリーズ / 作者 */
    kind: 'series' | 'author';
    /** カードのタイトル表示に使う（例: "鬼滅の刃" / "diletta コレクション"） */
    displayTitle: string;
}

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
    /** 作者タグクリック時に絞り込みを行うコールバック */
    onAuthorClick?: (author: string) => void;
    /** 書籍名 → タグリスト のマップ */
    getTags?: (name: string) => string[];
    /** タグクリック時に絞り込みを行うコールバック */
    onTagClick?: (tag: string) => void;
    /**
     * 集約カードのバッジ情報。null なら通常の書籍カード。
     * シリーズ・作者どちらの集約も同じ仕組みで扱う。
     */
    getBadge?: (name: string) => PdfCardBadge | null;
    /**
     * 集約カードをクリックしたときのハンドラ。指定されると onPdfClick より優先される。
     * `kind` で分岐して、シリーズなら series_id でドリルダウン、作者なら作者名でドリルダウン等の挙動をする想定。
     */
    onGroupClick?: (representativeName: string) => void;
    /** 「非表示にする」「再表示する」ボタンのハンドラ。
     *  - showHidden=false（通常モード）の時は EyeOff アイコンで「非表示にする」
     *  - showHidden=true（ゴミ箱モード）の時は Eye アイコンで「再表示する」
     */
    onToggleHidden?: (name: string) => void;
    /** ゴミ箱モード（true なら Eye アイコン、false なら EyeOff アイコンを表示） */
    showHidden?: boolean;
    /** 「シリーズ編集」ボタンのハンドラ。指定されるとカード右下にアイコンが出る */
    onEditSeries?: (name: string) => void;
    /**
     * DnD 並べ替えモード。`true` のとき各カードがドラッグ可能になり、
     * 並べ替え確定時に `onReorder(newOrder)` が呼ばれる。
     * シリーズドリルダウン中など、序列が意味を持つ画面でだけ有効化する。
     */
    dndEnabled?: boolean;
    /** DnD ドロップ時に呼ばれる。`newOrder` は並べ替え後の `pdf.name` 配列。 */
    onReorder?: (newOrder: string[]) => void;
}

/** カード本体の共通レンダラ。DnD 有効時はドラッグハンドルを上書きで差し込む。 */
interface CardContentProps {
    pdf: PdfFile;
    isFav: boolean;
    isSelected: boolean;
    isGroup: boolean;
    badge: PdfCardBadge | null;
    isSelectionMode: boolean;
    showHidden: boolean;
    onToggleSelect?: (name: string) => void;
    onToggleFavorite?: (name: string) => void;
    onPdfClick: (name: string) => void;
    onGroupClick?: (name: string) => void;
    onRename?: (name: string) => void;
    onRegenThumb?: (name: string) => void;
    onToggleHidden?: (name: string) => void;
    onEditSeries?: (name: string) => void;
    getAuthors?: (name: string) => string[];
    onAuthorClick?: (author: string) => void;
    getTags?: (name: string) => string[];
    onTagClick?: (tag: string) => void;
    /** DnD: ドラッグハンドル要素（指定時はカード左上に表示） */
    dragHandle?: React.ReactNode;
}

function CardContent({
    pdf, isFav, isSelected, isGroup, badge, isSelectionMode, showHidden,
    onToggleSelect, onToggleFavorite, onPdfClick, onGroupClick,
    onRename, onRegenThumb, onToggleHidden, onEditSeries,
    getAuthors, onAuthorClick, getTags, onTagClick, dragHandle,
}: CardContentProps) {
    return (
        <div
            className={`rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow flex flex-col border-2 ${
                isSelected
                    ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20'
                    : isGroup
                        ? 'border-purple-300 dark:border-purple-700 bg-white dark:bg-gray-800'
                        : 'border-transparent bg-white dark:bg-gray-800'
            }`}
        >
            <div
                className="aspect-[3/4] relative cursor-pointer"
                onClick={() => {
                    if (isSelectionMode && onToggleSelect) {
                        onToggleSelect(pdf.name);
                    } else if (isGroup && onGroupClick) {
                        onGroupClick(pdf.name);
                    } else {
                        onPdfClick(pdf.name);
                    }
                }}
            >
                {/* ドラッグハンドル（DnD 有効時のみ） */}
                {dragHandle}

                {/* 選択チェックボックス */}
                {isSelectionMode && (
                    <div className="absolute top-2 right-2 z-10 bg-white dark:bg-gray-800 rounded-full">
                        {isSelected ? (
                            <CheckSquare className="w-6 h-6 text-amber-500 fill-white" />
                        ) : (
                            <Square className="w-6 h-6 text-gray-400 fill-white" />
                        )}
                    </div>
                )}

                {/* 集約バッジ（シリーズ巻数 / 作者の作品数） */}
                {isGroup && badge && (
                    <div className="absolute top-2 right-2 z-10 px-1.5 py-0.5 rounded-full bg-purple-600 text-white text-xs font-semibold flex items-center gap-1 shadow">
                        {badge.kind === 'series'
                            ? <Library className="w-3 h-3" />
                            : <Users className="w-3 h-3" />}
                        {badge.count} {badge.kind === 'series' ? '巻' : '冊'}
                    </div>
                )}

                {/* お気に入りボタン */}
                {!isSelectionMode && onToggleFavorite && (
                    <button
                        className="absolute top-2 left-2 z-10 p-1 rounded-full bg-white/80 dark:bg-gray-900/70 hover:bg-white dark:hover:bg-gray-900 transition-colors"
                        onClick={(e) => {
                            e.stopPropagation();
                            onToggleFavorite(pdf.name);
                        }}
                        title={isFav ? 'お気に入りを解除' : 'お気に入りに追加'}
                    >
                        <Star
                            className={`w-4 h-4 transition-colors ${
                                isFav
                                    ? 'text-amber-400 fill-amber-400'
                                    : 'text-gray-300 dark:text-gray-500 hover:text-amber-300'
                            }`}
                        />
                    </button>
                )}

                {/* 遅延読み込みサムネイル */}
                <LazyThumbnail src={pdf.thumbnail} alt={pdf.name} className="absolute inset-0" />
            </div>

            <div className={`p-3 flex-1 flex flex-col justify-between ${isSelected ? 'bg-amber-50 dark:bg-amber-900/20' : 'bg-white dark:bg-gray-800'}`}>
                <span
                    className={`font-medium text-sm line-clamp-2 ${isGroup ? 'text-purple-700 dark:text-purple-300' : 'text-gray-800 dark:text-gray-200'}`}
                    title={isGroup && badge ? badge.displayTitle : pdf.name}
                >
                    {isGroup && badge ? badge.displayTitle : pdf.name.replace('.pdf', '')}
                </span>
                {/* 作者名タグ */}
                {getAuthors && (() => {
                    const authors = getAuthors(pdf.name);
                    return authors.length > 0 ? (
                        <div className="mt-1 flex flex-wrap gap-1">
                            {authors.map((a, i) => (
                                <span
                                    key={i}
                                    className={`text-xs px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 truncate max-w-full ${onAuthorClick ? 'cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-800/50' : ''}`}
                                    onClick={onAuthorClick ? (e) => { e.stopPropagation(); onAuthorClick(a); } : undefined}
                                    title={onAuthorClick ? `"${a}" で絞り込む` : undefined}
                                >
                                    {a}
                                </span>
                            ))}
                        </div>
                    ) : null;
                })()}
                {/* タグ */}
                {getTags && (() => {
                    const tags = getTags(pdf.name);
                    return tags.length > 0 ? (
                        <div className="mt-1 flex flex-wrap gap-1">
                            {tags.map((t, i) => (
                                <span
                                    key={i}
                                    className={`text-xs px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 truncate max-w-full ${onTagClick ? 'cursor-pointer hover:bg-emerald-100 dark:hover:bg-emerald-800/50' : ''}`}
                                    onClick={onTagClick ? (e) => { e.stopPropagation(); onTagClick(t); } : undefined}
                                    title={onTagClick ? `"${t}" で絞り込む` : undefined}
                                >
                                    #{t}
                                </span>
                            ))}
                        </div>
                    ) : null;
                })()}
                <div className="mt-2 flex items-center justify-between">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                        {pdf.created_at
                            ? new Date(pdf.created_at * 1000).toLocaleDateString()
                            : ''}
                    </span>
                    <div className="flex items-center gap-1">
                        {!isSelectionMode && onRename && (
                            <button
                                onClick={(e) => { e.stopPropagation(); onRename(pdf.name); }}
                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                title="名前を変更"
                            >
                                <Pencil className="w-3 h-3" />
                            </button>
                        )}
                        {!isSelectionMode && onRegenThumb && (
                            <button
                                onClick={(e) => { e.stopPropagation(); onRegenThumb(pdf.name); }}
                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                title="サムネイルを再生成"
                            >
                                <RefreshCw className="w-3 h-3" />
                            </button>
                        )}
                        {!isSelectionMode && onToggleHidden && (
                            <button
                                onClick={(e) => { e.stopPropagation(); onToggleHidden(pdf.name); }}
                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors"
                                title={showHidden ? '再表示する' : '非表示にする'}
                            >
                                {showHidden
                                    ? <Eye className="w-3 h-3" />
                                    : <EyeOff className="w-3 h-3" />}
                            </button>
                        )}
                        {!isSelectionMode && onEditSeries && (
                            <button
                                onClick={(e) => { e.stopPropagation(); onEditSeries(pdf.name); }}
                                className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-300 dark:text-gray-600 hover:text-purple-500 dark:hover:text-purple-400 transition-colors"
                                title="シリーズを編集"
                            >
                                <BookCopy className="w-3 h-3" />
                            </button>
                        )}
                        {isFav && (
                            <Star className="w-3 h-3 text-amber-400 fill-amber-400 shrink-0" />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

/** DnD 有効時のラッパー。useSortable で transform / handle を提供する。 */
function SortableCard(props: CardContentProps) {
    const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
        id: props.pdf.name,
    });
    const style: CSSProperties = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 10 : 'auto',
    };
    // ドラッグハンドル単体に listeners を付け、カード本体のクリックは通常通り動かす。
    // setActivatorNodeRef でハンドルがドラッグ起点であることを明示する。
    const handle = (
        <button
            ref={setActivatorNodeRef}
            {...listeners}
            onClick={(e) => e.stopPropagation()}
            className="absolute top-2 left-2 z-20 p-1 rounded-full bg-white/90 dark:bg-gray-900/80 text-gray-500 dark:text-gray-300 hover:text-purple-600 dark:hover:text-purple-300 cursor-grab active:cursor-grabbing shadow"
            title="ドラッグして並べ替え"
            aria-label={`${props.pdf.name} をドラッグ`}
        >
            <GripVertical className="w-4 h-4" />
        </button>
    );
    return (
        <div ref={setNodeRef} style={style} {...attributes}>
            <CardContent {...props} dragHandle={handle} />
        </div>
    );
}

/**
 * PDF一覧のグリッド表示コンポーネント
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
    getTags,
    onTagClick,
    getBadge,
    onGroupClick,
    onToggleHidden,
    showHidden = false,
    onEditSeries,
    dndEnabled = false,
    onReorder,
}: PdfGridProps) {
    const sensors = useSensors(
        // 8px 以上ドラッグしないと開始しない（ボタンクリックの誤検知を防ぐ）
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    if (pdfs.length === 0) {
        return (
            <div>
                <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">PDFs</h2>
                <p className="text-gray-500 dark:text-gray-400">No PDFs found.</p>
            </div>
        );
    }

    const buildCardProps = (pdf: PdfFile): CardContentProps => {
        const isFav = favorites.has(pdf.name);
        const isSelected = isSelectionMode && selectedItems.has(pdf.name);
        const badge = getBadge?.(pdf.name) ?? null;
        const isGroup = badge !== null && !!onGroupClick;
        return {
            pdf, isFav, isSelected, isGroup, badge, isSelectionMode, showHidden,
            onToggleSelect, onToggleFavorite, onPdfClick, onGroupClick,
            onRename, onRegenThumb, onToggleHidden, onEditSeries,
            getAuthors, onAuthorClick, getTags, onTagClick,
        };
    };

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over || active.id === over.id || !onReorder) return;
        const oldIndex = pdfs.findIndex(p => p.name === active.id);
        const newIndex = pdfs.findIndex(p => p.name === over.id);
        if (oldIndex < 0 || newIndex < 0) return;
        const reordered = arrayMove(pdfs, oldIndex, newIndex);
        onReorder(reordered.map(p => p.name));
    };

    const gridClass = "grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4";
    const useDnd = dndEnabled && !isSelectionMode;

    if (useDnd) {
        return (
            <div>
                <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">PDFs</h2>
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                    <SortableContext items={pdfs.map(p => p.name)} strategy={rectSortingStrategy}>
                        <div className={gridClass}>
                            {pdfs.map(pdf => (
                                <SortableCard key={pdf.name} {...buildCardProps(pdf)} />
                            ))}
                        </div>
                    </SortableContext>
                </DndContext>
            </div>
        );
    }

    return (
        <div>
            <h2 className="text-lg font-semibold mb-4 text-gray-700 dark:text-gray-300">PDFs</h2>
            <div className={gridClass}>
                {pdfs.map(pdf => (
                    <div key={pdf.name}>
                        <CardContent {...buildCardProps(pdf)} />
                    </div>
                ))}
            </div>
        </div>
    );
}
