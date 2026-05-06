import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

describe('ConfirmDialog', () => {
    it('open=false で表示されない', () => {
        const { container } = render(
            <ConfirmDialog
                open={false}
                title="削除"
                message="削除しますか？"
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(container.firstChild).toBeNull();
    });

    it('open=true で title と message が表示される', () => {
        const { getByText } = render(
            <ConfirmDialog
                open
                title="削除確認"
                message="本当に削除しますか？"
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(getByText('削除確認')).toBeInTheDocument();
        expect(getByText('本当に削除しますか？')).toBeInTheDocument();
    });

    it('既定の confirmLabel/cancelLabel は "実行" / "キャンセル"', () => {
        const { getByText } = render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={() => {}} />,
        );
        expect(getByText('実行')).toBeInTheDocument();
        expect(getByText('キャンセル')).toBeInTheDocument();
    });

    it('confirmLabel / cancelLabel を上書きできる', () => {
        const { getByText } = render(
            <ConfirmDialog
                open
                title="t"
                message="m"
                confirmLabel="OK"
                cancelLabel="閉じる"
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(getByText('OK')).toBeInTheDocument();
        expect(getByText('閉じる')).toBeInTheDocument();
    });

    it('confirm ラベルクリックで onConfirm が呼ばれる', () => {
        const onConfirm = vi.fn();
        const { getByText } = render(
            <ConfirmDialog open title="t" message="m" onConfirm={onConfirm} onCancel={() => {}} />,
        );
        fireEvent.click(getByText('実行'));
        expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it('cancel ラベルクリックで onCancel が呼ばれる', () => {
        const onCancel = vi.fn();
        const { getByText } = render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={onCancel} />,
        );
        fireEvent.click(getByText('キャンセル'));
        expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('Esc キーで onCancel が呼ばれる（Dialog の onClose=onCancel として渡している）', () => {
        const onCancel = vi.fn();
        render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={onCancel} />,
        );
        fireEvent.keyDown(window, { key: 'Escape' });
        expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('danger=true で OK ボタンが赤系（bg-red-600）になる', () => {
        const { getByText } = render(
            <ConfirmDialog
                open
                title="t"
                message="m"
                danger
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(getByText('実行').className).toContain('bg-red-600');
    });

    it('danger=false（既定）で OK ボタンは primary 系', () => {
        const { getByText } = render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={() => {}} />,
        );
        expect(getByText('実行').className).toContain('bg-primary-600');
    });

    it('複数行 message が whitespace-pre-line で表示される', () => {
        const { getByText } = render(
            <ConfirmDialog
                open
                title="t"
                message={'1 行目\n2 行目'}
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        const p = getByText(/1 行目/);
        expect(p.className).toContain('whitespace-pre-line');
    });
});
