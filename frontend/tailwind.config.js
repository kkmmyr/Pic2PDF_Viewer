/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // z-index 階層（カード内バッジ → ヘッダー/オーバーレイ → トースト → ダイアログ）
      // 利用例: className="z-header" "z-dialog" 等
      zIndex: {
        'card-badge':    '10',  // PdfGrid / PageRenderer のチェックボックス・お気に入りバッジ
        'overlay-bar':   '40',  // ヘッダー下に表示する検索バー / トリガーゾーン
        'header':        '50',  // Layout / ReaderHeader / LibraryHeader
        'toast':         '60',  // トースト通知（ヘッダーより前）
        'dialog':       '100',  // 全ダイアログのオーバーレイ
        'dialog-nested': '200', // ダイアログから開く子ダイアログ
      },
      keyframes: {
        'slide-in-right': {
          '0%': { transform: 'translateX(100%)' },
          '100%': { transform: 'translateX(0)' },
        },
      },
      animation: {
        'slide-in-right': 'slide-in-right 0.2s ease-out',
      },
    },
  },
  plugins: [],
}

