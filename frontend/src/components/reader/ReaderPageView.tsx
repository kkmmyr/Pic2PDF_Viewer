import { Document, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import { PageRenderer } from './PageRenderer';
import { useReaderContext } from '../../contexts/ReaderContext';

// <Document> を使うモジュールと同じファイルで workerSrc を設定する必要がある（react-pdf の要件）
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
).toString();

// Searchable PDF（ReportLab 生成）に含まれる ASCII85 ストリーム中の `<` を pdf.js の lenient parser が
// hex string 開始と誤読し getHexString warning を大量に出すため、verbosity を ERRORS に下げる。
// Document の options は識別性が変わると再読込を誘発するためモジュールスコープで固定する。
const PDF_DOCUMENT_OPTIONS = {
    verbosity: pdfjs.VerbosityLevel.ERRORS,
};

/**
 * リーダーのメインコンテンツ描画コンポーネント。
 * - 画像モード: WebP 画像を直接表示
 * - PDF モード: react-pdf <Document> 配下で <Page> を表示
 * renderPageItem / renderSpreadPages のロジックを集約する。
 * ナビゲーションは親の ReaderPanel がクリックゾーンで一元管理する。
 */
export function ReaderPageView() {
    const {
        pageNumber,
        numPages,
        windowHeight,
        isSpread,
        direction,
        isImageMode,
        imageUrls,
        searchText,
        customTextRenderer,
        handlePageSize,
        pdfUrl,
        onDocumentLoadSuccess,
    } = useReaderContext();

    const renderPageItem = (pNum: number) => (
        <PageRenderer
            key={`page-${pNum}`}
            pageNumber={pNum}
            numPages={numPages}
            windowHeight={windowHeight}
            isImageMode={isImageMode}
            imageUrl={imageUrls ? imageUrls[pNum - 1] : null}
            searchText={searchText}
            customTextRenderer={!isImageMode && searchText ? customTextRenderer : undefined}
            isSpread={isSpread}
            onPageSize={handlePageSize}
        />
    );

    const renderSpreadPages = () => {
        const p1 = pageNumber;
        const p2 = pageNumber + 1;
        if (direction === 'rtl') {
            if (pageNumber === 1) return <>{renderPageItem(p1)}</>;
            return (
                <>
                    {renderPageItem(p2)}
                    {renderPageItem(p1)}
                </>
            );
        }
        return (
            <>
                {renderPageItem(p1)}
                {renderPageItem(p2)}
            </>
        );
    };

    if (isImageMode) {
        return (
            <div className="flex gap-0 shadow-2xl justify-center bg-gray-900">
                {isSpread ? renderSpreadPages() : renderPageItem(pageNumber)}
            </div>
        );
    }

    return (
        <Document
            file={pdfUrl}
            options={PDF_DOCUMENT_OPTIONS}
            onLoadSuccess={onDocumentLoadSuccess}
            className="flex justify-center"
            loading={
                <div className="flex items-center justify-center h-96">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500" />
                </div>
            }
        >
            <div className="flex shadow-2xl">
                {isSpread ? renderSpreadPages() : renderPageItem(pageNumber)}
            </div>
        </Document>
    );
}
