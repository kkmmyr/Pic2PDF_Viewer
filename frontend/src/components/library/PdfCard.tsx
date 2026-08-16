import { type ReactNode } from 'react';
import type { PdfFile, ReadState } from '@/types';
import { PdfCardThumbnail } from '@/components/library/PdfCardThumbnail';
import { PdfCardActionButtons } from '@/components/library/PdfCardActionButtons';
import { BookCardShell } from '@/components/ui/book-card-shell';
import { formatTimestampJa } from '@/utils/date';

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

    const title = isGroup && badge ? badge.displayTitle : pdf.name.replace(/\.pdf$/i, '');
    const authors = getAuthors?.(pdf.name) ?? [];

    return (
        <BookCardShell
            title={pdf.name}
            displayTitle={title}
            tone={isSelected ? 'selected' : isGroup ? 'group' : 'default'}
            cover={
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
            }
            authors={
                authors.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                        {authors.map((author) =>
                            onAuthorClick ? (
                                <button
                                    key={author}
                                    type="button"
                                    className="inline-flex min-h-8 max-w-full items-center rounded-md bg-primary-50 px-2 text-left text-xs font-medium text-primary-800 hover:bg-primary-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 dark:bg-primary-900/30 dark:text-primary-200 dark:hover:bg-primary-800/50"
                                    onClick={() => onAuthorClick(author)}
                                    title={`「${author}」で絞り込む`}
                                    aria-label={`作者「${author}」で絞り込む`}
                                >
                                    <span className="truncate">{author}</span>
                                </button>
                            ) : (
                                <span
                                    key={author}
                                    className="truncate text-xs font-medium text-gray-700 dark:text-gray-300"
                                >
                                    {author}
                                </span>
                            ),
                        )}
                    </div>
                ) : undefined
            }
            footer={
                <PdfCardActionButtons
                    name={pdf.name}
                    createdAtLabel={formatTimestampJa(pdf.created_at)}
                    isSelectionMode={isSelectionMode}
                    showHidden={showHidden}
                    isGroup={isGroup}
                    readState={readState}
                    onRename={onRename}
                    onRegenThumb={onRegenThumb}
                    onToggleHidden={onToggleHidden}
                    onEditSeries={onEditSeries}
                />
            }
        />
    );
}
