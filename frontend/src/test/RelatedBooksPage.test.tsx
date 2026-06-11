import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RelatedBooksPage } from '@/components/reader/RelatedBooksPage';
import type { RelatedBooks } from '@/hooks/reader/useRelatedBooks';

const empty: RelatedBooks = { series: [], authors: [] };

describe('RelatedBooksPage', () => {
    it('セクションどちらも空でも見出しは出る（遷移自体は親側で抑止する想定）', () => {
        render(
            <RelatedBooksPage
                related={empty}
                currentPath=""
                currentSource="doujin"
                onSelect={vi.fn()}
            />,
        );
        expect(screen.getByText('関連書籍')).toBeInTheDocument();
        expect(screen.queryByText('同シリーズ')).not.toBeInTheDocument();
        expect(screen.queryByText('同じ作者')).not.toBeInTheDocument();
    });

    it('同シリーズセクションは series_index バッジ + タイトルを表示', () => {
        const related: RelatedBooks = {
            series: [
                { name: 'a.pdf', seriesIndex: 1, seriesTitle: 'X' },
                { name: 'b.pdf', seriesIndex: 2, seriesTitle: 'X' },
            ],
            authors: [],
        };
        render(
            <RelatedBooksPage
                related={related}
                currentPath=""
                currentSource="doujin"
                onSelect={vi.fn()}
            />,
        );
        expect(screen.getByText('同シリーズ')).toBeInTheDocument();
        expect(screen.getByText('#1')).toBeInTheDocument();
        expect(screen.getByText('#2')).toBeInTheDocument();
        expect(screen.getByText('a')).toBeInTheDocument();
        expect(screen.getByText('b')).toBeInTheDocument();
    });

    it('同作者セクションはタイトルのみ表示（バッジなし）', () => {
        const related: RelatedBooks = {
            series: [],
            authors: [{ name: 'c.pdf' }, { name: 'd.pdf' }],
        };
        render(
            <RelatedBooksPage
                related={related}
                currentPath=""
                currentSource="doujin"
                onSelect={vi.fn()}
            />,
        );
        expect(screen.getByText('同じ作者')).toBeInTheDocument();
        expect(screen.getByText('c')).toBeInTheDocument();
        expect(screen.getByText('d')).toBeInTheDocument();
    });

    it('カードクリックで onSelect(name) が呼ばれる', () => {
        const onSelect = vi.fn();
        const related: RelatedBooks = {
            series: [{ name: 'a.pdf', seriesIndex: 1, seriesTitle: 'X' }],
            authors: [{ name: 'c.pdf' }],
        };
        render(
            <RelatedBooksPage
                related={related}
                currentPath="sub"
                currentSource="doujin"
                onSelect={onSelect}
            />,
        );
        fireEvent.click(screen.getByText('a').closest('button')!);
        expect(onSelect).toHaveBeenCalledWith('a.pdf');

        fireEvent.click(screen.getByText('c').closest('button')!);
        expect(onSelect).toHaveBeenCalledWith('c.pdf');
    });
});
