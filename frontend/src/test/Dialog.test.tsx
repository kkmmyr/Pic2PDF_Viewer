import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import {
    Dialog,
    DialogBody,
    DialogFooter,
    DialogCancelButton,
    DialogPrimaryButton,
} from '../components/ui/Dialog';

describe('Dialog', () => {
    it('open=false で何もレンダリングしない', () => {
        const { container } = render(
            <Dialog open={false} title="t" onClose={() => {}}>
                <div>body</div>
            </Dialog>,
        );
        expect(container.firstChild).toBeNull();
    });

    it('open=true で title と children が表示される', () => {
        const { getByText } = render(
            <Dialog open title="フォルダ作成" onClose={() => {}}>
                <div>本文</div>
            </Dialog>,
        );
        expect(getByText('フォルダ作成')).toBeInTheDocument();
        expect(getByText('本文')).toBeInTheDocument();
    });

    it('subtitle が指定されると表示される', () => {
        const { getByText } = render(
            <Dialog open title="t" subtitle="3 冊適用" onClose={() => {}}>
                <div />
            </Dialog>,
        );
        expect(getByText('3 冊適用')).toBeInTheDocument();
    });

    it('Escape キーで onClose が呼ばれる', () => {
        const onClose = vi.fn();
        render(
            <Dialog open title="t" onClose={onClose}>
                <div />
            </Dialog>,
        );
        fireEvent.keyDown(window, { key: 'Escape' });
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('Escape 以外のキーでは onClose が呼ばれない', () => {
        const onClose = vi.fn();
        render(
            <Dialog open title="t" onClose={onClose}>
                <div />
            </Dialog>,
        );
        fireEvent.keyDown(window, { key: 'Enter' });
        fireEvent.keyDown(window, { key: 'a' });
        expect(onClose).not.toHaveBeenCalled();
    });

    it('open=false の間は Esc を押しても onClose は呼ばれない', () => {
        const onClose = vi.fn();
        render(
            <Dialog open={false} title="t" onClose={onClose}>
                <div />
            </Dialog>,
        );
        fireEvent.keyDown(window, { key: 'Escape' });
        expect(onClose).not.toHaveBeenCalled();
    });

    it('外クリック（オーバーレイ自身）で onClose が呼ばれる', () => {
        const onClose = vi.fn();
        const { container } = render(
            <Dialog open title="t" onClose={onClose}>
                <div>body</div>
            </Dialog>,
        );
        const overlay = container.firstChild as HTMLElement;
        fireEvent.click(overlay);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('内側クリックでは onClose が呼ばれない（target !== currentTarget）', () => {
        const onClose = vi.fn();
        const { getByText } = render(
            <Dialog open title="t" onClose={onClose}>
                <div>body</div>
            </Dialog>,
        );
        fireEvent.click(getByText('body'));
        expect(onClose).not.toHaveBeenCalled();
    });

    it('×ボタン（aria-label="閉じる"）クリックで onClose', () => {
        const onClose = vi.fn();
        const { getByLabelText } = render(
            <Dialog open title="t" onClose={onClose}>
                <div />
            </Dialog>,
        );
        fireEvent.click(getByLabelText('閉じる'));
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('nested=true で z-dialog-nested クラスが付く', () => {
        const { container } = render(
            <Dialog open title="t" nested onClose={() => {}}>
                <div />
            </Dialog>,
        );
        expect((container.firstChild as HTMLElement).className).toContain('z-dialog-nested');
    });

    it('nested 既定は z-dialog（z-dialog-nested ではない）', () => {
        const { container } = render(
            <Dialog open title="t" onClose={() => {}}>
                <div />
            </Dialog>,
        );
        const cls = (container.firstChild as HTMLElement).className;
        expect(cls).toContain('z-dialog');
        expect(cls).not.toContain('z-dialog-nested');
    });

    it('maxWidth=md で max-w-md', () => {
        const { container } = render(
            <Dialog open title="t" maxWidth="md" onClose={() => {}}>
                <div />
            </Dialog>,
        );
        expect(container.querySelector('.max-w-md')).not.toBeNull();
    });

    it('maxWidth 既定は sm', () => {
        const { container } = render(
            <Dialog open title="t" onClose={() => {}}>
                <div />
            </Dialog>,
        );
        expect(container.querySelector('.max-w-sm')).not.toBeNull();
    });
});

describe('Dialog のサブコンポーネント', () => {
    it('DialogBody は children を描画', () => {
        const { getByText } = render(<DialogBody>本文</DialogBody>);
        expect(getByText('本文')).toBeInTheDocument();
    });

    it('DialogFooter は children を描画', () => {
        const { getByText } = render(<DialogFooter>OK</DialogFooter>);
        expect(getByText('OK')).toBeInTheDocument();
    });

    it('DialogCancelButton 既定ラベルは "キャンセル"', () => {
        const onClick = vi.fn();
        const { getByRole } = render(<DialogCancelButton onClick={onClick} />);
        expect(getByRole('button').textContent).toBe('キャンセル');
        fireEvent.click(getByRole('button'));
        expect(onClick).toHaveBeenCalled();
    });

    it('DialogCancelButton で children を上書きできる', () => {
        const { getByRole } = render(
            <DialogCancelButton onClick={() => {}}>戻る</DialogCancelButton>,
        );
        expect(getByRole('button').textContent).toBe('戻る');
    });

    it('DialogCancelButton disabled で onClick されない', () => {
        const onClick = vi.fn();
        const { getByRole } = render(<DialogCancelButton onClick={onClick} disabled />);
        fireEvent.click(getByRole('button'));
        expect(onClick).not.toHaveBeenCalled();
    });

    it('DialogPrimaryButton クリックで onClick が呼ばれる', () => {
        const onClick = vi.fn();
        const { getByRole } = render(
            <DialogPrimaryButton onClick={onClick}>送信</DialogPrimaryButton>,
        );
        fireEvent.click(getByRole('button'));
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('DialogPrimaryButton disabled で onClick されない', () => {
        const onClick = vi.fn();
        const { getByRole } = render(
            <DialogPrimaryButton onClick={onClick} disabled>
                送信
            </DialogPrimaryButton>,
        );
        fireEvent.click(getByRole('button'));
        expect(onClick).not.toHaveBeenCalled();
    });
});
