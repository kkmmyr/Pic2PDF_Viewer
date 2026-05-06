import { useState, useEffect } from 'react';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { LibrarySource, BookImagesResponse } from '../types';

interface UseBookImagesReturn {
    imageUrls: string[] | null;
    numPages: number;
    isImageMode: boolean;
    isLoading: boolean;
}

/**
 * 書籍画像を取得するカスタムフック
 */
export function useBookImages(
    selectedPdf: string | null,
    currentPath: string,
    source: LibrarySource = 'generated'
): UseBookImagesReturn {
    const [imageUrls, setImageUrls] = useState<string[] | null>(null);
    const [numPages, setNumPages] = useState(0);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        setImageUrls(null);
        setNumPages(0);

        if (!selectedPdf) return;

        // novel ソースは OCR 済み Searchable PDF なので、PDF モードで表示する（画像取得スキップ）
        if (source === 'novel') return;

        // Try to fetch images
        const bookName = selectedPdf.replace(/\.pdf$/i, '');
        const bookPath = currentPath ? `${currentPath}/${bookName}` : bookName;

        setIsLoading(true);

        apiClient.get<unknown, BookImagesResponse>(API_ENDPOINTS.BOOK_IMAGES(bookPath, source))
            .then(data => {
                if (data.images && data.images.length > 0) {
                    setImageUrls(data.images);
                    setNumPages(data.images.length);
                }
            })
            .catch(() => {
                // Fallback to PDF mode (do nothing, imageUrls stays null)
                console.log("Images not found, falling back to PDF");
            })
            .finally(() => {
                setIsLoading(false);
            });
    }, [selectedPdf, currentPath, source]);

    return {
        imageUrls,
        numPages,
        isImageMode: imageUrls !== null,
        isLoading,
    };
}
