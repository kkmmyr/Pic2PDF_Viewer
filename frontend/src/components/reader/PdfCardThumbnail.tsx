import { type ReactNode } from 'react';
import { Check, Star, Library, Users } from 'lucide-react';
import type { PdfCardBadge } from './PdfCard';
import { LazyThumbnail } from './LazyThumbnail';

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
    name, thumbnail, isFav, isSelected, isGroup, badge,
    isSelectionMode, onClick, onToggleFavorite, dragHandle,
}: PdfCardThumbnailProps) {
    return (
        <div className="aspect-[3/4] relative cursor-pointer" onClick={onClick}>
            {dragHandle}

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

            {isGroup && badge && (
                <div className="absolute top-2 right-2 z-card-badge px-1.5 py-0.5 rounded-full bg-accent-600 text-white text-xs font-semibold flex items-center gap-1 shadow-md ring-1 ring-white/40 dark:ring-white/20">
                    {badge.kind === 'series'
                        ? <Library className="w-3 h-3" />
                        : <Users className="w-3 h-3" />}
                    {badge.kind === 'series' && badge.readCount !== undefined
                        ? `${badge.readCount}/${badge.count}巻`
                        : `${badge.count}${badge.kind === 'series' ? '巻' : '冊'}`}
                </div>
            )}

            {!isSelectionMode && onToggleFavorite && badge?.kind !== 'author' && (
                <button
                    className="absolute top-2 left-2 z-card-badge p-1 rounded-full bg-white/80 dark:bg-gray-900/70 hover:bg-white dark:hover:bg-gray-900 transition-colors"
                    onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(name);
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

            <LazyThumbnail src={thumbnail} alt={name} className="absolute inset-0" />
        </div>
    );
}
