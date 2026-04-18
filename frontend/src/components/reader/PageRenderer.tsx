import { Page } from 'react-pdf';
import { CheckSquare, Square } from 'lucide-react';
import { buildStaticUrl } from '../../config/api';
import type { PageSide, ReadingDirection } from '../../types';

interface PageRendererProps {
    pageNumber: number;
    numPages: number;
    windowHeight: number;
    isEditMode: boolean;
    isSelected: boolean;
    side: PageSide;
    direction: ReadingDirection;
    onToggleSelection: (pageNum: number, e: React.MouseEvent) => void;
    onNext: (e: React.MouseEvent) => void;
    onPrev: (e: React.MouseEvent) => void;
    // Image mode props
    imageUrl?: string | null;
    isImageMode?: boolean;
    // Search props (PDF mode only)
    searchText?: string;
    customTextRenderer?: (props: { str: string; itemIndex: number }) => string;
    /** ページのサイズが判明したときに呼ばれるコールバック（自動見開き判定用） */
    onPageSize?: (width: number, height: number) => void;
}

/**
 * 単一ページのレンダリングコンポーネント
 * - PDF モードと画像モードの両方に対応
 * - 検索テキストがある場合はテキストレイヤーを有効化してハイライト表示
 * - onPageSize コールバックでページの縦横比を親に通知（自動見開き判定）
 */
export function PageRenderer({
    pageNumber,
    numPages,
    windowHeight,
    isEditMode,
    isSelected,
    side,
    direction,
    onToggleSelection,
    onNext,
    onPrev,
    imageUrl,
    isImageMode = false,
    searchText,
    customTextRenderer,
    onPageSize,
}: PageRendererProps) {
    if (pageNumber > numPages) {
        return (
            <div
                style={{ height: windowHeight - 40, width: (windowHeight - 40) * 0.7 }}
                className="bg-gray-800 flex items-center justify-center text-gray-500 max-w-full"
            >
                End
            </div>
        );
    }

    const handleClick = (e: React.MouseEvent) => {
        if (isEditMode) {
            e.stopPropagation();
            onToggleSelection(pageNumber, e);
        } else {
            if (side === 'left') {
                direction === 'rtl' ? onNext(e) : onPrev(e);
            } else if (side === 'right') {
                direction === 'rtl' ? onPrev(e) : onNext(e);
            } else {
                onNext(e);
            }
        }
    };

    const selectionIndicator = isEditMode && (
        <div className="absolute top-2 right-2 z-10 bg-white rounded-full p-1 shadow-md">
            {isSelected ? (
                <CheckSquare className="w-6 h-6 text-red-500" />
            ) : (
                <Square className="w-6 h-6 text-gray-400" />
            )}
        </div>
    );

    if (isImageMode && imageUrl) {
        return (
            <div
                className={`relative ${isSelected ? 'ring-4 ring-red-500' : ''}`}
                onClick={handleClick}
            >
                {selectionIndicator}
                <img
                    src={buildStaticUrl(imageUrl)}
                    alt={`Page ${pageNumber}`}
                    style={{ height: 'auto', width: 'auto', maxWidth: '100%', maxHeight: windowHeight - 40, objectFit: 'contain' }}
                    className="bg-white"
                    onLoad={(e) => {
                        const img = e.currentTarget;
                        onPageSize?.(img.naturalWidth, img.naturalHeight);
                    }}
                />
            </div>
        );
    }

    // テキスト検索が有効な場合はテキストレイヤーも描画する
    const enableTextLayer = Boolean(searchText && customTextRenderer);

    return (
        <div
            className={`shadow-2xl cursor-pointer shrink-0 max-w-[calc(50vw-2rem)] flex justify-center relative ${
                isSelected ? 'ring-4 ring-red-500' : ''
            }`}
            onClick={handleClick}
        >
            {selectionIndicator}
            <Page
                pageNumber={pageNumber}
                height={windowHeight - 40}
                className="bg-white !w-auto !h-auto !max-w-full flex items-center justify-center [&_canvas]:!w-auto [&_canvas]:!h-auto [&_canvas]:!max-w-full [&_canvas]:!max-h-full [&_canvas]:object-contain"
                renderTextLayer={enableTextLayer}
                renderAnnotationLayer={false}
                customTextRenderer={enableTextLayer ? customTextRenderer : undefined}
                onRenderSuccess={(page) => {
                    onPageSize?.(page.width, page.height);
                }}
            />
        </div>
    );
}
