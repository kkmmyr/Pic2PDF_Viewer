import { type ReactNode } from 'react';
import { AlertCircle, CheckCircle, AlertTriangle, Info } from 'lucide-react';

type AlertVariant = 'error' | 'success' | 'warning' | 'info';

interface AlertProps {
    variant: AlertVariant;
    /** アイコン上書き。指定なしなら variant の既定アイコン。 */
    icon?: ReactNode;
    /** false にするとアイコン非表示。既定 true。 */
    showIcon?: boolean;
    /** 追加クラス（外側余白の調整に使う、`mt-3` / `mb-4` / `p-4` など）。 */
    className?: string;
    children: ReactNode;
}

const VARIANT_CLASS: Record<AlertVariant, string> = {
    error:   'bg-red-50 border-red-200 text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400',
    success: 'bg-green-50 border-green-200 text-green-700 dark:bg-green-900/20 dark:border-green-800 dark:text-green-400',
    warning: 'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-900/20 dark:border-amber-700 dark:text-amber-300',
    info:    'bg-primary-50 border-primary-200 text-primary-700 dark:bg-primary-900/20 dark:border-primary-800 dark:text-primary-300',
};

const DEFAULT_ICON: Record<AlertVariant, ReactNode> = {
    error:   <AlertCircle    className="w-4 h-4 shrink-0 mt-0.5" />,
    success: <CheckCircle    className="w-4 h-4 shrink-0 mt-0.5" />,
    warning: <AlertTriangle  className="w-4 h-4 shrink-0 mt-0.5" />,
    info:    <Info           className="w-4 h-4 shrink-0 mt-0.5" />,
};

const BASE_CLASS = 'flex items-start gap-2 p-3 rounded-lg border text-sm';

export function Alert({ variant, icon, showIcon = true, className = '', children }: AlertProps) {
    const classes = `${BASE_CLASS} ${VARIANT_CLASS[variant]} ${className}`.trim();
    const iconNode = showIcon ? (icon ?? DEFAULT_ICON[variant]) : null;
    return (
        <div className={classes} role={variant === 'error' ? 'alert' : 'status'}>
            {iconNode}
            <div className="min-w-0 flex-1">{children}</div>
        </div>
    );
}
