import { useState, useEffect } from 'react';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';
import { LibrarySource, BookImagesResponse } from '../../types';

interface UseBookImagesReturn {
    imageUrls: string[] | null;
    numPages: number;
    isImageMode: boolean;
    isLoading: boolean;
}

/**
 * 書籍画像を取得するカスタムフック
 *
 * `version` が変化すると画像リストを再フェッチする。ページ削除（`useEditMode`）後に
 * `pdfVersion` を渡すことで、image-only モード（generated）でも削除直後に表示が追従する。
 *
 * effect を 2 つに分けてあるのは flicker 防止のため:
 * - 状態リセット effect は書籍が変わった時のみ動かす
 * - `version` だけが変化したときは古い `imageUrls` を保持したまま新しいリクエストを発行し、
 *   到着次第差し替える。これをやらないと `imageUrls=null` を経由して `isImageMode=false`
 *   に倒れ、`generated` ソースで存在しない PDF を `<Document>` が取りに行ってエラーが出る。
 */
export function useBookImages(
    selectedPdf: string | null,
    currentPath: string,
    source: LibrarySource = 'doujin',
    version: number = 0,
): UseBookImagesReturn {
    const [imageUrls, setImageUrls] = useState<string[] | null>(null);
    const [numPages, setNumPages] = useState(0);
    const [isLoading, setIsLoading] = useState(false);

    // 書籍が変わったとき（または source が変わったとき）だけ state をリセットする。
    // version 変化では発火しない。
    useEffect(() => {
        setImageUrls(null);
        setNumPages(0);
    }, [selectedPdf, currentPath, source]);

    // 画像リスト取得。version 変化でも再フェッチするが、上の effect は動かないので
    // 古い imageUrls を保持したまま新しいリクエストが飛ぶ。
    useEffect(() => {
        if (!selectedPdf) return;

        const bookName = selectedPdf.replace(/\.pdf$/i, '');
        const bookPath = currentPath ? `${currentPath}/${bookName}` : bookName;

        setIsLoading(true);

        apiClient
            .get<unknown, BookImagesResponse>(API_ENDPOINTS.BOOK_IMAGES(bookPath, source))
            .then((data) => {
                if (data.images && data.images.length > 0) {
                    setImageUrls(data.images);
                    setNumPages(data.images.length);
                }
            })
            .catch(() => {
                // Fallback to PDF mode (do nothing, imageUrls stays null)
                console.log('Images not found, falling back to PDF');
            })
            .finally(() => {
                setIsLoading(false);
            });
    }, [selectedPdf, currentPath, source, version]);

    return {
        imageUrls,
        numPages,
        isImageMode: imageUrls !== null,
        isLoading,
    };
}
