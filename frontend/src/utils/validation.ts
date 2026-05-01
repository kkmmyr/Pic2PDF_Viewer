/**
 * ファイル名・フォルダ名のバリデーションユーティリティ。
 *
 * Windows / macOS / Linux で使用できないファイル名文字を共通の正規表現で除外する。
 * 各ダイアログ（CreateFolderDialog / RenameDialog / MergeDialog）から共有される。
 */

/** ファイル名・フォルダ名に使えない文字 */
const FORBIDDEN_FILENAME_CHARS = /[/\\:*?"<>|]/;

/** 表示用の禁止文字一覧（エラーメッセージに使う） */
const FORBIDDEN_CHARS_DISPLAY = '/ \\ : * ? " < > |';

export type FilenameKind = 'file' | 'folder';

/**
 * ファイル名/フォルダ名をバリデーションし、エラーがあればメッセージを返す。
 * 問題なければ null を返す。
 */
export function validateFilename(value: string, kind: FilenameKind): string | null {
    if (!value.trim()) {
        return `${kind === 'folder' ? 'フォルダ名' : 'ファイル名'}を入力してください。`;
    }
    if (FORBIDDEN_FILENAME_CHARS.test(value)) {
        return `使用できない文字が含まれています: ${FORBIDDEN_CHARS_DISPLAY}`;
    }
    return null;
}
