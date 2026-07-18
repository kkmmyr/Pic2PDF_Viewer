import { useQuery } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type { LibrarySource, BookImagesResponse } from '@/types';

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
 * `version` だけが変化した場合は placeholderData で直前の画像を保持する。
 * 書籍・パス・source の変更時は旧データを引き継がず、query key と AbortSignal により
 * 古いリクエストが現在の書籍状態を上書きしないようにする。
 */
export function useBookImages(
    selectedPdf: string | null,
    currentPath: string,
    source: LibrarySource = 'doujin',
    version: number = 0,
): UseBookImagesReturn {
    const query = useQuery<BookImagesResponse>({
        queryKey: ['book-images', selectedPdf, currentPath, source, version],
        enabled: selectedPdf !== null && source !== 'novel',
        queryFn: ({ signal }) => {
            if (!selectedPdf) return Promise.resolve({ images: [] });
            const bookName = selectedPdf.replace(/\.pdf$/i, '');
            const bookPath = currentPath ? `${currentPath}/${bookName}` : bookName;
            return apiClient.get<unknown, BookImagesResponse>(
                API_ENDPOINTS.BOOK_IMAGES(bookPath, source),
                { signal },
            );
        },
        placeholderData: (previousData, previousQuery) => {
            const previousKey = previousQuery?.queryKey;
            const isSameBook =
                previousKey?.[1] === selectedPdf &&
                previousKey?.[2] === currentPath &&
                previousKey?.[3] === source;
            return isSameBook ? previousData : undefined;
        },
    });

    const images = query.data?.images;
    const imageUrls = images && images.length > 0 ? images : null;

    return {
        imageUrls,
        numPages: imageUrls?.length ?? 0,
        isImageMode: imageUrls !== null,
        isLoading: query.isFetching,
    };
}
