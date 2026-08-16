import { type ReactNode } from 'react';
import { Check, Star, Library, Users } from 'lucide-react';
import type { PdfCardBadge } from '@/components/library/PdfCard';
import { LazyThumbnail } from '@/components/library/LazyThumbnail';

interface PdfCardThumbnailProps {
    name: string;
    thumbnail: string | null;
    isFav: boolean;
    isSelected: boolean;
    isGroup: boolean;
    badge: PdfCardBadge | null;
    isSelectionMode: boolean;
    onClick: () => void;
    onToggleFavorite?: (name: string) => void;
    dragHandle?: ReactNode;
}

export function PdfCardThumbnail({
    name,
    thumbnail,
    isFav,
    isSelected,
    isGroup,
    badge,
    isSelectionMode,
    onClick,
    onToggleFavorite,
    dragHandle,
}: PdfCardThumbnailProps) {
    const displayName = badge?.displayTitle ?? name.replace(/\.pdf$/i, '');
    const openLabel = isSelectionMode
        ? isSelected
            ? `${displayName} の選択を解除`
            : `${displayName} を選択`
        : isGroup
          ? `${displayName} を開く`
          : `${displayName} を読む`;

    return (
        <div className="relative aspect-[3/4] overflow-hidden bg-gray-100 dark:bg-gray-900">
            <button
                type="button"
                className="absolute inset-0 w-full text-left transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-accent-500"
                onClick={onClick}
                aria-label={openLabel}
            >
                <LazyThumbnail src={thumbnail} alt={name} className="absolute inset-0" />
            </button>
            {dragHandle}

            {isSelectionMode && (
                <div className="absolute right-2 top-2 z-card-badge" aria-hidden="true">
                    {isSelected ? (
                        <div className="w-6 h-6 rounded-full bg-amber-500 flex items-center justify-center shadow-md ring-2 ring-white dark:ring-gray-800">
                            <Check className="w-4 h-4 text-white" strokeWidth={3} />
                        </div>
                    ) : (
                        <div className="w-6 h-6 rounded-full bg-white/90 dark:bg-gray-800/90 border-2 border-gray-400 dark:border-gray-500 shadow-sm" />
                    )}
                </div>
            )}

            {isGroup && badge && (
                <div className="absolute top-2 right-2 z-card-badge px-1.5 py-0.5 rounded-full bg-accent-700 text-white text-xs font-semibold flex items-center gap-1 shadow-md ring-1 ring-white/40 dark:ring-white/20">
                    {badge.kind === 'series' ? (
                        <Library className="w-3 h-3" />
                    ) : (
                        <Users className="w-3 h-3" />
                    )}
                    {badge.kind === 'series' && badge.readCount !== undefined
                        ? `${badge.readCount}/${badge.count}巻`
                        : `${badge.count}${badge.kind === 'series' ? '巻' : '冊'}`}
                </div>
            )}

            {!isSelectionMode && onToggleFavorite && badge?.kind !== 'author' && (
                <button
                    type="button"
                    className="absolute left-1 top-1 z-card-badge flex h-11 w-11 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-sm transition-colors hover:bg-white hover:text-amber-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 dark:bg-gray-900/90 dark:text-gray-300 dark:hover:bg-gray-900 dark:hover:text-amber-300"
                    onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(name);
                    }}
                    title={isFav ? '集約カードの表示から外す' : '集約カードの表示に設定'}
                    aria-label={`${displayName}を${isFav ? '集約カードの表示から外す' : '集約カードの表示に設定'}`}
                >
                    <Star
                        aria-hidden="true"
                        className={`w-4 h-4 transition-colors ${
                            isFav
                                ? 'text-amber-400 fill-amber-400'
                                : 'text-gray-600 dark:text-gray-300'
                        }`}
                    />
                </button>
            )}
        </div>
    );
}
