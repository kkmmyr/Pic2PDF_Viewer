import { useState, useEffect } from 'react';
import { buildApiUrl, API_ENDPOINTS } from '../config/api';

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
    currentPath: string
): UseBookImagesReturn {
    const [imageUrls, setImageUrls] = useState<string[] | null>(null);
    const [numPages, setNumPages] = useState(0);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        setImageUrls(null);
        setNumPages(0);

        if (!selectedPdf) return;

        // Try to fetch images
        const bookName = selectedPdf.replace(/\.pdf$/i, '');
        const bookPath = currentPath ? `${currentPath}/${bookName}` : bookName;

        setIsLoading(true);

        fetch(buildApiUrl(API_ENDPOINTS.BOOK_IMAGES(bookPath)))
            .then(res => {
                if (res.ok) return res.json();
                throw new Error('No images');
            })
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
    }, [selectedPdf, currentPath]);

    return {
        imageUrls,
        numPages,
        isImageMode: imageUrls !== null,
        isLoading,
    };
}
