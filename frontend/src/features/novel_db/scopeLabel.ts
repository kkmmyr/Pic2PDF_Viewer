import type { Scope, ScopeType } from './types';

/**
 * スコープ種別 + ID から表示ラベルを生成する（例: 全件 / シリーズ: xxx / 単冊: xxx）。
 * scope種別の表示名を画面間で統一する。
 */
export function formatScopeLabel(type: ScopeType, id?: string | null): string {
    if (type === 'series') return `シリーズ: ${id ?? ''}`;
    if (type === 'book') return `単冊: ${id ?? ''}`;
    return '全件';
}

/** Scope オブジェクトから表示ラベルを生成する（formatScopeLabel の薄いラッパー）。 */
export function scopeLabel(scope: Scope): string {
    return formatScopeLabel(scope.type, scope.id);
}
