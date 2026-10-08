# Qwen3.8 MLXランタイム更新・再検証（2026-10-05）

> status: frozen | verified: 2026-10-05 | hardware: Apple M1 Max 64GB

## 結論

Qwen3.8を専用uv環境へ隔離して推論ライブラリを更新し、実HTTP生成を確認した。
通常回答はseedを変えると具体名「栗鼠」の欠落が再現し、品質ゲートNG。
46問・質問holdout・長文への拡大は実施せず、Qwen3.8の比較限定という判断を維持する。

引用方式の小規模診断は固定4問・seed101で本文一致4/4、前後本文補足後の要点4/4だった。
ただしモデル自身の引用選択は1問で具体名を欠落しており、表示の回復は既存の前後本文補足による。
引用方式の複数seed安定性や本番API全体の合格は確認していない。

本作業で本番設定・モデル・DB・索引は変更していない。検証port11441は停止し、
既存11437のQwen3.6がhealthy、Linuxのpic2pdf-viewerがactiveであることを確認した。
利用者が許可した別チャットとのGPU調整は完了通知済み。Ollama更新は未実施。
現行Qwen3.6にも別途未解決の引用エラーがあり、現行本番の全面品質合格とはしない。

## 更新対象

| 対象 | 旧環境 | 隔離環境 |
|---|---|---|
| Python | 3.12.13 | 3.12.13 |
| MLX | 0.32.0 / DSpark側0.32.1 | 0.32.3 |
| MLX-LM | 0.31.3 | 0.32.0 |
| MLX-VLM | 0.6.15 | 0.7.4 |
| MLX-dspark | 0.15.1 | 0.20.2 |
| transformers | 5.15.0 / DSpark側5.15.1 | 5.15.0 |

`uv.lock`とhash付きrequirementsを保存し、58依存の整合性、import、Metal基本演算を確認。
実モデルHTTP生成を検証した経路はDSpark 0.20.2。VLM 0.7.4標準サーバーは実生成未検証。
隔離runtimeは `/Users/medaro/.local/share/pic2pdf-mlx/runtimes/qwen38-retest-20261005-v1`。

モデル旧revision `3e6447f082e89cc7f0bc6e5441afd38dfce760ff` と更新revision
`10c35caafbb80f7dc6a7a432cdd11af10a6d4818` の差はprocessor_config.jsonのみ。
重み3ファイル計16,054,541,349 bytesのSHA-256、Tokenizer、chat templateは同じで、
本文理解能力を改善した重み更新とは扱わない。APFS cloneで元モデルと検証モデルを分離した。
旧runtimeのPythonソース2,790件、起動設定等9件、共通LLMアダプター11件に変更なし。
引用validatorの凍結した7定義も現行コードと一致した。

## 生成条件と事前ゲート

Qwen3.8-27B MLX 4-bit、DFlash2 snapshot `015e795645c74b1a0eeef3b570031fb62e769bc5`、
mode=dflash、drafter 4-bit、max draft7、KV 8-bit、server context131,072、batch1。
prefix cacheは無効で全要求cached tokens0。小説QAはthinking=false、temperature0.2、
top_p0.95、top_k20、max_tokens4,096、repeat1、presence/frequency0で固定した。
small-M/SDPA splitは有効、M1で対応しないmulti-row attentionとCPU co-prefillは起動検査で無効。

固定4問、46問、新規質問12問、引用4問・46問を本文・prompt SHAで生成前に封印。
新規質問12問は12冊の別事実を問う質問holdoutであり、独立した検索holdoutではない。
本文・具体名・話者・頁・仮説/事実を原文と照合し、最初の不合格で通常回答の拡大を止める。
DBを使わず、生成POSTは試験用portに限定した。

## 実測結果

実HTTP契約は7要求・8項目を通過。thinking on/off、JSONの構造と値、SSE終端、
自然停止、途中errorなし、同seed再現と異seed差を確認した。
seed確認用の名詞問題で12個の指示に対して6個を返す結果もあり、汎用の指示追従合格とはしない。

| 通常回答 | 内容 | 厳密な指示 | 判断 |
|---|---|---|---|
| 固定4問・seed101 | 4/4 | 3/4 | 1問で原文引用の改行を省略 |
| case1・seed202 | 不足 | 不合格 | 栗鼠を欠落、頁と引用は正しい、自然停止 |
| case1・seed303 | 不足 | 不合格 | 同じ欠落を再現、自然停止 |

case1の3seedは1/3。通常回答は計6要求であり、4問×3seed全体の評価ではない。
残り6要求、46問、holdout12問、長文は未実施。期待回答をpromptへ追加して再採点していない。
通常4問seed101の全体時間は119.2/131.5/159.7/180.4秒、最初のtokenは109.4〜170.1秒。
合計590.8秒、中央値145.6秒。

通常回答NG後の引用診断は、実モデルHTTP出力を凍結した本番validatorでオフライン検証した。
検索・本番API・再試行・保存を通すend-to-end検証ではない。

| 引用case / 頁 | raw要点 | 本文一致 | 前後本文補足後の要点 | 全体秒 |
|---|---|---|---|---|
| 1 / 40 | 栗鼠を欠落 | 合格 | 次行の琳麗の返答で具体名を含む | 120.7 |
| 2 / 61 | 庭園・池の上・二階建て | 合格 | 保持 | 140.9 |
| 7 / 45 | 牛肉の大和煮 | 合格 | レジ袋から出す原文も保持 | 171.2 |
| 8 / 68 | 偽の証拠という岩永の仮説 | 合格 | 不確実性を保持 | 190.6 |

raw要点3/4、補足後の要点4/4。独立した読み取り専用レビューでも本文の連続範囲・頁・
仮説の保持を確認し、未根拠補足や日本語の意味誤りは見つからなかった。
validatorは空白正規化後の一意な連続位置を照合し、canonical原文の引用行と前後1行を
各側500字以内で追加する。本文一致だけでは質問の充足や話者特定を検証できない。
case1・7の表示には話者名が明示されず、page全体との照合で誤帰属がないことを確認した。
前後1行の補足が常に具体名や話者を回復する保証はない。

## 解釈の限界と証跡

同日の旧Qwen3.8試験はseed未固定で、今回freshな旧runtime A/Bは未実施。
draft cap・cache条件も異なるため、4問の見かけ上の改善や速度差を更新効果と断定しない。
MLX-VLM標準HTTP生成、Ollama更新・生成、引用の複数seed/holdoutも未実施。
DSparkの生SSEではusageを取得できたが、現行共通アダプターの変換後はtoken計数がnullとなった。
今回の実測は生SSEを別に記録し、途中error・終端欠落も独立して検出した。

保存先は `/Users/medaro/Developer/pic2pdf-sol-runs/qwen38-runtime-retest-20261005-v1/`。
`REPORT.md`に再現手順、`manifest.json`に環境・保全hash・health・ゲート・結果hash、
`model-revision-proof.json`にモデル重み照合、`fixtures/sealed.json`に入力封印を保存した。
`results/`にHTTP契約、通常4問、seed再試行、引用4問、canonical検証、意味レビュー、生SSE、
`logs/`に起動と試験のログを保存した。検証サーバーを再利用するときも本番GPUと調整する。

公式資料は[モデルrevision履歴](https://huggingface.co/mlx-community/Qwen3.8-27B-4bit/commits/main)、
[MLX 0.32.3](https://github.com/ml-explore/mlx/releases/tag/v0.32.3)、
[MLX-LM 0.32.0](https://pypi.org/project/mlx-lm/0.32.0/)、
[MLX-VLM 0.7.4](https://github.com/Blaizzy/mlx-vlm/releases/tag/v0.7.4)、
[MLX-dspark 0.20.2](https://github.com/ARahim3/mlx-dspark/releases/tag/v0.20.2)。
品質判断は実測と原文レビューに基づく。
