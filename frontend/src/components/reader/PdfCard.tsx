import { type ReactNode } from 'react';
import type { PdfFile, ReadState } from '../../types';
import { PdfCardThumbnail } from './PdfCardThumbnail';
import { PdfCardActionButtons } from './PdfCardActionButtons';
import { formatTimestampJa } from '../../utils/date';

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
    readState?: ReadState;
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
    pdf,
    isFav,
    isSelected,
    isGroup,
    badge,
    isSelectionMode,
    showHidden,
    readState,
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
    getTags,
    onTagClick,
    dragHandle,
}: PdfCardProps) {
    const handleThumbnailClick = () => {
        if (isSelectionMode && onToggleSelect) {
            onToggleSelect(pdf.name);
        } else if (isGroup && onGroupClick) {
            onGroupClick(pdf.name);
        } else {
            onPdfClick(pdf.name);
        }
    };

    return (
        <div
            className={`rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow flex flex-col border-2 ${
                isSelected
                    ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20'
                    : isGroup
                      ? 'border-accent-300 dark:border-accent-700 bg-white dark:bg-gray-800'
                      : 'border-transparent bg-white dark:bg-gray-800'
            }`}
        >
            <PdfCardThumbnail
                name={pdf.name}
                thumbnail={pdf.thumbnail}
                isFav={isFav}
                isSelected={isSelected}
                isGroup={isGroup}
                badge={badge}
                isSelectionMode={isSelectionMode}
                onClick={handleThumbnailClick}
                onToggleFavorite={onToggleFavorite}
                dragHandle={dragHandle}
            />

            <div
                className={`p-3 flex-1 flex flex-col justify-between ${isSelected ? 'bg-amber-50 dark:bg-amber-900/20' : 'bg-white dark:bg-gray-800'}`}
            >
                <span
                    className={`font-medium text-sm line-clamp-2 ${isGroup ? 'text-accent-700 dark:text-accent-300' : 'text-gray-800 dark:text-gray-200'}`}
                    title={isGroup && badge ? badge.displayTitle : pdf.name}
                >
                    {isGroup && badge ? badge.displayTitle : pdf.name.replace('.pdf', '')}
                </span>
                {getAuthors &&
                    (() => {
                        const authors = getAuthors(pdf.name);
                        return authors.length > 0 ? (
                            <div className="mt-1 flex flex-wrap gap-1">
                                {authors.map((a, i) => (
                                    <span
                                        key={i}
                                        className={`text-xs px-1.5 py-0.5 rounded bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 truncate max-w-full ${onAuthorClick ? 'cursor-pointer hover:bg-primary-100 dark:hover:bg-primary-800/50' : ''}`}
                                        onClick={
                                            onAuthorClick
                                                ? (e) => {
                                                      e.stopPropagation();
                                                      onAuthorClick(a);
                                                  }
                                                : undefined
                                        }
                                        title={onAuthorClick ? `"${a}" で絞り込む` : undefined}
                                    >
                                        {a}
                                    </span>
                                ))}
                            </div>
                        ) : null;
                    })()}
                {getTags &&
                    (() => {
                        const tags = getTags(pdf.name);
                        return tags.length > 0 ? (
                            <div className="mt-1 flex flex-wrap gap-1">
                                {tags.map((t, i) => (
                                    <span
                                        key={i}
                                        className={`text-xs px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 truncate max-w-full ${onTagClick ? 'cursor-pointer hover:bg-emerald-100 dark:hover:bg-emerald-800/50' : ''}`}
                                        onClick={
                                            onTagClick
                                                ? (e) => {
                                                      e.stopPropagation();
                                                      onTagClick(t);
                                                  }
                                                : undefined
                                        }
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
                        {formatTimestampJa(pdf.created_at)}
                    </span>
                    <PdfCardActionButtons
                        name={pdf.name}
                        isSelectionMode={isSelectionMode}
                        showHidden={showHidden}
                        isGroup={isGroup}
                        readState={readState}
                        onRename={onRename}
                        onRegenThumb={onRegenThumb}
                        onToggleHidden={onToggleHidden}
                        onEditSeries={onEditSeries}
                    />
                </div>
            </div>
        </div>
    );
}
