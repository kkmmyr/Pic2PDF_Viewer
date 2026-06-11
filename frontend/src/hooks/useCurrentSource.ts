import { useLocation } from 'react-router-dom';
import type { LibrarySource } from '@/types';

export const useCurrentSource = (): LibrarySource => {
    const { pathname } = useLocation();
    if (pathname.startsWith('/comic')) return 'comic';
    if (pathname.startsWith('/novel')) return 'novel';
    return 'doujin';
};
