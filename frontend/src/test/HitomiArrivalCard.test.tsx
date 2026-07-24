import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { HitomiArrivalCard } from '@/components/hitomi/HitomiArrivalCard';
import type { ArrivalItem } from '@/types/hitomi';

const item: ArrivalItem = {
    id: 42,
    artist: 'aka shio',
    display_artist: 'あかしお',
    title: 'タイトルA',
    language: 'japanese',
    type: 'doujinshi',
    page_count: 30,
    published_at: '2026-05-01',
    discovered_at: '2026-05-06',
    url: 'https://hitomi.la/12345',
    is_read: false,
    read_at: null,
};

describe('HitomiArrivalCard', () => {
    it('title / display_artist / type / page_count を表示', () => {
        const { getByText } = render(<HitomiArrivalCard item={item} onDismiss={vi.fn()} />);
        expect(getByText('タイトルA')).toBeInTheDocument();
        expect(getByText(/あかしお/)).toBeInTheDocument();
        expect(getByText(/doujinshi/)).toBeInTheDocument();
        expect(getByText(/30 ページ/)).toBeInTheDocument();
    });

    it('display_artist が空なら artist にフォールバック', () => {
        const { getByText } = render(
            <HitomiArrivalCard item={{ ...item, display_artist: '' }} onDismiss={vi.fn()} />,
        );
        expect(getByText(/aka shio/)).toBeInTheDocument();
    });

    it('title が空文字なら "(タイトル不明)" 表示', () => {
        const { getByText } = render(
            <HitomiArrivalCard item={{ ...item, title: '' }} onDismiss={vi.fn()} />,
        );
        expect(getByText('(タイトル不明)')).toBeInTheDocument();
    });

    it('hitomi.la リンクが正しい href / target=_blank', () => {
        const { getByText } = render(<HitomiArrivalCard item={item} onDismiss={vi.fn()} />);
        const link = getByText('hitomi.la で開く').closest('a')!;
        expect(link.getAttribute('href')).toBe('https://hitomi.la/12345');
        expect(link.getAttribute('target')).toBe('_blank');
        expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    });

    it('「既読」ボタンクリックで onDismiss(id) が呼ばれる', () => {
        const onDismiss = vi.fn();
        const { getByText } = render(<HitomiArrivalCard item={item} onDismiss={onDismiss} />);
        fireEvent.click(getByText('既読'));
        expect(onDismiss).toHaveBeenCalledWith(42);
    });

    it('published_at / discovered_at の日付フォーマットが含まれる', () => {
        const { container } = render(<HitomiArrivalCard item={item} onDismiss={vi.fn()} />);
        expect(container.textContent).toMatch(/公開:/);
        expect(container.textContent).toMatch(/検出:/);
        expect(container.textContent).toMatch(/2026/);
    });

    it('published_at 不在なら公開ラベルが出ない', () => {
        const { container } = render(
            <HitomiArrivalCard item={{ ...item, published_at: '' }} onDismiss={vi.fn()} />,
        );
        expect(container.textContent).not.toMatch(/公開:/);
    });

    it('履歴表示では既読ボタンを隠し、旧移行データの日時なしを表示', () => {
        const { queryByText, getByText } = render(
            <HitomiArrivalCard item={{ ...item, is_read: true, read_at: null }} />,
        );
        expect(queryByText('既読', { selector: 'button' })).not.toBeInTheDocument();
        expect(getByText(/日時記録なし/)).toBeInTheDocument();
    });
});
