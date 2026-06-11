import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { SearchableSelect } from '@/components/ui/SearchableSelect';

beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
});

const opts = ['Apple', 'Banana', 'Cherry'];

describe('SearchableSelect', () => {
    it('閉じている間は emptyLabel が placeholder に出る', () => {
        const { getByRole } = render(
            <SearchableSelect
                value=""
                options={opts}
                emptyLabel="作者: すべて"
                onChange={() => {}}
            />,
        );
        const input = getByRole('textbox') as HTMLInputElement;
        expect(input.value).toBe('');
        expect(input.placeholder).toBe('作者: すべて');
    });

    it('value 既存値は閉じている間 input の value に表示される', () => {
        const { getByRole } = render(
            <SearchableSelect value="Apple" options={opts} emptyLabel="-" onChange={() => {}} />,
        );
        expect((getByRole('textbox') as HTMLInputElement).value).toBe('Apple');
    });

    it('開閉トグル: ChevronDown ボタンで開く', () => {
        const { getByLabelText, queryByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />,
        );
        expect(queryByText('Apple')).toBeNull();
        fireEvent.click(getByLabelText('開く'));
        expect(queryByText('Apple')).not.toBeNull();
    });

    it('focus で開く', () => {
        const { getByRole, queryByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />,
        );
        fireEvent.focus(getByRole('textbox'));
        expect(queryByText('Apple')).not.toBeNull();
    });

    it('入力で候補が部分一致フィルタ（大小区別なし）', () => {
        const { getByRole, queryByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />,
        );
        fireEvent.focus(getByRole('textbox'));
        fireEvent.change(getByRole('textbox'), { target: { value: 'AP' } });
        expect(queryByText('Apple')).not.toBeNull();
        expect(queryByText('Banana')).toBeNull();
        expect(queryByText('Cherry')).toBeNull();
    });

    it('Enter で highlight 中の項目を選択して onChange を呼ぶ（初期は空 = empty）', () => {
        const onChange = vi.fn();
        const { getByRole } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('textbox'));
        fireEvent.keyDown(getByRole('textbox'), { key: 'Enter' });
        expect(onChange).toHaveBeenCalledWith('');
    });

    it('↓キーで highlight が次へ移動 / Enter で確定', () => {
        const onChange = vi.fn();
        const { getByRole } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('textbox'));
        fireEvent.keyDown(getByRole('textbox'), { key: 'ArrowDown' });
        fireEvent.keyDown(getByRole('textbox'), { key: 'Enter' });
        expect(onChange).toHaveBeenCalledWith('Apple');
    });

    it('↑キーで highlight が戻る（0 で止まる）', () => {
        const onChange = vi.fn();
        const { getByRole } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('textbox'));
        fireEvent.keyDown(getByRole('textbox'), { key: 'ArrowDown' });
        fireEvent.keyDown(getByRole('textbox'), { key: 'ArrowDown' });
        fireEvent.keyDown(getByRole('textbox'), { key: 'ArrowUp' });
        fireEvent.keyDown(getByRole('textbox'), { key: 'Enter' });
        expect(onChange).toHaveBeenCalledWith('Apple');
    });

    it('Escape で閉じる（onChange は呼ばれない）', () => {
        const onChange = vi.fn();
        const { getByRole, queryByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('textbox'));
        expect(queryByText('Apple')).not.toBeNull();
        fireEvent.keyDown(getByRole('textbox'), { key: 'Escape' });
        expect(queryByText('Apple')).toBeNull();
        expect(onChange).not.toHaveBeenCalled();
    });

    it('候補のクリック（mouseDown）で選択', () => {
        const onChange = vi.fn();
        const { getByRole, getByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('textbox'));
        fireEvent.mouseDown(getByText('Banana'));
        expect(onChange).toHaveBeenCalledWith('Banana');
    });

    it('value がある + 閉じている時に X クリックで select("")', () => {
        const onChange = vi.fn();
        const { getByTitle } = render(
            <SearchableSelect value="Apple" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.click(getByTitle('クリア'));
        expect(onChange).toHaveBeenCalledWith('');
    });

    it('value="" の時は X クリアボタンが表示されない', () => {
        const { queryByTitle } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />,
        );
        expect(queryByTitle('クリア')).toBeNull();
    });

    it('該当なし入力で「該当なし」が表示される', () => {
        const { getByRole, getByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />,
        );
        fireEvent.focus(getByRole('textbox'));
        fireEvent.change(getByRole('textbox'), { target: { value: 'ZZZZ' } });
        expect(getByText('該当なし')).toBeInTheDocument();
    });

    it('外クリック（document mousedown）で閉じる', () => {
        const { getByRole, queryByText } = render(
            <div>
                <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />
                <button>outside</button>
            </div>,
        );
        fireEvent.focus(getByRole('textbox'));
        expect(queryByText('Apple')).not.toBeNull();
        fireEvent.mouseDown(document.body);
        expect(queryByText('Apple')).toBeNull();
    });
});
