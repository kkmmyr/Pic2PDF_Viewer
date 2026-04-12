import { useState, useEffect, useMemo } from 'react';
import {
    Dialog, DialogActions, DialogContent, DialogTitle,
    Button, TextField,
} from '@mui/material';

// Windows / Unix で使用できないファイル名文字
const FORBIDDEN_RE = /[/\\:*?"<>|]/;

interface Props {
    open: boolean;
    onClose: () => void;
    onCreate: (name: string) => Promise<void>;
}

/**
 * フォルダ作成ダイアログ。
 * バリデーション（空文字・禁止文字）を行ってから onCreate を呼び出す。
 */
export function CreateFolderDialog({ open, onClose, onCreate }: Props) {
    const [name, setName] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    // ダイアログを閉じるたびに入力をリセット
    useEffect(() => {
        if (!open) {
            setName('');
            setError(null);
        }
    }, [open]);

    const validate = (value: string): string | null => {
        if (!value.trim()) return 'フォルダ名を入力してください。';
        if (FORBIDDEN_RE.test(value)) return '使用できない文字が含まれています: / \\ : * ? " < > |';
        return null;
    };

    const validationError = useMemo(() => validate(name), [name]);
    const isSubmittable = !validationError && !loading;

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setName(e.target.value);
        setError(null);
    };

    const handleCreate = async () => {
        const err = validate(name);
        if (err) { setError(err); return; }

        setLoading(true);
        try {
            await onCreate(name.trim());
            onClose();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'フォルダの作成に失敗しました。');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && isSubmittable) handleCreate();
    };

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
            <DialogTitle>フォルダを作成</DialogTitle>
            <DialogContent>
                <TextField
                    autoFocus
                    fullWidth
                    label="フォルダ名"
                    value={name}
                    onChange={handleChange}
                    onKeyDown={handleKeyDown}
                    error={!!error}
                    helperText={error ?? ' '}
                    sx={{ mt: 1 }}
                />
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={loading}>キャンセル</Button>
                <Button
                    onClick={handleCreate}
                    disabled={!isSubmittable}
                    variant="contained"
                >
                    {loading ? '作成中...' : '作成'}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
