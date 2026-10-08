# Qwen3.6 / MiMo再比較・ローカルLLM候補調査（2026-09-23）

> status: frozen | verified: 2026-09-23 | hardware: Apple M1 Max 64GB

## 目的と結論

「両方」は、現行Qwen3.6 35B-A3BとMiMo V2.6 Distill Qwen 9Bを指すものとして、
固定済み入力、未調整の追加入力、20ページ入力で再比較した。公開DB・索引・通常runtimeには書き込んでいない。

結論は次のとおり。

1. Qwen3.6は品質ゲートをすべて通る万能モデルではない。追加4主張の厳密形式は0/3、
   20ページ出力には話者・ページ帰属と重複の誤りが残り、自動公開できない。
2. それでもQwen3.6は、公式の思考なしsamplingで固定ケース3/3、20ページの書籍・人物両工程を
   合計176.4秒で自然停止し、回答本文を返した。現行主生成としてMiMoより明確に運用へ近い。
3. MiMoはthinkingありの固定ケース3/3と約11.6GBの小さい実行メモリが長所だが、
   20ページ入力では8,192 tokenをreasoningだけに使い、390.8秒後に回答0文字で終了した。
   主生成、既定QA、人物辞典、Qwen3.6置換には採用しない。
4. 公開情報を含めた次の品質優先候補は`llm-jp-4-33b-thinking Q4_K_M`とする。
   日本語向けの別系統モデルとして隔離評価する価値があるが、65,536 contextと専用llama.cpp forkが
   必要なため、131,072 contextの現行主生成を直ちに置換する候補ではない。

## 比較条件

| 項目 | Qwen3.6 | MiMo |
|---|---|---|
| model | Qwen3.6 35B-A3B MLX 4-bit、約19GB | MiMo V2.6 Distill Qwen 9B GGUF Q8_0、9.53GB |
| runtime | MLX 0.32.0 / mlx-lm 0.31.3 / mlx-vlm 0.6.15 | llama.cpp b10360 |
| context / 最大生成 | 32,768 / 8,192 | 32,768 / 8,192 |
| 固定入力 | source `7a44d2…` / prompt `4ce54b…` | 同一 |
| 追加入力 | source `051220…` / prompt `c4d591…` | 同一 |
| 20ページ | source `47f62b…` / prompt `d38f4a…` | 同一 |
| 本番状態の変更 | なし | なし |

完全なhashとrawはrepo外の
`/Users/medaro/.local/share/pic2pdf-llm/evaluations/2026-09-23-qwen-mimo-comparison/`と
`/Users/medaro/.local/share/pic2pdf-llm/evaluations/2026-09-23-mimo/`へ保存した。

## 実測結果

| ゲート | Qwen3.6 | MiMo | 判定 |
|---|---:|---:|---|
| 固定ケース・既存sampling | 2/3 | thinkingなし2/3 | 両方不安定 |
| 固定ケース・推奨条件 | 公式思考なし3/3 | thinkingあり3/3 | 同等 |
| 追加4主張・厳密契約 | 0/3 | 0/3 | 両方不合格 |
| 20ページ・自然停止 | 書籍・人物とも合格 | 8,192 tokenで`length` | Qwen優位 |
| 20ページ・回答本文 | あり | 0文字 | Qwen優位 |
| 20ページ・公開品質 | 不合格 | 不合格 | 両方自動公開不可 |

Qwen3.6の固定ケースは、過去に使った`temperature=0.7 / top_p=0.95 / top_k=40`で2/3、
公式の思考なし条件`temperature=0.7 / top_p=0.8 / top_k=20`で3/3だった。
このruntimeではpresence penaltyを評価スクリプトが転送しないため、公式条件の完全再現ではない。
samplingをモデル名から独立した評価契約として固定する必要がある。

追加4主張では、Qwen3.6は配列を平坦化したり複数配列を連結したりして厳密JSON契約を3件とも外した。
意味面でも、召使いの理由を`contradicted`、外出予定を`insufficient`とする取り違えがあり、
形式修復だけで合格にはならない。MiMoは毎回3/4だったが、根拠ページまたはstatusを外した。

20ページではQwen3.6の書籍生成が79.7秒、人物生成が96.8秒で、両方とも自然停止した。
一方、10ページの台詞を別人物へ帰属し、人物欄を二重出力し、背景情報を誤ったページ・人物へ
結び付けたため公開不可とした。MiMoは16,678入力token後にcompletion 8,192 tokenをすべて
reasoningへ使用し、390.8秒、回答0文字で終了した。

## 公式情報と利用者情報の確認

### Qwen3.6 / MiMo

- [Qwen3.6公式model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)は35B総量・3B active、
  native 262,144 context、思考なしの推奨samplingを案内している。長い公称contextは実アプリの
  日本語事実統合精度を保証しないため、本評価では同一32K条件を使った。
- [MiMo公式model card](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B)は、
  Qwen3.5-9BをMiMo生成データでSFTしたagentic researchの出発点と説明する。
  公開benchmarkはcode・tool・automation中心で、小説RAGや日本語根拠抽出を直接評価していない。
- [MiMoのコミュニティ報告](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Distill-Qwen-9B/discussions/6)には、
  llama.cppでtool callとreasoningのtemplate修正が必要という報告がある。今回の非tool経路は接続できたが、
  長文停止の問題は解消しなかった。

### 次の候補

| 候補 | 公式情報と外部実績 | このアプリでの判断 |
|---|---|---|
| llm-jp-4-33b-thinking Q4_K_M | [公式GGUF](https://huggingface.co/llm-jp/llm-jp-4-33b-thinking-gguf)は33.2B dense、65,536 context、Q4_K_M 20.2GB。公式日本語MT-Benchはmedium 8.00、Q4は8.02 | **次の品質優先候補**。M1 Max 64GBへ収まる見込み。専用llama.cpp fork、thinking parser、65K上限を先に検証する |
| llm-jp-4-32b-a3b-thinking | 32.1B総量・3.83B active。公式日本語MT-Benchはmedium 7.82。非公式の[日本語JSON抽出検証](https://qiita.com/ntaka329/items/7cb7e4565060b9f8691b)は53/57、5回同一 | 速度優先の次点。外部検証は独自データ・vLLM条件なので、本アプリの合格根拠にはしない |
| [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | 新世代だが既存の本アプリ固定試験でQwen3.6を置換できなかった | 再試験を優先しない |
| [Agnes 3.0 Flash](https://huggingface.co/Agnes-AI/Agnes-3.0-Flash) | 公開weightがPreviewで、API版の成績をそのまま利用できない | 公開weight同士の条件が揃うまで保留 |
| MiMo 9B | 小型・高速だが本実測で長文回答0文字 | 不採用 |

LLM-jp 33Bは公式GGUFの注意書きどおり、upstream llama.cppではtokenizer処理が不足してchat parseに失敗する。
LLM-jp forkを隔離buildし、固定ケース、追加4主張、20ページの順に通す。65Kを超える一冊全文は
Qwen3.6経路を維持し、最初は短窓の生成または独立verifierとして比較する。

## 運用判断

- 主生成・既定QA: Qwen3.6を維持する。
- sampling: モデル公式条件を比較基準へ加え、既存値を無条件に流用しない。
- 公開: Qwen3.6を含め、根拠・話者・重複ゲート不合格時は自動公開しない。
- MiMo: runtime/templateまたはcheckpoint更新で長文を8,192 token以内に自然停止できるまで再評価しない。
- 次の隔離評価: llm-jp-4-33b-thinking Q4_K_M。合格前にアプリへ配線しない。
