# ADR-0019: Apple Siliconのローカル推論にMLXを追加する

- **Status**: Accepted
- **Date**: 2026-08-17
- **Last verified**: 2026-09-05
- **決定者**: プロジェクトオーナー
- **関連**: [ADR-0009](0009_llm-backend-llama-server.md) / [小説RAG データ設計](../../詳細設計/機能別/小説RAG_データ.md) / [GPU環境セットアップ](../../環境構築/GPU環境セットアップ.md)

## コンテキスト

M1 Max 64GBのMacでも、小説RAGのQwen・bge-m3をローカル実行したい。
Ollama、llama.cpp、MLXではthinking、sampling、Embedding応答、モデルcacheの契約が異なる。
Windows/Linux本番は安定稼働中であり、Mac対応によって既定経路を変更してはならない。

## 決定

1. MLXをApple Silicon専用の選択可能backendとして採用する。
2. Windows/Linuxの既定は`llama_server` / `ollama`のまま維持する。
3. Macの採用構成はQwen3.6 35B-A3Bとbge-m3をMLX、Gemma 4 12BをOllamaとする。
4. MLX serverは`127.0.0.1`へbindし、生成は同時1件に制限する。
5. bge-m3 MLXはFP16 + CLS poolingを必須とする。mean poolingは既存Ollama索引と
   異なるベクトル空間になるため使用しない。
6. runtime疎通と小説品質を別ゲートにする。transport smokeだけでモデルを本番採用しない。
7. Qwen3.8、Nemotron、Ornith、Graniteなどの比較候補は、固定本文・prompt・sampling・出力上限・
   機械ゲートを揃えた再評価に合格するまでopt-in比較に限定する。
8. Ollamaで128K以上に対応する比較モデルをMacで評価するときは、`num_ctx`をリクエストごとに
   明示し、`ollama ps`で実際のcontext、メモリ使用量、GPU配置を確認する。固定ゲート合格前は
   32,768を基準とし、長文上限だけを理由に64K以上へ拡大しない。

## 採用理由

- Qwen3.6 MLXは固定ケース、構造化出力、長文処理をM1 Max 64GBで完走した。
- bge-m3 FP16 + CLSは既存Ollama embeddingと同一文cosine・検索順位の互換を確認できた。
- Macだけ環境変数で切り替えられ、Windows/Linux本番とrollbackを維持できる。
- MLX化しても長距離の事実統合誤りは残るため、公開成果物の品質ゲートは省略できない。

## 非採用・限定利用

| 候補 | 現在の扱い | 理由 |
|---|---|---|
| Gemma 4 12B MLX | 不採用 | Ollamaより品質・速度が劣り、終端互換にも問題があった |
| Qwen3.8-27B MLX | QA・比較のみ | transportは通るが固定小説品質でQwen3.6を置換できない |
| Nemotron Puzzle 75B | 不採用 | 64GBへロード可能でも固定ケース不合格 |
| Nemotron 30B | 不採用 | thinkingを含む長文抽出の根拠精度・効率が不足 |
| Ornith 1.5 35B-A3B | 不採用 | 短窓schemaは改善したが、長文の停止・日本語意味精度が不合格 |
| Granite 4.2 30B Q4_K_M | 比較のみ | M1 Max 64GBへ22GB・GPU 100%・32Kでロードできたが、固定小説ケースは公式の思考なし0/3、低思考2/3、低温0/3で、途中発言と最終合意の時系列誤認が残った |

## 影響

- MLX runtimeとモデルはrepo外の専用venv・モデルディレクトリで管理する。
- Qwen/Gemmaなど異なる生成モデルを同じcacheで処理中に切り替えない。
- Granite 4.2 30Bはrepo外のOllamaモデルとして比較用に保持し、主生成・既定QA・自動公開へ
  配線しない。公式samplingは`temperature=1.0`、`top_p=0.95`とし、再評価時も対照条件として残す。
- Embedding切替前に1024次元、同一文cosine、旧新交差検索を確認する。
- LanceDB内容の完全性はMLX runtime互換とは別問題であり、page-level ICU索引は
  [ADR-0020](0020_page-level-lancedb-icu-shadow.md)の世代管理・完全再構築契約に従う。

## 再評価条件

- runtime、変換weight、chat templateのいずれかが更新された。
- 固定小説ケースで現行Qwen3.6を非劣化で上回った。
- strict JSON、自然停止、根拠引用、長文終盤保持の全ゲートに合格した。
- メモリ使用量だけでなく、同一入力の意味精度と公開可否を比較した。

詳細な実測値と試行履歴は
[Apple Silicon MLX検証履歴](../../../archive/検証/Apple_Silicon_MLX_検証履歴.md)と
[小説RAG技術知見](../../../log/技術知見/小説RAG_技術知見.md)を参照する。
