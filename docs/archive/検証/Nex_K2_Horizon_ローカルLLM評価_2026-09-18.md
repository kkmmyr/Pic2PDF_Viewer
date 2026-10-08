# Nex / K2 Horizon ローカルLLM評価（2026-09-18）

> status: frozen | evaluated: 2026-09-17〜18 | hardware: Apple M1 Max / 64GB

## 結論

**今回の条件では現行Qwen3.6の主生成・QAを置換しない。** Nexはmediumの短窓比較候補に留め、
K2はこのMLX量子化・runtimeでの採用を見送る。両モデルとも64GBへロードでき、メモリ不足が
見送り理由ではない。小規模な既知fixtureの結果なので、一般的な日本語性能の順位を意味しない。

- Nex: mediumは固定判定3/3。現行Qwenも3/3で、Nexの優位は確認できない。
  20ページ抽出は公式sampling・アプリsamplingとも回答前に出力上限へ達した。
- K2: highは機械判定2/3。lowは終了タグへの対応後に機械判定3/3だが、全件に他言語が混入し、
  1件は最大期間を最小期間に逆転した。日本語根拠を含むゲートには通らない。
- 評価中にMLXの乱数固定を発見した。回避前の品質結果を無効化し、全モデルを再測定した。
  通常Mac runtimeへの対処は[既知の問題](../../log/既知の問題.md)として残る。

## 評価範囲

Nex-N2.5-mini → K2-Horizon-MoVA-36B-A4Bの順で、テキスト生成用MLX 4-bit版を隔離評価した。
現行モデルQwen3.6 35B-A3Bも同じ評価runtimeで対照測定した。結論は、この量子化・runtime・
日本語小説fixture・出力枠の組合せに限定する。原版BF16、画像、OCR、ツール実行、全文検索自体、
Windows/Linux GPU、GGUF、全冊サマリ、実ブラウザのQA操作は今回の評価範囲外である。

本番DBはSSH越しのSQLite read-onlyで参照し、既存source/prompt SHAの一致を必須にした。
モデルと評価用venvはrepo外に配置した。アプリのソース・設定・既存venv・索引・公開物は変更していない。

## 固定したモデルと環境

| 項目 | Nex | K2 Horizon |
|---|---|---|
| MLX変換元 | `abenzerps/Nex-N2.5-mini-MLX-4bit` | `abenzerps/K2-Horizon-MoVA-36B-A4B-MLX-4bit` |
| revision | `98d82d7d030ff5e438b146c3957cba9e371ed01e` | `0c576733b69e8ca2d7a0292d0f01ee1d955bb9b5` |
| 重み | 約19.51 GB / 4 shards | 約21.07 GB / 48 shards |
| 取得検証 | 13ファイルのサイズ・SHAを記録、LFS hash照合 | 60ファイルのサイズ・SHAを記録、LFS hash照合 |
| 思考制御 | `reasoning_effort=none/medium/high` | `reasoning_effort=low/medium/high` |
| 品質測定sampling | temperature 0.7 / top-p 0.95 / top-k 40 | temperature 1.0 / top-p 0.95 / top-k 0 |

runtimeは`mlx=0.32.0`、`mlx-lm=0.31.3`、`transformers=5.15.0`。
後述のsampling回避策を全モデルへ同条件で適用した。`127.0.0.1:11440`、生成・prompt同時1件、
prompt cache 0、prefill 512、出力上限8,192 token。HTTP非stream応答のrawを修復前に保存した。
時間はHTTP要求から応答までで、モデルのダウンロード・起動・vmmap測定を含めない。

[Nex公式カード](https://huggingface.co/nex-agi/Nex-N2.5-mini)の推奨samplingと、
[K2公式カード](https://huggingface.co/IFM/K2-Horizon-MoVA-36B-A4B)のhigh・samplingを参照した。
K2公式例の出力枠は32,768であり、今回の8,192はアプリの事実抽出予算を評価する条件である。
公式のBF16/SGLang品質をこのMLX測定で否定するものではない。

## sampling不具合と初回結果の無効化

初回は全モデルでseedを変えても同じ出力になった。単独のsampler試験は変化したが、実サーバーでは
温度1,000・top-p 1・top-k 0・8 tokenの診断要求でも3 seedが完全一致した。
MLX 0.32.0の推論スレッドとimport時compileの乱数状態に関する
[MLX #4234](https://github.com/ml-explore/mlx/issues/4234)・
[mlx-lm #1439](https://github.com/ml-explore/mlx-lm/issues/1439)の報告と一致する。

評価用起動プロセスだけで`categorical_sampling`を同じ数式の未compile関数へ置換した。
[上流の修正案](https://github.com/ml-explore/mlx-lm/pull/1593)もimport時のsampler compileを除去する。
インストール済みパッケージやモデル重みは編集していない。

- 回避前: 異なる3 seedのHTTP応答が1種類。
- 回避後: 異なる3 seedで3種類。同じseedを4回目に再送し、1回目と応答hashが一致。
- 実品質設定のQwen/Nexでも各seedの応答が異なり、prompt cache hitは0。
- 初回のQwen・Nex・K2品質結果はすべて`invalidated-runs.json`で無効とし、下記の結果へ混ぜない。
  特に旧「3/3」は独立試行の証拠にならず、旧反復失敗をモデル固有の結論に使わない。
- 読み取り専用の独立レビューで、回避策が数式を変えないこと、seedの生成threadへの伝達、
  raw保存・自然停止判定を確認した。同一seed再現の診断は上記の高温設定に限る。

既存Mac venvも同じ版で、通常runtimeへの対処は未実施。
[既知の問題](../../log/既知の問題.md)に解消条件を記録した。Linuxのllama-server/Ollamaは別経路である。
過去のMLX測定を一律無効とはせず、同じ版・同じ推論経路でseedに依存した判断は再確認する。

## 品質ゲート

1. 書籍ID 46の74〜75ページ。途中の牢戻り発言より、後の最大10年間の逃亡への合意を優先できるか。
   seed 20260821/22/23。bare JSONの4 key、enum、人物名、日本語根拠、自然停止を要求し、
   根拠の意味は手動確認する。同一モード3/3通過時だけ後段へ進む。
2. 8〜27ページの20ページ抽出。既存のBOOK_FACTS→CHARACTER_FACTの2段階promptとparserを使用。
   引用page、正規人物名、自然停止、既知の誤帰属を確認する。seed 20260813。
   機械ゲートだけでは未登録人物名を排除しないため、合格時も手動照合を必要とする。
3. 52〜54ページの追加4主張。正答とpromptは候補推論前に固定した。ただし過去に未使用とは
   証明しておらず、独立holdoutと呼ばない。「従者の共犯が確定」の設問は、命題全体の否定と
   共犯の証拠不足が競合するため、contradicted/insufficientの単一採点差を採否根拠にしない。

固定source SHA: `7a44d23a1bdb263c7a67bcc3efa1405f1c3eeec33e076ff12efd3644e00e0f4e`  
固定prompt SHA: `4ce54b1fe01087b4b47eb584e8e630db88356541d90f76f64d899451b88bbeba`  
20ページsource SHA: `47f62bc67042c39dbf09d0b9213041d8a6a048c98a41a5d0e3341292f6c15007`  
20ページ人物台帳SHA: `3c93cdb7f234e530f320ef00724136115785b4757000c58461eff1704576d86c`  
20ページprompt SHA: `d38f4a04f5b8dcfb38069a42debe166bffd6a4c4860c824ff6042365deb23664`  
追加source SHA: `051220698de4e49fe9e9ee3c2a8e0560fcb579b1e2f5d1e52ddc61bfc46bd8db`

## 回避策適用後の固定ケース結果

「機械判定」はJSON・enum・最終行動・名前・自然停止の既存チェックであり、日本語の自然さや
根拠の全意味を保証しない。モード間で成功数を合算しない。

| モデル / mode | 機械判定 | 各seedのHTTP秒数 | 手動確認 |
|---|---:|---|---|
| Qwen3.6 / none | 3/3 | 8.5 / 7.7 / 7.6 | 最終合意は3件とも妥当。根拠文で「長くて」を省略する記述は残る。 |
| Nex / none | 2/3 | 8.5 / 7.5 / 8.5 | 1件が将来の牢戻りの推測を混ぜ、誤要約を部分矛盾に留める。 |
| Nex / medium | 3/3 | 15.8 / 18.5 / 11.8 | 3件とも判定・根拠が本文に沿う。Qwenより速くはない。 |
| K2 / high | 2/3 | 22.5 / 61.8 / 201.0 | 1件は回答前に終了。成功2件のうち1件に韓国語の語尾が混入。 |
| K2 / low（終了タグ対応後） | 3/3 | 21.4 / 20.6 / 19.7 | 全件で多言語混入。1件は「長くて10年」を「少なくとも10年」に逆転。 |

K2 highの回答前停止は、同一seedに`logprobs:true`だけを加えた診断で応答を完全再現し、
最後の実生成tokenが`250019`（`<|ifm|im_end|>`）であると確認した。
思考終了token `250030`との取り違えではない。EOSを抑制して成功扱いにはしていない。

K2 lowは、最初のadapterではcanonical終了タグ後のJSONが思考欄へ残った。
この3件は形式確認の診断証拠として残し、品質スコアには使わない。表は終了境界だけを修正し、
新プロセスで同じ3 seedを再測定した値である。token・prompt・samplingは変更していない。

K2はhigh・lowとも手動根拠を含め3/3に達しないため、20ページ抽出と追加ページへ進まなかった。
medium、32,768出力、公式BF16実装、低温への追加調整は未測定であり、改善しないとは断定しない。

## Nex mediumの後段評価

| 20ページ抽出の条件 | HTTP秒数 | 入力 / 出力token | 終了と回答 |
|---|---:|---:|---|
| 公式sampling | 244.1 | 16,678 / 8,192 | length、思考中、回答0文字 |
| アプリsampling | 237.0 | 16,678 / 8,192 | length、思考中、回答0文字 |

アプリsamplingは現行`FACT_EXTRACTION_OPTIONS`を`MlxLmBackend._build_body`へ通し、
思考指定だけmediumへ合わせたもの（temperature 0.1、repetition penalty 1.15、出力8,192）。
top-p/top-kはbodyに含めずserver既定を使用した。両方ともBOOK_FACTSが得られず、後続の人物抽出は未実行。
これは回避前の反復観測に頼った結論ではなく、回避後も生成枠内に最終回答が出なかった結果である。

追加4主張は全seedで自然停止・JSON成功。機械採点は各3/4だが、唯一の差は前述の曖昧な従者設問。
残る「翌日の外出」「誘拐捜査経験」「話者訂正」は全seedでラベル・引用ページ・理由が一致し、
従者設問の理由自体も本文の二つの可能性を保持していた。これを4/4へ採点変更したり、
長文不合格を覆す採用証拠として使ったりはしない。HTTP時間は約20.6〜32.8秒。

## メモリと運用

有効な測定の`vmmap -summary`で、Qwen短窓はphysical footprint約18.6G・同プロセスpeak 19.2G、
Nexの20ページ測定後は約19.5G・peak 20.0G、K2 highの固定ケース後は約21.4G・peak 22.7Gだった。
RSSだけでApple Siliconの総使用量を見積もらない。値は当該プロセスと観測区間のもので、
全冊処理や全サービス同時常駐の最大値ではない。固定ケース中の全体swap usedは約1.32 GBのまま
増加しなかったが、既存swapが0という意味ではない。

評価用11440サーバーは停止済み。モデルとrawをrepo外に保持し、転送用remote一時領域と
失敗した未完ダウンロードは後片付けした。既存Ollama等のユーザープロセスは操作していない。

## アプリ接続上の差分

- **Nex**: `enable_thinking`を参照しない。現行backendが送る値を、モデル別の
  `chat_template_kwargs.reasoning_effort`へ変換する必要がある。今回の評価はHTTP bodyで明示した。
- **K2**: 独自の`k2_horizon_mova_mlx.py`を使うコミュニティ変換。実行前に読み取り専用で監査し、
  固定したコードhashと一致を確認した。SHA-256は
  `0b0417dd7430467a7847cbd0611ad09d45a0a91ce86720022e8cc00aa1cf42ef`。
  BF16の公式実装との数値同等性は未検証である。
- **K2の思考分離**: 標準MLX tokenizerの自動判定は独自タグを認識しないため、隔離起動wrapperで
  high=`<ifm|think>` / `</ifm|think>`を登録した。lowは開始`<ifm|think_faster>`に対し、
  実生成がcanonicalの`</ifm|think>`で閉じるため、その組合せへ対応した。mediumの実生成は未確認。
  境界は起動時に固定されるため、effort変更時はプロセスを再起動し、環境値・CLI・requestを揃えた。
  トークン・logits・EOSは書き換えていない。初回lowの対称終了タグを仮定したadapterでは
  JSON回答が思考欄へ残ったため、旧0/3を品質不合格として使わず、新プロセスの3 seedを採点した。
- **K2のtokenizer**: MLX変換にはupstream AutoConfigのPythonファイルが含まれない。
  当該モデルパスだけ標準fast tokenizerを`trust_remote_code=False`でロードした。
  これはモデル本体の独自Python実装を使わないという意味ではない。
- **K2の複数ターンQA**: 現行アプリ形式のassistant `{role, content}`を含む履歴では、
  templateがthinking field不足の例外になる。`reasoning_content:""`を加えると描画できたが、
  これはtemplate互換の確認までで、複数ターンQAの精度・ストリームUI完走は未評価。
  モデル名だけの差し替えでは接続済みにならない。

## 保存した証跡と再実行

ローカル評価ルート: `/Users/medaro/.local/share/pic2pdf-mlx/evaluations/2026-09-17-nex-k2/`。
raw本文は書籍データを含むため、このレポートには全文を複製しない。

- `nex-verified.json` / `k2-verified.json`: revision・全ファイルhash。
- `requirements-frozen.txt`: 評価venv。
- `sampling-server-probe/` / `sampling-server-debug/` / `sampling-server-corrected/`: 乱数不具合と回避確認。
- `invalidated-runs.json`: 初回結果の無効化理由。旧rawは削除せず監査用に保持。
- `corrected/`: 再測定・診断のraw request/response、summary、固定ゲートのmemory sample・vmmap。
  `k2-low/`は`adapter-limitation.json`に従い採点対象外で、`k2-low-canonical/`が置換後の結果。
- `corrected/manual-review.json`: 手動判定と設問の限界。
- `corrected/script-hashes.json`: 評価・起動スクリプトのhash。
- `k2-multiturn-preflight.json` / `k2-code-match.json`: 接続契約と独自実装の照合。

再実行時はrepoの`eval_ornith_mlx.py` / `eval_ornith_mlx_gate_b.py`のfixtureとprompt SHAを照合し、
repo外の`evaluate.py` / `evaluate_20page.py` / `evaluate_fresh.py`を使用する。
アプリ設定を接続先へ向ける前に、seed診断とモデル別template境界を必ず確認する。
