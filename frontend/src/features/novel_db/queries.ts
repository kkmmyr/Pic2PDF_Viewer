import { queryOptions } from '@tanstack/react-query';

import { fetchBooks, fetchSeries } from '@/features/novel_db/api';
import type { Scope } from '@/features/novel_db/types';

export const novelDbKeys = {
    all: ['novelDb'] as const,
    library: () => [...novelDbKeys.all, 'library'] as const,
    books: () => [...novelDbKeys.library(), 'books'] as const,
    series: () => [...novelDbKeys.library(), 'series'] as const,
    bookDetail: (bookName: string) => [...novelDbKeys.all, 'bookDetail', bookName] as const,
    pageCount: (bookName: string) => [...novelDbKeys.all, 'pageCount', bookName] as const,
    characters: (bookName: string) => [...novelDbKeys.all, 'characters', bookName] as const,
    character: (bookName: string | null, charName: string | null) =>
        [...novelDbKeys.all, 'character', bookName, charName] as const,
    search: (query: string, scope: Scope) =>
        [...novelDbKeys.all, 'search', query, scope.type, scope.id ?? null] as const,
    qaHistory: (book?: string) => [...novelDbKeys.all, 'qaHistory', book ?? null] as const,
    chatSessionsRoot: () => [...novelDbKeys.all, 'chatSessions'] as const,
    chatSessions: (scope?: Scope) =>
        [...novelDbKeys.chatSessionsRoot(), scope?.type ?? null, scope?.id ?? null] as const,
    chatSession: (sessionId: number | null) =>
        [...novelDbKeys.all, 'chatSession', sessionId] as const,
    discussions: (bookName: string) => [...novelDbKeys.all, 'discussions', bookName] as const,
    similarBooks: (bookName: string) => [...novelDbKeys.all, 'similarBooks', bookName] as const,
    rebuildStatus: () => [...novelDbKeys.all, 'rebuildStatus'] as const,
};

export const novelBooksQueryOptions = () =>
    queryOptions({
        queryKey: novelDbKeys.books(),
        queryFn: fetchBooks,
    });

export const novelSeriesQueryOptions = () =>
    queryOptions({
        queryKey: novelDbKeys.series(),
        queryFn: fetchSeries,
    });
