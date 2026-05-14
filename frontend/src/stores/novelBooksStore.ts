import { create } from 'zustand';
import type { BookSummary, SeriesSummary } from '../features/novel_db/types';
import { fetchBooks, fetchSeries } from '../features/novel_db/api';

interface NovelBooksState {
    books: BookSummary[];
    series: SeriesSummary[];
    isLoading: boolean;
    error: string | null;
}

interface NovelBooksActions {
    fetch: () => Promise<void>;
}

export const useNovelBooksStore = create<NovelBooksState & NovelBooksActions>((set, get) => ({
    books: [],
    series: [],
    isLoading: false,
    error: null,

    fetch: async () => {
        // Prevent concurrent fetches
        if (get().isLoading) return;
        set({ isLoading: true, error: null });
        try {
            const [b, s] = await Promise.all([fetchBooks(), fetchSeries()]);
            set({ books: Array.isArray(b) ? b : [], series: Array.isArray(s) ? s : [] });
        } catch (e) {
            set({ error: e instanceof Error ? e.message : String(e) });
        } finally {
            set({ isLoading: false });
        }
    },
}));
