import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { PdfSearchBar } from '../components/reader/PdfSearchBar';

const renderBar = (overrides: Partial<Parameters<typeof PdfSearchBar>[0]> = {}) => {
    const props = {
        searchText: '',
        matchCount: 0,
        currentMatch: 0,
        onSearchChange: vi.fn(),
        onPrevMatch: vi.fn(),
        onNextMatch: vi.fn(),
        onClose: vi.fn(),
        ...overrides,
    };
    return { props, ...render(<PdfSearchBar {...props} />) };
};

describe('PdfSearchBar', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('入力欄と検索アイコンが描画される', () => {
        const { getByPlaceholderText } = renderBar();
        expect(getByPlaceholderText('PDFテキストを検索...')).toBeInTheDocument();
    });

    it('入力で localText が更新され、デバウンス後に onSearchChange が呼ばれる', () => {
        const { props, getByRole } = renderBar();

        fireEvent.change(getByRole('textbox'), { target: { value: 'hello' } });
        // デバウンス前は呼ばれない（初回マウントの '' は許容）
        const callsBefore = props.onSearchChange.mock.calls.length;

        // SEARCH_DEBOUNCE_MS = 300
        act(() => {
            vi.advanceTimersByTime(300);
        });
        expect(props.onSearchChange.mock.calls.length).toBeGreaterThan(callsBefore);
        const lastCall = props.onSearchChange.mock.calls.at(-1);
        expect(lastCall?.[0]).toBe('hello');
    });

    it('Enter キーで onNextMatch を呼ぶ', () => {
        const { props, getByRole } = renderBar({ matchCount: 5, currentMatch: 1 });
        fireEvent.keyDown(getByRole('textbox'), { key: 'Enter' });
        expect(props.onNextMatch).toHaveBeenCalled();
        expect(props.onPrevMatch).not.toHaveBeenCalled();
    });

    it('Shift+Enter で onPrevMatch を呼ぶ', () => {
        const { props, getByRole } = renderBar({ matchCount: 5, currentMatch: 3 });
        fireEvent.keyDown(getByRole('textbox'), { key: 'Enter', shiftKey: true });
        expect(props.onPrevMatch).toHaveBeenCalled();
        expect(props.onNextMatch).not.toHaveBeenCalled();
    });

    it('Escape キーで onClose を呼ぶ', () => {
        const { props, getByRole } = renderBar();
        fireEvent.keyDown(getByRole('textbox'), { key: 'Escape' });
        expect(props.onClose).toHaveBeenCalled();
    });

    it('matchCount > 0 で "current / total" が表示される', () => {
        const { getByText } = renderBar({ matchCount: 7, currentMatch: 3 });
        expect(getByText('3 / 7')).toBeInTheDocument();
    });

    it('localText が非空 + matchCount=0 で「見つかりません」が表示される', () => {
        const { getByText, getByRole } = renderBar({ matchCount: 0 });
        fireEvent.change(getByRole('textbox'), { target: { value: 'xxx' } });
        expect(getByText('見つかりません')).toBeInTheDocument();
    });

    it('上ボタン（前の結果）クリックで onPrevMatch', () => {
        const { props, getByTitle } = renderBar({ matchCount: 5 });
        fireEvent.click(getByTitle(/前の結果/));
        expect(props.onPrevMatch).toHaveBeenCalled();
    });

    it('下ボタン（次の結果）クリックで onNextMatch', () => {
        const { props, getByTitle } = renderBar({ matchCount: 5 });
        fireEvent.click(getByTitle(/次の結果/));
        expect(props.onNextMatch).toHaveBeenCalled();
    });

    it('閉じるボタンクリックで onClose', () => {
        const { props, getByTitle } = renderBar();
        fireEvent.click(getByTitle(/閉じる/));
        expect(props.onClose).toHaveBeenCalled();
    });

    it('matchCount=0 のとき上下ボタンは disabled', () => {
        const { getByTitle } = renderBar({ matchCount: 0 });
        expect((getByTitle(/前の結果/) as HTMLButtonElement).disabled).toBe(true);
        expect((getByTitle(/次の結果/) as HTMLButtonElement).disabled).toBe(true);
    });
});
