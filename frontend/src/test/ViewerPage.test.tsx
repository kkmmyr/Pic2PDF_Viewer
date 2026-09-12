import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ViewerPage from '@/pages/ViewerPage';
import { useLibraryStore } from '@/stores/libraryStore';
import { pdfQueryKey } from '@/hooks/library/useLibraryPdfs';

vi.mock('@/components/library', () => ({
    LibraryPanel: ({
        onPdfClick,
        onUpClick,
    }: {
        onPdfClick: (name: string) => void;
        onUpClick: () => void;
    }) => {
        const [value, setValue] = useState('');
        return (
            <section aria-label="一覧fixture">
                <input
                    aria-label="保持する入力"
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                />
                <button onClick={() => onPdfClick('book.pdf')}>本を開く</button>
                <button onClick={onUpClick}>上のフォルダ</button>
            </section>
        );
    },
}));
vi.mock('@/components/reader', () => ({
    ReaderPanel: (props: {
        selectedPdf: string;
        currentPath: string;
        currentSource: string;
        initialPage?: number;
        onClose: () => void;
        onPdfUpdated: () => void;
        onSelectPdf: (name: string) => void;
    }) => (
        <section aria-label="Reader fixture">
            <output>
                {JSON.stringify({
                    file: props.selectedPdf,
                    path: props.currentPath,
                    source: props.currentSource,
                    page: props.initialPage,
                })}
            </output>
            <button onClick={props.onClose}>読書を閉じる</button>
            <button onClick={props.onPdfUpdated}>編集完了</button>
            <button onClick={() => props.onSelectPdf('next.pdf')}>次巻</button>
        </section>
    ),
}));

function setup(url: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const router = createMemoryRouter([{ path: '*', element: <ViewerPage /> }], {
        initialEntries: [url],
    });
    render(
        <QueryClientProvider client={client}>
            <RouterProvider router={router} />
        </QueryClientProvider>,
    );
    return { router, invalidate };
}

describe('Viewerの一覧と読書sessionの契約', () => {
    beforeEach(() => useLibraryStore.setState({ currentPath: '', currentSource: 'doujin' }));

    it('読書中も一覧のDOMと状態を保持し、閉じる・履歴戻る/進むで復帰する', async () => {
        const { router } = setup('/comic?path=sub&author=作者&series=シリーズ');
        const list = screen.getByRole('region', { name: '一覧fixture' });
        const input = screen.getByLabelText('保持する入力');
        fireEvent.change(input, { target: { value: '保持' } });
        list.scrollTop = 230;
        fireEvent.click(screen.getByText('本を開く'));
        expect(list.parentElement).toHaveClass('hidden');
        expect(screen.getByRole('region', { name: 'Reader fixture' })).toHaveTextContent(
            '"source":"comic"',
        );
        fireEvent.click(screen.getByText('読書を閉じる'));
        expect(screen.getByRole('region', { name: '一覧fixture' })).toBe(list);
        expect(input).toHaveValue('保持');
        expect(list.scrollTop).toBe(230);
        expect(router.state.location.search).toContain('author=');
        expect(router.state.location.search).toContain('series=');
        await act(() => router.navigate(-1));
        expect(screen.getByRole('region', { name: 'Reader fixture' })).toBeInTheDocument();
        await act(() => router.navigate(1));
        expect(screen.queryByRole('region', { name: 'Reader fixture' })).not.toBeInTheDocument();
    });

    it('URLのsource/path/pageを渡し、編集時は当該一覧のcacheだけ無効化する', async () => {
        const { router, invalidate } = setup('/novel?path=a&file=book.pdf&page=4&author=作者');
        expect(useLibraryStore.getState()).toMatchObject({
            currentSource: 'novel',
            currentPath: 'a',
        });
        expect(screen.getByRole('region', { name: 'Reader fixture' })).toHaveTextContent(
            '"page":4',
        );
        fireEvent.click(screen.getByText('編集完了'));
        expect(invalidate).toHaveBeenLastCalledWith({ queryKey: pdfQueryKey('a', 'novel') });
        fireEvent.click(screen.getByText('次巻'));
        expect(router.state.location.search).toContain('file=next.pdf');
        expect(router.state.location.search).not.toContain('page=');
        await act(() => router.navigate('/comic?path=b&file=other.pdf'));
        expect(useLibraryStore.getState()).toMatchObject({
            currentSource: 'comic',
            currentPath: 'b',
        });
        fireEvent.click(screen.getByText('編集完了'));
        expect(invalidate).toHaveBeenLastCalledWith({ queryKey: pdfQueryKey('b', 'comic') });
    });
});
