export const novelGraphKeys = {
    all: ['novelGraph'] as const,
    series: () => [...novelGraphKeys.all, 'series'] as const,
    books: (seriesId: string | null) => [...novelGraphKeys.all, 'books', seriesId] as const,
    graph: (seriesId: string | null, bookIds: number[]) =>
        [...novelGraphKeys.all, 'graph', seriesId, bookIds] as const,
};
