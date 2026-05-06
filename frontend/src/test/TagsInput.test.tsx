import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { createRef } from 'react';
import { TagsInput } from '../components/ui/TagsInput';

const noop = () => {};

describe('TagsInput', () => {
    it('tags 配列を chip として描画する', () => {
        const inputRef = createRef<HTMLInputElement>();
        const { getByText } = render(
            <TagsInput
                tags={['A', 'B']}
                input=""
                inputRef={inputRef}
                onChange={noop}
                onKeyDown={noop}
                onRemove={noop}
            />,
        );
        expect(getByText('A')).toBeInTheDocument();
        expect(getByText('B')).toBeInTheDocument();
    });

    it('tags 数だけ × ボタンが描画され、index 付きで onRemove が呼ばれる', () => {
        const onRemove = vi.fn();
        const inputRef = createRef<HTMLInputElement>();
        const { container } = render(
            <TagsInput
                tags={['A', 'B', 'C']}
                input=""
                inputRef={inputRef}
                onChange={noop}
                onKeyDown={noop}
                onRemove={onRemove}
            />,
        );
        const removeButtons = container.querySelectorAll('button');
        expect(removeButtons.length).toBe(3);
        fireEvent.click(removeButtons[0]);
        expect(onRemove).toHaveBeenCalledWith(0);
        fireEvent.click(removeButtons[2]);
        expect(onRemove).toHaveBeenCalledWith(2);
    });

    it('input への入力で onChange が文字列で呼ばれる', () => {
        const onChange = vi.fn();
        const inputRef = createRef<HTMLInputElement>();
        const { getByRole } = render(
            <TagsInput
                tags={[]}
                input=""
                inputRef={inputRef}
                onChange={onChange}
                onKeyDown={noop}
                onRemove={noop}
            />,
        );
        fireEvent.change(getByRole('textbox'), { target: { value: 'tag1' } });
        expect(onChange).toHaveBeenCalledWith('tag1');
    });

    it('Enter キーで onKeyDown が呼ばれる', () => {
        const onKeyDown = vi.fn();
        const inputRef = createRef<HTMLInputElement>();
        const { getByRole } = render(
            <TagsInput
                tags={[]}
                input="x"
                inputRef={inputRef}
                onChange={noop}
                onKeyDown={onKeyDown}
                onRemove={noop}
            />,
        );
        fireEvent.keyDown(getByRole('textbox'), { key: 'Enter' });
        expect(onKeyDown).toHaveBeenCalled();
    });

    it('placeholder は tags が空のときだけ表示される', () => {
        const inputRef = createRef<HTMLInputElement>();
        const { rerender, getByPlaceholderText, queryByPlaceholderText } = render(
            <TagsInput
                tags={[]}
                input=""
                inputRef={inputRef}
                placeholder="入力"
                onChange={noop}
                onKeyDown={noop}
                onRemove={noop}
            />,
        );
        expect(getByPlaceholderText('入力')).toBeInTheDocument();

        rerender(
            <TagsInput
                tags={['A']}
                input=""
                inputRef={inputRef}
                placeholder="入力"
                onChange={noop}
                onKeyDown={noop}
                onRemove={noop}
            />,
        );
        expect(queryByPlaceholderText('入力')).toBeNull();
    });

    it('hintText が指定されると表示される', () => {
        const inputRef = createRef<HTMLInputElement>();
        const { getByText } = render(
            <TagsInput
                tags={[]}
                input=""
                inputRef={inputRef}
                hintText="ヒント"
                onChange={noop}
                onKeyDown={noop}
                onRemove={noop}
            />,
        );
        expect(getByText('ヒント')).toBeInTheDocument();
    });

    it('onBlur が指定されると input の blur 時に呼ばれる', () => {
        const onBlur = vi.fn();
        const inputRef = createRef<HTMLInputElement>();
        const { getByRole } = render(
            <TagsInput
                tags={[]}
                input=""
                inputRef={inputRef}
                onChange={noop}
                onKeyDown={noop}
                onRemove={noop}
                onBlur={onBlur}
            />,
        );
        fireEvent.blur(getByRole('textbox'));
        expect(onBlur).toHaveBeenCalled();
    });

    it('chip × ボタンクリックは外側 div の click と独立して onRemove が呼ばれる', () => {
        const onRemove = vi.fn();
        const inputRef = createRef<HTMLInputElement>();
        const { container } = render(
            <TagsInput
                tags={['A']}
                input=""
                inputRef={inputRef}
                onChange={noop}
                onKeyDown={noop}
                onRemove={onRemove}
            />,
        );
        const removeBtn = container.querySelector('button')!;
        fireEvent.click(removeBtn);
        expect(onRemove).toHaveBeenCalledWith(0);
    });
});
