import { ArrowLeft, ImageIcon, Merge, Tag, Library, EyeOff, Eye, ChevronRight, Home, User, BookOpen, Trash2, Layers } from 'lucide-react';
import type { LibrarySource, SortOrder } from '../../types';
import type { GroupMode } from '../../hooks/useLibraryGrouping';
import { HeaderSearchBar } from './HeaderSearchBar';
import { HeaderSortSelect } from './HeaderSortSelect';
import { SourceSelector } from './SourceSelector';
import { ToolsMenu } from '../viewer/ToolsMenu';

export interface LibraryBreadcrumb {
    kind: 'home' | 'author' | 'series';
    label: string;
    /** 指定なしならクリック不可（現在地） */
    onClick?: () => void;
}

interface LibraryHeaderProps {
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedCount: number;
    sortOrder: SortOrder;
    searchText: string;
    authorFilter: string;
    tagFilter: string;
    allAuthors: string[];
    allTags: string[];
    /** ライブラリの集約モード（none / series / author / author-then-series） */
    groupMode: GroupMode;
    /** ドリルダウン中のパンくず（空配列なら非表示）。先頭から順に並び、最後の要素は現在地 */
    breadcrumbs: LibraryBreadcrumb[];
    /** 非表示書籍を表示するモード（ゴミ箱モード） */
    showHidden: boolean;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onBulkSetAuthor: () => void;
    onBulkSetTag: () => void;
    onBulkSetSeries: () => void;
    onBulkSetGenre: () => void;
    onBulkToggleHidden: () => void;
    /** 非表示モード専用: 選択した書籍をディスクから完全削除 */
    onBulkDelete: () => void;
    onRegenThumbnailBulk: () => void;
    onMergePdfs: () => void;
    onSortChange: (order: SortOrder) => void;
    onSearchChange: (text: string) => void;
    onAuthorFilterChange: (author: string) => void;
    onTagFilterChange: (tag: string) => void;
    onGroupModeChange: (mode: GroupMode) => void;
    onToggleShowHidden: () => void;
    /** 未読フィルター（view_count=0 のみ表示） */
    showUnreadOnly: boolean;
    onToggleUnreadOnly: () => void;
    /** ジョブ完了後のメタデータ再取得（ツールメニュー内で利用） */
    onMetaRefresh: () => void;
}

/*
 * ボタンクラスのプリセット（規約: 詳細設計書_フロントエンド編「ボタン色規約」）
 * - Primary: 実行系の主要アクション
 * - Secondary: 中立・補助・取消
 * - Active (Secondary トグルが ON のとき)
 */
const BTN_PRIMARY = 'px-3 py-1.5 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5';
const BTN_SECONDARY = 'px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 flex items-center gap-1.5';
const BTN_SECONDARY_ACTIVE = 'px-3 py-1.5 bg-gray-700 text-white rounded-md text-sm font-medium hover:bg-gray-800 flex items-center gap-1.5';
const BTN_DANGER = 'px-3 py-1.5 bg-red-600 text-white rounded-md text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5';

export function LibraryHeader({
    currentPath,
    currentSource,
    isSelectionMode,
    selectedCount,
    sortOrder,
    searchText,
    authorFilter,
    tagFilter,
    allAuthors,
    allTags,
    groupMode,
    breadcrumbs,
    showHidden,
    onUpClick,
    onSourceChange,
    onToggleSelectionMode,
    onBulkSetAuthor,
    onBulkSetTag,
    onBulkSetSeries,
    onBulkSetGenre,
    onBulkToggleHidden,
    onBulkDelete,
    onRegenThumbnailBulk,
    onMergePdfs,
    onSortChange,
    onSearchChange,
    onAuthorFilterChange,
    onTagFilterChange,
    onGroupModeChange,
    onToggleShowHidden,
    showUnreadOnly,
    onToggleUnreadOnly,
    onMetaRefresh,
}: LibraryHeaderProps) {
    return (
        <div className="sticky top-0 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm shrink-0 z-header">
            {/* 1 段目: ナビゲーション + パンくず + ソース */}
            <div className="h-12 flex items-center px-4 justify-between gap-4">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                    {currentPath && (
                        <button
                            onClick={onUpClick}
                            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full shrink-0"
                        >
                            <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                        </button>
                    )}
                    <h1 className="font-semibold truncate text-gray-900 dark:text-gray-100 shrink-0">
                        {currentPath ? currentPath.split('/').pop() : 'Library'}
                    </h1>
                    {breadcrumbs.length > 0 && (
                        <div className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 min-w-0 overflow-hidden">
                            <span className="text-gray-300 dark:text-gray-600 shrink-0">|</span>
                            {breadcrumbs.map((crumb, i) => {
                                const isLast = i === breadcrumbs.length - 1;
                                const Icon = crumb.kind === 'home' ? Home : crumb.kind === 'author' ? User : Library;
                                const labelEl = (
                                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${
                                        isLast
                                            ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 font-medium'
                                            : crumb.onClick
                                                ? 'hover:bg-gray-200 dark:hover:bg-gray-800 cursor-pointer'
                                                : ''
                                    }`}>
                                        <Icon className="w-3.5 h-3.5" />
                                        <span className="truncate max-w-[180px]">{crumb.label}</span>
                                    </span>
                                );
                                return (
                                    <span key={`${crumb.kind}-${i}`} className="inline-flex items-center gap-1 shrink-0">
                                        {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 shrink-0" />}
                                        {crumb.onClick && !isLast
                                            ? <button onClick={crumb.onClick}>{labelEl}</button>
                                            : labelEl}
                                    </span>
                                );
                            })}
                        </div>
                    )}
                </div>
                <SourceSelector currentSource={currentSource} onSourceChange={onSourceChange} />
            </div>

            {/* 2 段目: 検索 + フィルター + 表示設定 + アクション */}
            <div className="h-12 flex items-center px-4 gap-3 border-t border-gray-100 dark:border-gray-800">
                <HeaderSearchBar
                    searchText={searchText}
                    authorFilter={authorFilter}
                    tagFilter={tagFilter}
                    allAuthors={allAuthors}
                    allTags={allTags}
                    hideAuthorSelect={breadcrumbs.length > 0}
                    onSearchChange={onSearchChange}
                    onAuthorFilterChange={onAuthorFilterChange}
                    onTagFilterChange={onTagFilterChange}
                />

                <div className="flex-1" />

                {/* グループ化 select（ネイティブ select、色は中立） */}
                <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                    <Library className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0" />
                    <select
                        value={groupMode}
                        onChange={(e) => onGroupModeChange(e.target.value as GroupMode)}
                        title="ライブラリの集約表示"
                        /*
                         * select 自身の背景は常に bg-white / dark:bg-gray-800 に固定する。
                         * Chromium では <option> の背景色が <select> の bg を継承し、
                         * かつ CSS で <option> 個別に上書きできないため、<select> 側で
                         * 紫背景にすると <option> がダークモードで読めなくなる。
                         * 紫強調は border + ring + 文字色で表現する。
                         */
                        className={`border rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-400 max-w-[140px] truncate ${
                            groupMode !== 'none'
                                ? 'text-purple-700 dark:text-purple-300 border-purple-400 dark:border-purple-600 ring-1 ring-purple-200 dark:ring-purple-800'
                                : 'text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600'
                        }`}
                    >
                        <option value="none">グループ化なし</option>
                        <option value="series">シリーズで</option>
                        <option value="author">作者で</option>
                        <option value="author-then-series">作者 → シリーズで</option>
                    </select>
                </div>

                <button
                    onClick={onToggleUnreadOnly}
                    title={showUnreadOnly ? '全書籍を表示する' : '未読書籍のみを表示する'}
                    className={showUnreadOnly ? BTN_SECONDARY_ACTIVE : BTN_SECONDARY}
                >
                    <BookOpen className="w-4 h-4" />
                    未読のみ
                </button>

                <button
                    onClick={onToggleShowHidden}
                    title={showHidden ? '通常モードに戻る' : '非表示書籍を表示する（ゴミ箱）'}
                    className={showHidden ? BTN_SECONDARY_ACTIVE : BTN_SECONDARY}
                >
                    {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                    {showHidden ? '通常表示' : '非表示を表示'}
                </button>

                <HeaderSortSelect sortOrder={sortOrder} onSortChange={onSortChange} />

                <ToolsMenu source={currentSource} onComplete={onMetaRefresh} />

                {!isSelectionMode && (
                    <button onClick={onToggleSelectionMode} className={BTN_SECONDARY}>
                        選択
                    </button>
                )}
            </div>

            {/* 3 段目: 選択モード時のみ表示。一括アクションバー */}
            {isSelectionMode && (
                <div className="h-11 flex items-center px-4 gap-2 border-t border-gray-100 dark:border-gray-800 bg-indigo-50/50 dark:bg-indigo-900/10">
                    <span className="text-sm font-medium mr-2 text-gray-700 dark:text-gray-300 shrink-0">
                        {selectedCount} 選択中
                    </span>
                    <button onClick={onBulkSetAuthor} disabled={selectedCount === 0} className={BTN_PRIMARY}>
                        <User className="w-4 h-4" />
                        作者を設定
                    </button>
                    <button onClick={onBulkSetTag} disabled={selectedCount === 0} title="選択した書籍のタグを一括設定" className={BTN_PRIMARY}>
                        <Tag className="w-4 h-4" />
                        タグを設定
                    </button>
                    <button onClick={onBulkSetSeries} disabled={selectedCount === 0} title="選択した書籍をシリーズに一括登録（選択順に採番）" className={BTN_PRIMARY}>
                        <Library className="w-4 h-4" />
                        シリーズに登録
                    </button>
                    <button onClick={onBulkSetGenre} disabled={selectedCount === 0} title="選択した書籍のジャンルを一括設定" className={BTN_PRIMARY}>
                        <Layers className="w-4 h-4" />
                        ジャンルを設定
                    </button>
                    <button
                        onClick={onBulkToggleHidden}
                        disabled={selectedCount === 0}
                        title={showHidden ? '選択した書籍を再表示' : '選択した書籍を非表示'}
                        className={BTN_PRIMARY}
                    >
                        {showHidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                        {showHidden ? 'まとめて再表示' : 'まとめて非表示'}
                    </button>
                    {showHidden && (
                        <button
                            onClick={onBulkDelete}
                            disabled={selectedCount === 0}
                            title="選択した書籍をディスクから完全に削除する（元に戻せません）"
                            className={BTN_DANGER}
                        >
                            <Trash2 className="w-4 h-4" />
                            完全削除
                        </button>
                    )}
                    <button onClick={onMergePdfs} disabled={selectedCount < 2} title="選択した書籍を1つのPDFに結合" className={BTN_PRIMARY}>
                        <Merge className="w-4 h-4" />
                        結合
                    </button>
                    <button onClick={onRegenThumbnailBulk} disabled={selectedCount === 0} title="選択した書籍のサムネイルを再生成" className={BTN_PRIMARY}>
                        <ImageIcon className="w-4 h-4" />
                        サムネイル再生成
                    </button>
                    <div className="flex-1" />
                    <button onClick={onToggleSelectionMode} className={BTN_SECONDARY}>
                        キャンセル
                    </button>
                </div>
            )}
        </div>
    );
}
