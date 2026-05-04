import { useState, useCallback } from 'react';
import { pdfjs } from 'react-pdf';

/**
 * PDF ドキュメントのメタ状態（ページ数 / リフレッシュ用バージョン）を管理するフック。
 *
 * - `numPages`: PDF の総ページ数（ロード成功時にバックエンドから設定）
 * - `pdfVersion`: ページ削除等で PDF が更新された際にインクリメントして
 *   `<Document>` に再フェッチを促す（クエリパラメータに付与する）
 */
export function usePdfDocumentState() {
    const [numPages, setNumPages] = useState(0);
    const [pdfVersion, setPdfVersion] = useState(0);

    const bumpPdfVersion = useCallback(() => setPdfVersion(v => v + 1), []);
    const resetNumPages = useCallback(() => setNumPages(0), []);

    /** react-pdf の `<Document onLoadSuccess>` から呼ぶハンドラ。`onLoaded` で副作用を継続できる。 */
    const handleDocumentLoadSuccess = useCallback(
        (pdf: pdfjs.PDFDocumentProxy, onLoaded?: (pdf: pdfjs.PDFDocumentProxy) => void) => {
            setNumPages(pdf.numPages);
            onLoaded?.(pdf);
        },
        [],
    );

    return {
        numPages, setNumPages, resetNumPages,
        pdfVersion, bumpPdfVersion,
        handleDocumentLoadSuccess,
    };
}
