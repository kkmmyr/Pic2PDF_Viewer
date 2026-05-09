import { Page } from 'react-pdf';
import { buildStaticUrl } from '../../config/api';
import type { PageSide, ReadingDirection } from '../../types';

interface PageRendererProps {
    pageNumber: number;
    numPages: number;
    windowHeight: number;
    side: PageSide;
    direction: ReadingDirection;
    onNext: (e: React.MouseEvent) => void;
    onPrev: (e: React.MouseEvent) => void;
    /** 現在の実効見開き状態。1 ページ表示時は max-width を全幅に拡大して表示する */
    isSpread: boolean;
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
 *
 * 編集モードでのページ選択 UI は本コンポーネントには持たない。
 * 削除対象ページの選択は `<PageGridOverlay>`（全画面オーバーレイ）で行う。
 */
export function PageRenderer({
    pageNumber,
    numPages,
    windowHeight,
    side,
    direction,
    onNext,
    onPrev,
    isSpread,
    imageUrl,
    isImageMode = false,
    searchText,
    customTextRenderer,
    onPageSize,
}: PageRendererProps) {
    // 1 ページ表示時は画面幅を広く使う（横長見開き原稿が画面幅一杯に表示される）
    const maxWidthClass = isSpread ? 'max-w-[calc(50vw-2rem)]' : 'max-w-[calc(100vw-4rem)]';

    // ページ範囲外、または画像モードで該当 URL が無い（削除直後に
    // imageUrls.length が numPages の同期より一瞬先に縮むケース）は End を返す。
    // これをやらないと画像モードのまま PDF 経路の <Page> が <Document> 無しで
    // 描画され "Attempted to load a page, but no document was specified" になる。
    if (pageNumber > numPages || (isImageMode && !imageUrl)) {
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
        if (side === 'left') {
            if (direction === 'rtl') onNext(e);
            else onPrev(e);
        } else if (side === 'right') {
            if (direction === 'rtl') onPrev(e);
            else onNext(e);
        } else {
            onNext(e);
        }
    };

    if (isImageMode && imageUrl) {
        return (
            <div className="relative" onClick={handleClick}>
                <img
                    src={buildStaticUrl(imageUrl)}
                    alt={`Page ${pageNumber}`}
                    style={{
                        height: 'auto',
                        width: 'auto',
                        maxWidth: '100%',
                        maxHeight: windowHeight - 40,
                        objectFit: 'contain',
                    }}
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
            className={`shadow-2xl cursor-pointer shrink-0 ${maxWidthClass} flex justify-center relative`}
            onClick={handleClick}
        >
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
