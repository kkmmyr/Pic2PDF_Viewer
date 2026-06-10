/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { useLibraryPanel } from '../hooks/library/useLibraryPanel';

type LibraryPanelContextValue = ReturnType<typeof useLibraryPanel> & {
    onUpClick: () => void;
};

const LibraryPanelContext = createContext<LibraryPanelContextValue | null>(null);

export function useLibraryPanelContext(): LibraryPanelContextValue {
    const ctx = useContext(LibraryPanelContext);
    if (!ctx) throw new Error('useLibraryPanelContext must be inside LibraryPanelProvider');
    return ctx;
}

interface LibraryPanelProviderProps {
    onPdfClick: (name: string) => void;
    onUpClick: () => void;
    children: ReactNode;
}

export function LibraryPanelProvider({
    onPdfClick,
    onUpClick,
    children,
}: LibraryPanelProviderProps) {
    const panel = useLibraryPanel(onPdfClick);
    return (
        <LibraryPanelContext.Provider value={{ ...panel, onUpClick }}>
            {children}
        </LibraryPanelContext.Provider>
    );
}
