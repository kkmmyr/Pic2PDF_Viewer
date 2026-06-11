/**
 * QuestionInput: 文字数 + 送信ボタン disable + 連投警告。
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import QuestionInput from '@/components/novel_db/QuestionInput';

function setup(opts: {
    onSubmit?: ReturnType<typeof vi.fn<(question: string) => void>>;
    isReplay?: (q: string) => boolean;
    disabled?: boolean;
}) {
    const onSubmit = opts.onSubmit ?? vi.fn<(question: string) => void>();
    const isReplay = opts.isReplay ?? (() => false);
    const utils = render(
        <QuestionInput onSubmit={onSubmit} isReplay={isReplay} disabled={opts.disabled} />,
    );
    return { ...utils, onSubmit };
}

describe('QuestionInput', () => {
    it('空欄では送信ボタンが disabled', () => {
        setup({});
        const button = screen.getByRole('button', { name: /送信/ });
        expect(button).toBeDisabled();
    });

    it('500 字超で送信ボタンが disabled', () => {
        setup({});
        const textarea = screen.getByRole('textbox');
        fireEvent.change(textarea, { target: { value: 'あ'.repeat(501) } });
        const button = screen.getByRole('button', { name: /送信/ });
        expect(button).toBeDisabled();
        expect(screen.getByText(/501 \/ 500/)).toBeInTheDocument();
    });

    it('正常時は onSubmit が呼ばれて入力がクリアされる', () => {
        const { onSubmit } = setup({});
        const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
        fireEvent.change(textarea, { target: { value: 'デュークは?' } });

        fireEvent.click(screen.getByRole('button', { name: /送信/ }));

        expect(onSubmit).toHaveBeenCalledWith('デュークは?');
        expect(textarea.value).toBe('');
    });

    it('連投の場合は確認ダイアログが出て、確定で onSubmit', () => {
        const { onSubmit } = setup({ isReplay: () => true });
        const textarea = screen.getByRole('textbox');
        fireEvent.change(textarea, { target: { value: '同じ質問' } });

        fireEvent.click(screen.getByRole('button', { name: /送信/ }));
        // この時点で onSubmit は未呼び出し（ダイアログ表示中）
        expect(onSubmit).not.toHaveBeenCalled();

        // ダイアログが表示されている
        expect(screen.getByText('同じ質問を再送しますか?')).toBeInTheDocument();

        // ダイアログ表示中は入力欄の「送信」ボタンが aria-hidden。ダイアログ内のみが accessible
        const sendButtons = screen.getAllByRole('button', { name: /送信/ });
        expect(sendButtons.length).toBe(1);
        fireEvent.click(sendButtons[0]);
        expect(onSubmit).toHaveBeenCalledWith('同じ質問');
    });

    it('disabled prop で textarea が無効化される', () => {
        setup({ disabled: true });
        const textarea = screen.getByRole('textbox');
        expect(textarea).toBeDisabled();
    });
});
