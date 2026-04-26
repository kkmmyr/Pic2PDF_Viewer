import { useState, useCallback, useEffect, useRef } from 'react';
import { pdfjs } from 'react-pdf';

interface UsePdfSearchParams {
    isSearchOpen: boolean;
    setPageNumber: (page: number) => void;
}

export function usePdfSearch({ isSearchOpen, setPageNumber }: UsePdfSearchParams) {
    const [searchText, setSearchText] = useState('');
    const [matchCount, setMatchCount] = useState(0);
    const [currentMatch, setCurrentMatch] = useState(0);
    const pdfRef = useRef<pdfjs.PDFDocumentProxy | null>(null);

    const searchAllPages = useCallback(async (text: string, pdf: pdfjs.PDFDocumentProxy) => {
        if (!text) {
            setMatchCount(0);
            setCurrentMatch(0);
            return;
        }

        let totalMatches = 0;
        let firstMatchPage = -1;
        const escaped = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(escaped, 'gi');

        for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            const content = await page.getTextContent();
            const pageText = content.items
                .map((item) => ('str' in item ? item.str : ''))
                .join('');
            const matches = pageText.match(regex);
            const count = matches ? matches.length : 0;

            if (count > 0 && firstMatchPage === -1) firstMatchPage = i;
            totalMatches += count;
        }

        setMatchCount(totalMatches);
        setCurrentMatch(totalMatches > 0 ? 1 : 0);
        if (firstMatchPage > 0) setPageNumber(firstMatchPage);
    }, [setPageNumber]);

    useEffect(() => {
        if (!isSearchOpen || !searchText) {
            setMatchCount(0);
            setCurrentMatch(0);
            return;
        }
        if (!pdfRef.current) return;
        searchAllPages(searchText, pdfRef.current);
    }, [searchText, isSearchOpen, searchAllPages]);

    const handleCloseSearch = useCallback(() => {
        setSearchText('');
        setMatchCount(0);
        setCurrentMatch(0);
    }, []);

    const handlePrevMatch = useCallback(() => {
        setCurrentMatch(prev => (prev > 1 ? prev - 1 : matchCount));
    }, [matchCount]);

    const handleNextMatch = useCallback(() => {
        setCurrentMatch(prev => (prev < matchCount ? prev + 1 : 1));
    }, [matchCount]);

    const customTextRenderer = useCallback(
        ({ str }: { str: string }) => {
            if (!searchText || !str) return str;
            const escaped = searchText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escaped})`, 'gi');
            return str.replace(regex, `<mark style="background:rgba(255,200,0,0.5);border-radius:2px;">$1</mark>`);
        },
        [searchText]
    );

    const onDocumentLoaded = useCallback((pdf: pdfjs.PDFDocumentProxy) => {
        pdfRef.current = pdf;
        if (isSearchOpen && searchText) {
            searchAllPages(searchText, pdf);
        }
    }, [isSearchOpen, searchText, searchAllPages]);

    return {
        searchText,
        setSearchText,
        matchCount,
        currentMatch,
        pdfRef,
        handleCloseSearch,
        handlePrevMatch,
        handleNextMatch,
        customTextRenderer,
        onDocumentLoaded,
    };
}
