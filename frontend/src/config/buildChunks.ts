export function resolveManualChunk(id: string): string | undefined {
    if (!id.includes('node_modules')) return undefined;
    if (id.includes('vis-network') || id.includes('vis-data')) return 'chunk-vis';
    if (id.includes('react-pdf') || id.includes('pdfjs-dist')) return 'chunk-pdf';
    if (id.includes('@tanstack')) return 'chunk-tanstack';
    if (id.includes('lucide-react')) return 'chunk-lucide';
    return undefined;
}
