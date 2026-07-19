import { useQuery } from '@tanstack/react-query';

import type { DiscussionHistoryItem } from '@/features/novel_db/api';
import { fetchDiscussionHistory, fetchSimilarBooks } from '@/features/novel_db/api';
import { novelDbKeys } from '@/features/novel_db/queries';
import type { SimilarBook } from '@/features/novel_db/types';

interface UseNovelDetailDataReturn {
    discussions: DiscussionHistoryItem[];
    discussionsLoading: boolean;
    similarBooks: SimilarBook[];
    similarLoading: boolean;
}

export function useNovelDetailData(bookName: string, isIndexed: boolean): UseNovelDetailDataReturn {
    const discussionsQuery = useQuery({
        queryKey: novelDbKeys.discussions(bookName),
        queryFn: () => fetchDiscussionHistory(bookName),
        enabled: bookName.length > 0,
    });
    const similarQuery = useQuery({
        queryKey: novelDbKeys.similarBooks(bookName),
        queryFn: () => fetchSimilarBooks(bookName),
        enabled: bookName.length > 0 && isIndexed,
    });

    return {
        discussions: discussionsQuery.data ?? [],
        discussionsLoading: discussionsQuery.isLoading,
        similarBooks: similarQuery.data ?? [],
        similarLoading: similarQuery.isLoading,
    };
}
