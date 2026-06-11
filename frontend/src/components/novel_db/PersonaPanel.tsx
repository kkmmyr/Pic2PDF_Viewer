/**
 * 読書会ペルソナ設定パネル（B-20）。
 * NovelDiscussionPage のペルソナ A / B 設定 UI を切り出したサブコンポーネント。
 */

const READING_STYLES = ['批評家', 'ファン', '懐疑派'] as const;
const TONES = ['敬語丁寧', 'フランク', '関西弁風'] as const;
const PERSPECTIVES = ['文学評論', '感情重視', 'ロジック重視'] as const;

export interface PersonaState {
    name: string;
    readingStyle: string;
    tone: string;
    perspective: string;
    useCustom: boolean;
    customDesc: string;
}

export function buildStyleDesc(p: PersonaState): string {
    if (p.useCustom) return p.customDesc.trim();
    return [p.readingStyle, p.tone, p.perspective].filter(Boolean).join('・');
}

interface PresetRowProps {
    label: string;
    options: readonly string[];
    value: string;
    onChange: (v: string) => void;
    disabled?: boolean;
}

function PresetRow({ label, options, value, onChange, disabled }: PresetRowProps) {
    return (
        <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs text-gray-400 dark:text-gray-500 w-14 shrink-0">{label}</span>
            {options.map((opt) => (
                <button
                    key={opt}
                    type="button"
                    onClick={() => onChange(opt)}
                    disabled={disabled}
                    className={`text-xs px-2 py-0.5 rounded-full border transition-colors disabled:opacity-50 ${
                        value === opt
                            ? 'bg-accent-600 border-accent-600 text-white dark:bg-accent-500 dark:border-accent-500'
                            : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-accent-400'
                    }`}
                >
                    {opt}
                </button>
            ))}
        </div>
    );
}

interface PersonaPanelProps {
    label: string;
    persona: PersonaState;
    onChange: (p: PersonaState) => void;
    disabled?: boolean;
}

export default function PersonaPanel({ label, persona, onChange, disabled }: PersonaPanelProps) {
    const set = (patch: Partial<PersonaState>) => onChange({ ...persona, ...patch });

    return (
        <div className="flex-1 border border-gray-200 dark:border-gray-700 rounded-lg p-3 space-y-2.5">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                {label}
            </p>
            <div>
                <label
                    htmlFor={`persona-name-${label}`}
                    className="text-xs text-gray-500 dark:text-gray-400"
                >
                    名前
                </label>
                <input
                    id={`persona-name-${label}`}
                    type="text"
                    value={persona.name}
                    onChange={(e) => set({ name: e.target.value })}
                    disabled={disabled}
                    className="mt-0.5 w-full text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                    maxLength={50}
                />
            </div>

            <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">スタイル</span>
                <button
                    type="button"
                    onClick={() => set({ useCustom: !persona.useCustom })}
                    disabled={disabled}
                    className="text-xs text-accent-600 dark:text-accent-400 hover:underline disabled:opacity-50"
                >
                    {persona.useCustom ? 'プリセットに戻す' : 'カスタム入力'}
                </button>
            </div>

            {persona.useCustom ? (
                <textarea
                    value={persona.customDesc}
                    onChange={(e) => set({ customDesc: e.target.value })}
                    disabled={disabled}
                    placeholder="例: 哲学的な観点から問い直す、ですます調"
                    rows={2}
                    className="w-full text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50 resize-none"
                    maxLength={200}
                />
            ) : (
                <div className="space-y-1.5">
                    <PresetRow
                        label="読書スタイル"
                        options={READING_STYLES}
                        value={persona.readingStyle}
                        onChange={(v) => set({ readingStyle: v })}
                        disabled={disabled}
                    />
                    <PresetRow
                        label="口調"
                        options={TONES}
                        value={persona.tone}
                        onChange={(v) => set({ tone: v })}
                        disabled={disabled}
                    />
                    <PresetRow
                        label="視点"
                        options={PERSPECTIVES}
                        value={persona.perspective}
                        onChange={(v) => set({ perspective: v })}
                        disabled={disabled}
                    />
                </div>
            )}

            <p className="text-xs text-gray-400 dark:text-gray-500 italic">
                → {buildStyleDesc(persona) || '（未設定）'}
            </p>
        </div>
    );
}
