import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error('ErrorBoundary caught an error:', error, info);
    }

    render() {
        if (!this.state.hasError) {
            return this.props.children;
        }

        return (
            <div className="flex justify-center items-center min-h-[60vh] p-5">
                <div className="p-10 border-2 border-red-500 rounded-xl max-w-lg w-full text-center bg-white dark:bg-gray-900 shadow-md">
                    <span className="text-5xl block mb-3">⚠️</span>
                    <h2 className="text-red-600 text-2xl font-bold mb-3">エラーが発生しました</h2>
                    <p className="text-gray-500 dark:text-gray-400 mb-6 break-words">
                        {this.state.error?.message ?? '不明なエラーが発生しました。'}
                    </p>
                    <button
                        className="inline-block bg-red-500 text-white px-7 py-2.5 rounded-lg text-base hover:bg-red-600 transition-colors cursor-pointer"
                        onClick={() => window.location.reload()}
                    >
                        再読み込み
                    </button>
                </div>
            </div>
        );
    }
}
