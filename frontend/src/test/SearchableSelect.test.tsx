import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { SearchableSelect } from '@/components/ui/searchable-select';

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
        const input = getByRole('combobox') as HTMLInputElement;
        expect(input.value).toBe('');
        expect(input.placeholder).toBe('作者: すべて');
    });

    it('value 既存値は閉じている間 input の value に表示される', () => {
        const { getByRole } = render(
            <SearchableSelect value="Apple" options={opts} emptyLabel="-" onChange={() => {}} />,
        );
        expect((getByRole('combobox') as HTMLInputElement).value).toBe('Apple');
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
        fireEvent.focus(getByRole('combobox'));
        expect(queryByText('Apple')).not.toBeNull();
    });

    it('入力で候補が部分一致フィルタ（大小区別なし）', () => {
        const { getByRole, queryByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />,
        );
        fireEvent.focus(getByRole('combobox'));
        fireEvent.change(getByRole('combobox'), { target: { value: 'AP' } });
        expect(queryByText('Apple')).not.toBeNull();
        expect(queryByText('Banana')).toBeNull();
        expect(queryByText('Cherry')).toBeNull();
    });

    it('Enter で highlight 中の項目を選択して onChange を呼ぶ（初期は空 = empty）', () => {
        const onChange = vi.fn();
        const { getByRole } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('combobox'));
        fireEvent.keyDown(getByRole('combobox'), { key: 'Enter' });
        expect(onChange).toHaveBeenCalledWith('');
    });

    it('↓キーで highlight が次へ移動 / Enter で確定', () => {
        const onChange = vi.fn();
        const { getByRole } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('combobox'));
        fireEvent.keyDown(getByRole('combobox'), { key: 'ArrowDown' });
        fireEvent.keyDown(getByRole('combobox'), { key: 'Enter' });
        expect(onChange).toHaveBeenCalledWith('Apple');
    });

    it('↑キーで highlight が戻る（0 で止まる）', () => {
        const onChange = vi.fn();
        const { getByRole } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('combobox'));
        fireEvent.keyDown(getByRole('combobox'), { key: 'ArrowDown' });
        fireEvent.keyDown(getByRole('combobox'), { key: 'ArrowDown' });
        fireEvent.keyDown(getByRole('combobox'), { key: 'ArrowUp' });
        fireEvent.keyDown(getByRole('combobox'), { key: 'Enter' });
        expect(onChange).toHaveBeenCalledWith('Apple');
    });

    it('Escape で閉じる（onChange は呼ばれない）', () => {
        const onChange = vi.fn();
        const { getByRole, queryByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('combobox'));
        expect(queryByText('Apple')).not.toBeNull();
        fireEvent.keyDown(getByRole('combobox'), { key: 'Escape' });
        expect(queryByText('Apple')).toBeNull();
        expect(onChange).not.toHaveBeenCalled();
    });

    it('候補のクリック（mouseDown）で選択', () => {
        const onChange = vi.fn();
        const { getByRole, getByText } = render(
            <SearchableSelect value="" options={opts} emptyLabel="all" onChange={onChange} />,
        );
        fireEvent.focus(getByRole('combobox'));
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
        fireEvent.focus(getByRole('combobox'));
        fireEvent.change(getByRole('combobox'), { target: { value: 'ZZZZ' } });
        expect(getByText('該当なし')).toBeInTheDocument();
    });

    it('外クリック（document mousedown）で閉じる', () => {
        const { getByRole, queryByText } = render(
            <div>
                <SearchableSelect value="" options={opts} emptyLabel="all" onChange={() => {}} />
                <button>outside</button>
            </div>,
        );
        fireEvent.focus(getByRole('combobox'));
        expect(queryByText('Apple')).not.toBeNull();
        fireEvent.mouseDown(document.body);
        expect(queryByText('Apple')).toBeNull();
    });

    it('combobox と listbox の状態・候補関係を公開する', () => {
        const { getByRole, getAllByRole } = render(
            <SearchableSelect
                value=""
                options={opts}
                emptyLabel="作者: すべて"
                onChange={() => {}}
            />,
        );
        const combobox = getByRole('combobox');
        expect(combobox).toHaveAttribute('aria-expanded', 'false');

        fireEvent.focus(combobox);

        const listbox = getByRole('listbox');
        expect(combobox).toHaveAttribute('aria-expanded', 'true');
        expect(combobox).toHaveAttribute('aria-controls', listbox.id);
        expect(combobox).toHaveAttribute('aria-activedescendant', getAllByRole('option')[0].id);
        expect(getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true');
    });
});
