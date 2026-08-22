# 小説RAG — 現行技術知見

> status: living | last-verified: 2026-08-22

本書は、現在のモデル・検索・運用判断へ短時間で到達するための要約である。
時系列のベンチマーク、失敗した候補、個別試行の数値は
[小説RAG 技術検証履歴](../../archive/検証/小説RAG_技術検証履歴.md)へ凍結した。
仕様は[データ設計](../../design/詳細設計/機能別/小説RAG_データ.md)、
[パイプライン設計](../../design/詳細設計/機能別/小説RAG_パイプライン設計.md)、
[検索QA設計](../../design/詳細設計/機能別/小説RAG_検索QA設計.md)を正本とする。

## 1. 現行推奨構成

| 環境・役割 | 現行選択 | 備考 |
|---|---|---|
| Windows/Linux 主生成・QA | Qwen3.6 35B-A3B + llama-server | 既定経路。長文は131,072 context、生成は直列 |
| Mac 主生成・QA | Qwen3.6 35B-A3B MLX | Apple Siliconのopt-in。公開前品質ゲートは同じ |
| 補助抽出・query expansion | Gemma 4 12B Ollama | MacでもMLXへ切り替えない |
| Embedding | bge-m3 | Ollama既定。Mac MLXはFP16 + CLS poolingのみ互換採用 |
| lexical検索 | SQLite FTS5 | 本番既定。page-level LanceDB ICUはshadow観測中 |
| dense検索 | bge-m3 chunk KNN | lexicalとのRRFを維持 |

モデル・backend・port・環境変数の値は
[小説RAG データ設計](../../design/詳細設計/機能別/小説RAG_データ.md)を正本とし、
本書へ複写しない。

## 2. 品質上の不変条件

- thinkingを有効にした事実だけでは品質を保証しない。自然停止、根拠、意味精度を別々に判定する。
- transport smoke、JSON parse成功、メモリ内ロード成功を本番品質合格として扱わない。
- 長文全体の入力が可能でも、終盤事実・主体・時系列の統合誤りは残る。
- 完成要約は構造検査だけで公開せず、主張単位の根拠照合と重要事実欠落検査を通す。
- 同じholdoutを調整と採用判定へ繰り返し使わない。
- OCR本文・索引・公開要約は別の成果物としてrollback可能にする。

## 3. Qwen運用

- Windowsの採用起動値は`-c 131072 -ncmoe 28`を基準とする。
- KV cache量子化とngram speculative decodingは速度改善に使えるが、意味精度を改善するものではない。
- `enable_thinking`、sampling、presence/repetition penaltyの転送漏れで品質と停止条件が変わる。
- 1冊全文がcontextへ収まっても、一覧向け要約や人物同定は根拠検査を省略しない。
- Qwen3.8は抽出構造を部分改善したが、固定小説ケースではQwen3.6の完成要約を置換しない。

## 4. Apple Silicon MLX

- M1 Max 64GBではQwen3.6 35B-A3B、bge-m3、比較用30B級モデルを実行できる。
- bge-m3 MLXは`1_Pooling/config.json`でCLS poolingを固定する。mean poolingは不採用。
- Qwenと別生成モデルを同じcacheへ同時常駐・同時生成させない。
- Qwen3.8の`mlx-dspark`経路はQA・比較専用で、永続生成jobと自動公開を拒否する。
- 詳細な決定は[ADR-0019](../../design/基本設計/ADR/0019_apple-silicon-mlx-inference.md)、
  起動手順は[GPU環境セットアップ](../../design/環境構築/GPU環境セットアップ.md)を参照する。

## 5. 比較候補の現在判断

| 候補 | 判断 | 再評価する条件 |
|---|---|---|
| Gemma 4 12B MLX | 不採用 | 変換weight/template更新後にOllamaを非劣化で上回る |
| Qwen3.8-27B | 比較限定 | 根拠・意味・自然停止の固定ゲート合格 |
| Nemotron 75B | 不採用 | 固定小説ケースと長文根拠精度の改善 |
| Nemotron 30B | 不採用 | thinking効率と長文抽出精度の同時改善 |
| Ornith 1.5 35B-A3B | 不採用 | 20ページ入力で自然停止し、日本語意味ゲート合格 |
| Muse Glimmer 30B | 補助比較のみ | 短窓以外で現行役割を明確に上回る |

64GB不足だけを不合格理由にしない。ロード可否、token速度、停止、形式、意味、根拠を分けて記録する。

## 6. 検索の現在判断

- dense大型化より先に、日本語lexical検索の0-hitを減らす。
- page-level LanceDB ICU BM25は固定20問と封印12問でFTS5を大きく上回り、個別Recall回帰0件だった。
- ただし本番切替はshadow実利用観測と利用者の別承認を残す。既定はFTS5のまま。
- ICU世代はSQLite全対象から完全再構築し、件数・ID・source hash・tokenizerをmanifestで検証する。
- stale、不整合、LanceDB例外時はFTS5へfail closedで縮退する。
- 正式契約と切替手順は[検索QA設計 §10](../../design/詳細設計/機能別/小説RAG_検索QA設計.md#rag-search-evaluation)と
  [ADR-0020](../../design/基本設計/ADR/0020_page-level-lancedb-icu-shadow.md)を参照する。

## 7. トラブルシューティングの順序

1. 入力文字数・token数・context上限・出力上限を分けて確認する。
2. backend、model、chat template、thinking、sampling、seedを記録する。
3. JSON/停止違反と意味不正解を別の失敗理由にする。
4. retrieval単体で正解ページが候補へ入るか確認してからLLMを疑う。
5. 公開前ゲート不合格時は候補を監査保存し、旧公開版を維持する。

## 8. 履歴を参照する場合

モデル別の実測、採否の詳細、過去の速度表、B-36の試行錯誤は
[小説RAG 技術検証履歴](../../archive/検証/小説RAG_技術検証履歴.md)を参照する。
履歴の数値を現在の推奨値として再利用するときは、runtime・model revision・hardware・
prompt・samplingが一致するかを再確認する。
