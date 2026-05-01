import { type ReactNode } from 'react';
import { Check, Star, Pencil, RefreshCw, Library, EyeOff, Eye, BookCopy, Users } from 'lucide-react';
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
    /** シリーズ集約のみ: view_count > 0 の既読冊数 */
    readCount?: number;
}

export interface PdfCardProps {
    pdf: PdfFile;
    isFav: boolean;
    isSelected: boolean;
    isGroup: boolean;
    badge: PdfCardBadge | null;
    isSelectionMode: boolean;
    showHidden: boolean;
    isUnread?: boolean;
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
    /** DnD: ドラッグハンドル要素（指定時はカード内に表示） */
    dragHandle?: ReactNode;
}

/** 書籍カード本体。DnD 有効時はドラッグハンドルを外側から差し込む。 */
export function PdfCard({
    pdf, isFav, isSelected, isGroup, badge, isSelectionMode, showHidden, isUnread,
    onToggleSelect, onToggleFavorite, onPdfClick, onGroupClick,
    onRename, onRegenThumb, onToggleHidden, onEditSeries,
    getAuthors, onAuthorClick, getTags, onTagClick, dragHandle,
}: PdfCardProps) {
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
                    <div className="absolute top-2 right-2 z-card-badge">
                        {isSelected ? (
                            <div className="w-6 h-6 rounded-full bg-amber-500 flex items-center justify-center shadow-md ring-2 ring-white dark:ring-gray-800">
                                <Check className="w-4 h-4 text-white" strokeWidth={3} />
                            </div>
                        ) : (
                            <div className="w-6 h-6 rounded-full bg-white/90 dark:bg-gray-800/90 border-2 border-gray-400 dark:border-gray-500 shadow-sm" />
                        )}
                    </div>
                )}

                {/* 集約バッジ（シリーズ: readCount/count巻 / 作者: count冊） */}
                {isGroup && badge && (
                    <div className="absolute top-2 right-2 z-card-badge px-1.5 py-0.5 rounded-full bg-purple-600 text-white text-xs font-semibold flex items-center gap-1 shadow">
                        {badge.kind === 'series'
                            ? <Library className="w-3 h-3" />
                            : <Users className="w-3 h-3" />}
                        {badge.kind === 'series' && badge.readCount !== undefined
                            ? `${badge.readCount}/${badge.count}巻`
                            : `${badge.count}${badge.kind === 'series' ? '巻' : '冊'}`}
                    </div>
                )}

                {/* ピンボタン（シリーズ集約カードのみ非表示） */}
                {!isSelectionMode && onToggleFavorite && !(isGroup && badge?.kind === 'series') && (
                    <button
                        className="absolute top-2 left-2 z-card-badge p-1 rounded-full bg-white/80 dark:bg-gray-900/70 hover:bg-white dark:hover:bg-gray-900 transition-colors"
                        onClick={(e) => {
                            e.stopPropagation();
                            onToggleFavorite(pdf.name);
                        }}
                        title={isFav ? '集約カードの表示から外す' : '集約カードの表示に設定'}
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
                        {!isGroup && isUnread && (
                            <span className="px-1.5 py-0.5 rounded-full bg-sky-500 text-white text-xs font-semibold leading-none">NEW</span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
