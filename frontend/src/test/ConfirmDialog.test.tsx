import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

describe('ConfirmDialog', () => {
    it('open=false で表示されない', () => {
        render(
            <ConfirmDialog
                open={false}
                title="削除"
                message="削除しますか？"
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(screen.queryByRole('alertdialog')).toBeNull();
    });

    it('open=true で title と message が表示される', () => {
        render(
            <ConfirmDialog
                open
                title="削除確認"
                message="本当に削除しますか？"
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(screen.getByText('削除確認')).toBeInTheDocument();
        expect(screen.getByText('本当に削除しますか？')).toBeInTheDocument();
    });

    it('既定の confirmLabel/cancelLabel は "実行" / "キャンセル"', () => {
        render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={() => {}} />,
        );
        expect(screen.getByText('実行')).toBeInTheDocument();
        expect(screen.getByText('キャンセル')).toBeInTheDocument();
    });

    it('confirmLabel / cancelLabel を上書きできる', () => {
        render(
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
        expect(screen.getByText('OK')).toBeInTheDocument();
        expect(screen.getByText('閉じる')).toBeInTheDocument();
    });

    it('confirm ラベルクリックで onConfirm が呼ばれる', () => {
        const onConfirm = vi.fn();
        render(
            <ConfirmDialog open title="t" message="m" onConfirm={onConfirm} onCancel={() => {}} />,
        );
        fireEvent.click(screen.getByText('実行'));
        expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it('cancel ラベルクリックで onCancel が呼ばれる', () => {
        const onCancel = vi.fn();
        render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={onCancel} />,
        );
        fireEvent.click(screen.getByText('キャンセル'));
        expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('Esc キーで onCancel が呼ばれる', () => {
        const onCancel = vi.fn();
        render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={onCancel} />,
        );
        fireEvent.keyDown(document, { key: 'Escape' });
        expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('danger=true で OK ボタンが赤系（bg-red-600）になる', () => {
        render(
            <ConfirmDialog
                open
                title="t"
                message="m"
                danger
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        expect(screen.getByText('実行').className).toContain('bg-red-600');
    });

    it('danger=false（既定）で OK ボタンは primary 系', () => {
        render(
            <ConfirmDialog open title="t" message="m" onConfirm={() => {}} onCancel={() => {}} />,
        );
        expect(screen.getByText('実行').className).toContain('bg-primary-600');
    });

    it('複数行 message が whitespace-pre-line で表示される', () => {
        render(
            <ConfirmDialog
                open
                title="t"
                message={'1 行目\n2 行目'}
                onConfirm={() => {}}
                onCancel={() => {}}
            />,
        );
        const p = screen.getByText(/1 行目/);
        expect(p.className).toContain('whitespace-pre-line');
    });
});
