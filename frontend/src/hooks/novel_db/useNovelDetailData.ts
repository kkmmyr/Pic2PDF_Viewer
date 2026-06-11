import { useEffect, useState } from 'react';
import type { DiscussionHistoryItem } from '@/features/novel_db/api';
import { fetchDiscussionHistory, fetchSimilarBooks } from '@/features/novel_db/api';
import type { SimilarBook } from '@/features/novel_db/types';

interface UseNovelDetailDataReturn {
    discussions: DiscussionHistoryItem[];
    discussionsLoading: boolean;
    similarBooks: SimilarBook[];
    similarLoading: boolean;
}

export function useNovelDetailData(bookName: string, isIndexed: boolean): UseNovelDetailDataReturn {
    const [discussions, setDiscussions] = useState<DiscussionHistoryItem[]>([]);
    const [discussionsLoading, setDiscussionsLoading] = useState(false);
    const [similarBooks, setSimilarBooks] = useState<SimilarBook[]>([]);
    const [similarLoading, setSimilarLoading] = useState(false);

    useEffect(() => {
        if (!bookName) return;
        setDiscussionsLoading(true);
        fetchDiscussionHistory(bookName)
            .then(setDiscussions)
            .catch(() => {})
            .finally(() => setDiscussionsLoading(false));
    }, [bookName]);

    useEffect(() => {
        if (!bookName || !isIndexed) return;
        setSimilarLoading(true);
        fetchSimilarBooks(bookName)
            .then(setSimilarBooks)
            .catch(() => {})
            .finally(() => setSimilarLoading(false));
    }, [bookName, isIndexed]);

    return { discussions, discussionsLoading, similarBooks, similarLoading };
}
