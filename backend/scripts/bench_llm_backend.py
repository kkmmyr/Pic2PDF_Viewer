"""LLM 推論バックエンド (Ollama / llama-server) のベンチマーク。

B-14 / ADR-0009 採用時に Phase 0〜4b として手動実行したベンチを統合し、再現
可能な形で残したもの。共通 `local_llm` パッケージの `OllamaBackend` /
`LlamaServerBackend` を直接 instantiate して同じプロンプトで叩き、
`prompt_eval_count` / `eval_count` / 応答時間を比較する。

3 種類のプロンプトサイズで warm-up + 計測 1 回ずつを流す:
    - A_short (~120 tok in)  - 単冊・短文 RAG
    - B_mid   (~2k tok in)   - 単冊・中文 RAG
    - C_long  (~13k tok in)  - scope=all + 全 11 冊サマリ模擬

使用例:
    cd backend
    uv run python scripts/bench_llm_backend.py --backend llama_server
    uv run python scripts/bench_llm_backend.py --backend ollama
    uv run python scripts/bench_llm_backend.py --compare  # 両 backend の JSON を比較

結果は `backend/scripts/results/bench_{backend}.json` に保存される。

注意:
    - llama_server backend は事前に llama-server が `--port 11435` で稼働している必要
      （Windows タスクスケジューラ `llama-server-qwen` で自動起動）
    - ollama backend は VRAM 競合に注意（gemma4:e4b 等が常駐していると OOM の可能性）
    - 採用時の実機ベンチ結果は docs/05_記録/小説RAG_技術知見.md §9 を参照
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 共通 LLM パッケージ（A-1 で qwen_client → local_llm に再構築）
_LLM_PKG_DIR = r"D:\61.tool\common\llm"
if _LLM_PKG_DIR not in sys.path:
    sys.path.insert(0, _LLM_PKG_DIR)

from local_llm import (  # noqa: E402
    Backend,
    BackendConfig,
    LlamaServerBackend,
    OllamaBackend,
)

from config import NOVEL_DB_QA_NUM_CTX  # noqa: E402

DEFAULT_MODEL = "qwen3.6-iq4xs"
NUM_PREDICT = 256       # tg 計測の安定化のため短めに固定
TEMPERATURE = 0.2
REPEAT_PENALTY = 1.2

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# プロンプト 3 種類（novel_db の PROMPT_TEMPLATE 構造を模擬）
# ---------------------------------------------------------------------------

PROMPT_SHORT = """以下は小説『サンプル書籍』からの抜粋です。
これを参考にして質問に答えてください。

【回答ルール】
- 根拠としたページ番号を必ず明記してください。
- 簡潔に 100 字以内で答えてください。

[page 12]
主人公のアリスは森の入口に立っていた。彼女は祖母から受け取った手紙を握りしめ、
意を決して足を踏み入れた。

質問: アリスは何を持って森に入ったか？

回答:"""

_MID_PAGE_TEMPLATE = """[page {page}, 主要登場人物: 太郎, 花子]
{page} ページ目の本文サンプル。物語はここから動き始める。太郎は窓辺に立ち、遠くに見える山々を眺めながら過去を回想していた。
昔、彼はこの町を離れる決心をした。だが、花子との約束だけが心残りだった。「いつか必ず戻る」と告げたあの日の夕暮れを、
彼はまだ忘れていない。十年が経ち、彼はようやくこの地に戻ってきた。しかし、町の風景は様変わりしていた。古い駅舎は
取り壊され、代わりに無機質なガラス張りの建物が立っていた。商店街もシャッターを下ろした店が目立ち、彼が知っていた
温かみは消えていた。それでも、彼は花子を探し続けた。喫茶店で聞き込みをし、図書館で名簿を調べ、ようやく彼女が町外れ
の小さな診療所で働いていることを突き止めた。診療所の扉を押し開けたとき、彼の心臓は十年ぶりの再会を前に高鳴った。"""

PROMPT_MID = """以下は小説『中程度サンプル』からの抜粋です。
これを参考にして質問に答えてください。

【回答ルール】
- 根拠としたページ番号を必ず明記してください（例: 「page 50 に記述あり」）。
- 引用する際は、誰の発言・行動・心情かを必ず明記してください。
- 抜粋に直接の記述がなくても、関連する複数の記述から推論して構いません。

""" + "\n\n".join(_MID_PAGE_TEMPLATE.format(page=p) for p in (12, 34, 58, 79, 102, 145, 188, 221)) + """

質問: 太郎が町に戻ってきた理由を本文中の記述から推論してください。

回答:"""

_LONG_SUMMARY = """■ サンプル書籍1
本書はある町を舞台に、主人公太郎が過去の約束を果たすために十年ぶりに帰郷する物語である。
町は変貌していたが、彼は粘り強く花子を探し、最終的に町外れの診療所で再会を果たす。
作中では、変わりゆく地方都市の風景と、変わらぬ人々の感情の対比が繰り返し描かれる。
特に、駅舎の取り壊しと喫茶店マスターの変わらぬ笑顔の対比は象徴的である。終盤では、
花子が長年抱えていた秘密 — 太郎の弟との関係 — が明かされ、物語は予想外の方向へと展開する。
読者はここで初めて、太郎が町を離れた本当の理由を知ることになる。
"""

PROMPT_LONG = """以下は小説からの抜粋です。
これを参考にして質問に答えてください。

【書籍俯瞰サマリ】（各書籍の事前生成あらすじ。背景知識として活用）
""" + (_LONG_SUMMARY * 6) + """

【回答ルール】
- 根拠としたページ番号を必ず明記してください（例: 「page 50 に記述あり」）。
- 引用する際は、誰の発言・行動・心情かを必ず明記してください。
- 質問が抽象的・概括的な場合は、具体的なシーン・出来事を 3 つ以上挙げて構造的に
  深く分析してください。

""" + "\n\n".join(_MID_PAGE_TEMPLATE.format(page=p) for p in range(10, 410, 13)) + """

質問: この物語群に共通するテーマと、それを象徴する具体的なシーンを 3 つ挙げて分析してください。

回答:"""


CASES = [
    ("A_short", PROMPT_SHORT),
    ("B_mid", PROMPT_MID),
    ("C_long", PROMPT_LONG),
]


# ---------------------------------------------------------------------------
# 1 回計測
# ---------------------------------------------------------------------------

def _run_once(label: str, prompt: str, backend: Backend, model: str) -> dict:
    """1 リクエストを投げて Ollama 形式の最終イベントから統計を取り出す。

    `local_llm` の Backend が両系統で同じ形式（`response` / `done`
    / `prompt_eval_count` / `eval_count`）に正規化してくれるため、ここでは
    backend 種別を意識しない。

    `tg_t_per_s` の意味（重要）:
        - **OllamaBackend**: `eval_count / eval_duration` = 純粋な生成速度（プロンプト処理時間を除く）
        - **LlamaServerBackend**: `eval_count / elapsed` = end-to-end 速度（プロンプト処理込み）
            * OpenAI 互換 SSE は `timings` フィールドを返さないため
            * 純粋な生成速度を知りたい場合は llama-server を `/v1/chat/completions`
              に **非ストリーミング**で叩いて `timings.predicted_per_second` を読む
              （ADR-0009 の引用値はこの方式で取得した）
    """
    options = {
        "temperature": TEMPERATURE,
        "repeat_penalty": REPEAT_PENALTY,
        "num_predict": NUM_PREDICT,
        # 本番 QA と同じ num_ctx を使う（config.NOVEL_DB_QA_NUM_CTX）。
        # 段階 A=16384 / 段階 B=32768 などの切替に追従。LlamaServerBackend では
        # 起動時 -c で決まるためここの値は無視されるが、OllamaBackend では効く
        "num_ctx": NOVEL_DB_QA_NUM_CTX,
    }
    print(f"\n--- {label} (prompt_chars={len(prompt)}) ---", flush=True)
    start = time.time()
    final: dict = {}
    response_parts: list[str] = []
    for event in backend.stream_ask(prompt, model=model, options=options, think=False, timeout=600):
        if event.get("response"):
            response_parts.append(event["response"])
        if event.get("done"):
            final = event
            break
    elapsed = time.time() - start
    response = "".join(response_parts)

    pec = final.get("prompt_eval_count") or 0
    ped_ns = final.get("prompt_eval_duration") or 0
    ec = final.get("eval_count") or 0
    ed_ns = final.get("eval_duration") or 0

    # llama_server は duration を返さないため、elapsed の比例配分で近似する。
    # （pp は入力 tok の重み、tg は出力 tok の重みで割り振り）
    if pec and not ped_ns and ec and not ed_ns:
        tg_t_per_s = ec / elapsed if elapsed else 0
        pp_t_per_s = 0.0  # 近似困難なので 0 として明示
    else:
        pp_t_per_s = pec / (ped_ns / 1e9) if ped_ns else 0.0
        tg_t_per_s = ec / (ed_ns / 1e9) if ed_ns else 0.0

    tg_label = "tg" if ped_ns else "tg*"  # * = end-to-end approximation
    print(
        f"  in: {pec:>6} tok, out: {ec:>4} tok, "
        f"pp={pp_t_per_s:>6.1f} t/s, {tg_label}={tg_t_per_s:>6.1f} t/s, "
        f"elapsed={elapsed:>5.2f}s",
    )
    return {
        "label": label,
        "prompt_chars": len(prompt),
        "in_tok": pec,
        "out_tok": ec,
        "pp_t_per_s": pp_t_per_s,
        "tg_t_per_s": tg_t_per_s,
        "elapsed_s": elapsed,
        "response_first_120": response[:120],
        "response_chars": len(response),
    }


# ---------------------------------------------------------------------------
# 1 backend を回す
# ---------------------------------------------------------------------------

def _make_backend(kind: str, *, model: str, llama_url: str) -> Backend:
    """ベンチ対象の Backend を 1 つ作る。

    URL は CLI フラグ (`--llama-url`) で上書き可。Ollama 側は localhost:11434 固定
    （bench で叩く対象を変えるユースケースが無いため）。
    """
    cfg_model = model
    if kind == "llama_server":
        return LlamaServerBackend(BackendConfig(base_url=llama_url, model=cfg_model))
    if kind == "ollama":
        return OllamaBackend(BackendConfig(
            base_url="http://localhost:11434", model=cfg_model,
        ))
    raise ValueError(f"unknown backend kind: {kind}")


def run_backend(kind: str, *, model: str, llama_url: str) -> dict:
    """backend を切り替えて 3 ケース実走。各ケース warm-up + 計測 1 回。"""
    backend = _make_backend(kind, model=model, llama_url=llama_url)
    print(f"\n=== Bench: backend={kind}, model={model} ===", flush=True)

    results: list[dict] = []
    for label, prompt in CASES:
        _run_once(f"{label} [warmup]", prompt, backend, model)
        r = _run_once(f"{label} [measure]", prompt, backend, model)
        results.append(r)

    return {"backend": kind, "model": model, "results": results}


def _summary_table(results: list[dict]) -> str:
    # llama_server は eval_duration を返さないため tg は end-to-end 近似（脚注 *）
    lines = [
        f"{'case':<10} {'in_tok':>7} {'pp t/s':>9} {'out_tok':>7} {'tg t/s*':>9} {'elapsed s':>11}",
    ]
    for r in results:
        lines.append(
            f"{r['label']:<10} {r['in_tok']:>7} {r['pp_t_per_s']:>9.1f} "
            f"{r['out_tok']:>7} {r['tg_t_per_s']:>9.1f} {r['elapsed_s']:>11.2f}",
        )
    lines.append("(*) llama_server は eval_duration を返さないため end-to-end (out_tok/elapsed) で近似")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 比較モード
# ---------------------------------------------------------------------------

def compare(ollama_path: Path, llama_path: Path) -> None:
    """両 backend の JSON を読み比較表示する。"""
    if not ollama_path.exists() or not llama_path.exists():
        missing = [p for p in (ollama_path, llama_path) if not p.exists()]
        print(f"[error] missing result file(s): {missing}", file=sys.stderr)
        sys.exit(1)

    ollama = json.loads(ollama_path.read_text(encoding="utf-8"))
    llama = json.loads(llama_path.read_text(encoding="utf-8"))

    print(f"\n=== Compare: {ollama_path.name} vs {llama_path.name} ===")
    print(
        f"\n{'case':<10} {'ollama tg':>10} {'llama tg':>10} {'tg×':>6} "
        f"{'ollama s':>10} {'llama s':>10} {'speedup':>8}",
    )
    for o, l in zip(ollama["results"], llama["results"]):
        tg_ratio = l["tg_t_per_s"] / o["tg_t_per_s"] if o["tg_t_per_s"] else 0
        speedup = o["elapsed_s"] / l["elapsed_s"] if l["elapsed_s"] else 0
        print(
            f"{o['label']:<10} {o['tg_t_per_s']:>10.1f} {l['tg_t_per_s']:>10.1f} "
            f"{tg_ratio:>5.2f}× {o['elapsed_s']:>10.2f} {l['elapsed_s']:>10.2f} "
            f"{speedup:>7.2f}×",
        )


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--backend", choices=["ollama", "llama_server"],
        help="ベンチ対象の backend。--compare 時は不要",
    )
    ap.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"モデル名（既定: {DEFAULT_MODEL}）",
    )
    ap.add_argument(
        "--llama-url", default="http://127.0.0.1:11435",
        help="llama-server の base URL（backend=llama_server 時）",
    )
    ap.add_argument(
        "--out", type=Path, default=None,
        help="JSON 出力先（既定: backend/scripts/results/bench_{backend}.json）",
    )
    ap.add_argument(
        "--compare", action="store_true",
        help="既存 JSON を比較表示。--out で 2 ファイルを指定するか、既定パスを使う",
    )
    ap.add_argument("--ollama-json", type=Path, default=RESULTS_DIR / "bench_ollama.json")
    ap.add_argument("--llama-json", type=Path, default=RESULTS_DIR / "bench_llama_server.json")
    args = ap.parse_args()

    if args.compare:
        compare(args.ollama_json, args.llama_json)
        return 0

    if not args.backend:
        ap.error("--backend is required when not in --compare mode")

    result = run_backend(args.backend, model=args.model, llama_url=args.llama_url)

    out_path = args.out or (RESULTS_DIR / f"bench_{args.backend}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out_path}")

    print(f"\n=== Summary ({args.backend}) ===")
    print(_summary_table(result["results"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
