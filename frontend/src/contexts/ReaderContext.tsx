/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { useReaderState } from '@/hooks/reader/useReaderState';
import type { LibrarySource } from '@/types';

type ReaderContextValue = ReturnType<typeof useReaderState> & {
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
};

const ReaderContext = createContext<ReaderContextValue | null>(null);

export function useReaderContext(): ReaderContextValue {
    const ctx = useContext(ReaderContext);
    if (!ctx) throw new Error('useReaderContext must be inside ReaderProvider');
    return ctx;
}

interface ReaderProviderProps {
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    onPdfUpdated: () => void;
    onClose: () => void;
    onSelectPdf?: (name: string) => void;
    children: ReactNode;
}

export function ReaderProvider({ children, ...props }: ReaderProviderProps) {
    const { selectedPdf, currentPath, currentSource } = props;
    const reader = useReaderState(props);
    return (
        <ReaderContext.Provider value={{ ...reader, selectedPdf, currentPath, currentSource }}>
            {children}
        </ReaderContext.Provider>
    );
}
