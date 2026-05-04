/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // セマンティック色トークン（Phase A）
      // 利用例: className="bg-primary-600 text-white" "border-accent-400"
      // primary  = 主 CTA（indigo 系）
      // accent   = グループ化・トグル ON 状態（purple 系）
      // success  = 成功・hitomi 系（emerald 系）
      // surface  = メイン背景 / surface-2 = 副パネル背景
      colors: {
        primary: {
          50:  '#eef2ff', 100: '#e0e7ff', 200: '#c7d2fe', 300: '#a5b4fc',
          400: '#818cf8', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca',
          800: '#3730a3', 900: '#312e81', 950: '#1e1b4b',
        },
        accent: {
          50:  '#faf5ff', 100: '#f3e8ff', 200: '#e9d5ff', 300: '#d8b4fe',
          400: '#c084fc', 500: '#a855f7', 600: '#9333ea', 700: '#7e22ce',
          800: '#6b21a8', 900: '#581c87', 950: '#3b0764',
        },
        success: {
          50:  '#ecfdf5', 100: '#d1fae5', 200: '#a7f3d0', 300: '#6ee7b7',
          400: '#34d399', 500: '#10b981', 600: '#059669', 700: '#047857',
          800: '#065f46', 900: '#064e3b', 950: '#022c22',
        },
      },
      // z-index 階層（カード内バッジ → ヘッダー/オーバーレイ → トースト → ダイアログ）
      // 利用例: className="z-header" "z-dialog" 等
      zIndex: {
        'card-badge':    '10',  // PdfGrid / PageRenderer のチェックボックス・お気に入りバッジ
        'floating-action': '30', // フローティングアクションボタン（「次の巻へ」など）
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

