# MacローカルLLM移行・比較計画

> 状態: 初回比較完了（3回再現性試験・本番採否は未完了）
> 作成日: 2026-07-28
> 最終更新: 2026-08-13
> 対象: 小説RAGの事実抽出、巻別要約、人物辞典、生成物QA

## 1. 目的

M1 Max 64GBのApple Silicon Macを、Pic2PDFViewer本番環境から分離した
ローカルLLM推論ホストとして評価する。現在のWindows上の
Qwen3.6-35B-A3Bを直ちに置き換えず、同じ10巻パイロットを使って、
処理時間、メモリ使用量、日本語の可読性、ページ根拠への忠実性、
人物正規名の安定性を比較してから採否を決める。

[ADR-0018](../../design/基本設計/ADR/0018_sol-primary-post-ocr-generation.md)により、
OCR後の公開成果物はSol主生成へ段階移行中である。本計画でいう「主生成器」は、対話QAと
オフライン代替を担う**ローカルLLM系統内の主生成器**を意味し、Sol主生成方針を置き換えない。

モデル変更だけで事実性を保証しない。正規名・別名統合、完成文と事実表の
意味的照合、人物集合の削除回帰検査は、モデル選定と独立したB-36の必須改善とする。

## 2. 現状と変更しない範囲

- 現在の採用モデルはQwen3.6-35B-A3B IQ4_XS、実行基盤はWindowsの
  `llama-server`である。
- Linux本番のSQLite、LanceDB、OCR本文、撮影画像はMacへ複製して正本化しない。
- MacはLLM推論APIだけを提供し、本番DBの更新と公開判定は従来どおり
  Linuxバックエンドと監査CLIが担う。
- 比較中は公開中の要約・人物辞典を置換しない。各試行はスナップショット、
  JSON/Markdown差分、Codex補助QAを必須とする。
- Kindle撮影、OCR、検索索引構築はMac移行の完了を待たず継続できる。
  品質改善中の要約・人物辞典生成だけを独立した後続工程として保留する。

## 3. 比較候補

| 優先 | 候補 | 量子化の初期候補 | 主な評価目的 |
|---:|---|---|---|
| 1 | Qwen3.6-27B Dense | MLX 6bit、収まらない場合4bit | 最終要約・人物説明の事実保持と文章品質 |
| 2 | Qwen3.6-35B-A3B | 現行相当の4bit | Windowsとの差がモデルか実行環境かを分離する基準 |
| 3 | Gemma 4-31B Dense | MLXまたはGGUF 4bit/6bit | 別系統モデルによる独立校正・事実性確認 |
| 4 | Muse Glimmer 30B Dense | GGUF Q6_K_XL | Meta系の別モデルによる構造化抽出・日本語要約・独立検証 |

Qwen3.6-27BはDenseモデルのため、活性約3Bの35B-A3Bより低速になる見込みである。
速度ではなく夜間バッチの品質候補として評価する。Gemma 4-31Bは全面置換を前提とせず、
編集・批評モデルとしての併用も比較する。64GBで余裕が少ない122B級モデルや、
日本語小説を主対象としていないモデルは初回比較から除外する。

Muse Glimmer 30Bは2026年8月公開のMeta Superintelligence Labs製Apache 2.0モデルで、
131,072以上のcontextと100言語以上への対応を掲げる。公開評価はagent・tool利用・coding中心で、
日本語小説の長文要約品質を直接示すものではないため、Qwenの置換候補とはまだ扱わない。
M1 Max 64GBでは品質優先の`UD-Q6_K_XL`（言語GGUF約26GB）を取得し、Qwen・Gemmaを
停止した単独常駐で固定10巻を比較する。取得元のUnsloth GGUFはMeta公式ウェイトの量子化配布物で
あるため、モデル名、量子化、blob digest、runtimeバージョンを実測記録へ残す。2026-08-13時点の
Ollamaは同梱vision projectorをロードできないため、比較実行にはHomebrew版`llama.cpp`を使う。

M1 Max 64GBでQwen3.6-27B Dense 6bitを別プロセスとして2本常駐させる構成は採用しない。
単体実測のモデル常駐が約22GBでも、2本分の重み、macOS、長文リクエストごとのKV cacheを
合わせると13万文字級では安全余裕を確保できないためである。同一モデルの処理は1サーバーで
重みを共有して直列実行し、並行検証が必要な場合は27B 6bitと軽量な4bit検証モデルを組み合わせ、
実測メモリとswapを受入条件に含める。

参考:

- [Qwen3.6公式リポジトリ](https://github.com/QwenLM/Qwen3.6)
- [Qwen3.6-27Bモデルカード](https://huggingface.co/Qwen/Qwen3.6-27B)
- [Gemma 4-31Bモデルカード](https://huggingface.co/google/gemma-4-31B)
- [Muse Glimmer 30B公式モデルカード（Meta）](https://huggingface.co/meta-models/Muse-Glimmer-30B)
- [Muse Glimmer評価方法（Meta）](https://research.meta.ai/static/muse-glimmer-methodology)
- [Muse Glimmer 30B GGUFモデルカード（Unsloth）](https://huggingface.co/unsloth/Muse-Glimmer-30B-GGUF)

## 4. 実施前にMacで確認する情報

```bash
system_profiler SPHardwareDataType
sw_vers
df -h /
```

- チップ名がM1 Max、統合メモリが64GBである。
- モデル、変換キャッシュ、監査出力を置く空き容量が100GB以上ある。
- macOS、Xcode Command Line Tools、Homebrew、git、uvを更新できる。
- Macから`medaroserver`へSSH接続できる。

## 5. 実施手順

### Phase 0: 現行基準の固定

1. 10巻の公開版スナップショットと、2026-07-28に不採用とした差分を基準として保存する。
2. 入力する本文ページ、事実抽出・要約・人物・編集プロンプト、sampling設定を固定する。
3. 現行Windows Qwen3.6-35B-A3Bで基準結果を再取得し、モデル以外の差をなくす。

### Phase 1: Mac推論環境

1. Apple Silicon対応の`mlx-lm`を第一候補、既存API互換を優先する場合は
   最新`llama.cpp`を第二候補として導入する。
2. まずQwen3.6-35B-A3Bの4bit版で短い生成と131,072 contextの起動を確認する。
3. 推論APIをMacのLANへ直接公開せず、MacからLinux本番へのSSH reverse tunnelで
   `127.0.0.1:11435`として提供する。
4. Macのスリープを実行中だけ抑止し、処理後は推論serverとtunnelを停止する。
5. Muse Glimmerは既存モデルを削除・上書きせず、Q6を追加する。

   ```bash
   ollama pull hf.co/unsloth/Muse-Glimmer-30B-GGUF:UD-Q6_K_XL
   ```

6. Ollama 0.30.11は同梱vision projectorの`muse-glimmer`アーキテクチャをロードできない。
   対応版が確認できるまではOllama APIを使わず、`brew install llama.cpp`で導入した
   `llama-server`へ言語GGUFだけを渡す。
7. 導入直後は短い日本語応答、モデル常駐量、context上限を確認するだけに留め、
   `NOVEL_DB_LLM_MODEL`などの本番既定値は変更しない。

#### Muse Glimmer導入実測（2026-08-13）

- 実機はM1 Max 64GB、macOS 26.6.1、Ollama 0.30.11、`llama.cpp` b10360。
- 登録名は`hf.co/unsloth/Muse-Glimmer-30B-GGUF:UD-Q6_K_XL`、Ollama表示は30GB。
  内訳はQ6_K言語ウェイト26GBとvision projector 3.8GBで、モデルIDは`b6802b7d8c07`。
- Ollamaはモデル情報を27.9B、context 131,072、Q6_Kとして読めるが、推論開始時に
  projectorの未知アーキテクチャで停止する。ウェイト破損ではなくruntime未対応として扱う。
- `llama.cpp` b10360へ言語blobだけを渡すと、4,096 context・Metal 100%配置でロードできた。
  初回ロードは約30.9秒、RSSは約24.8GiB、短い直接回答は入力49.2 token/s、生成11.9 token/sだった。
- 標準chat templateはreasoning強度の既定値がhighで、low指定でも簡単なJSONを256 token以上
  考え続ける場合がある。1冊比較では思考と本文を分離保存し、出力上限到達を品質失敗として記録する。
- 導入確認後は`llama-server`を停止した。本番DB、公開要約、OCR本文、環境変数は変更していない。

#### Muse Glimmer / Qwen3.6比較実測（2026-08-13）

茉莉花官吏伝10巻の隔離コピーを読み取り専用で使い、Qwen3.6 35B-A3Bと
Muse Glimmer 30B Q6を同じ固定ケースと4ブロックで比較した。本番DBと公開要約は変更していない。

今回の値は各条件1回の予備試験であり、Phase 2が求める3回再現性試験は未完了である。両モデルとも
同じOCRページ、意味上同じ指示、JSON Schema、seed 42、temperature 0で比較し、Qwenは`think=false`、
Museは`Reasoning strength: high`と回答先`user`を固定した直接completionを使った。Muse公式推奨の
temperature 1.0 / top_p 0.95 / top_k 64やDFlash drafterは使っていないため、速度・品質とも
Museの最適化済み上限を示す測定ではない。またMuse側ではprompt先頭のBOSがserver側と重複する警告が
記録されており、次回再現性試験ではchat template経路を統一して解消する。

- 74〜75ページの固定ケースでは、Qwenが最終行動、事実メモ、誤要約の3判定をすべて誤り、
  Museは「最長10年逃亡」「事実メモは部分矛盾」「牢へ戻る要約は矛盾」をすべて正解した。
  単独の所要時間はQwen 18.25秒、Muse 45.63秒だった。
- 8,192 contextで両方を常駐させると合計約47.3GiB、空き約12%、swap 0で起動できた。
  ただしcacheを分離した同時生成はQwen 49.62秒、Muse 63.46秒で、逐次実行の合計52.68秒より
  同時実行の完了時刻が約20.5%遅くなった。Qwenの生成速度は34.24から2.67 token/sへ低下した。
- 131,072 contextも合計約50.0GiB、空き約7%、swap 0で同時常駐できたが、長文同時生成に必要な
  安全余裕はない。同時常駐可能という事実を、同時生成可能または推奨と読み替えない。
- 77ページを一括投入したQwenは10分39秒で完走したが、詳細730字、一覧208字で文字数契約に
  違反し、終盤の将来証言を落とした。Museの一括投入は入力63,488 token、約89%を処理した時点で
  約53分を要し、生成前に評価上限で停止した。
- 同じ8〜27、28〜49、50〜69、70〜84ページの4ブロック方式では、Qwenは約9分18秒、
  Museは約42分47秒で完走した。詳細要約はQwen 1,280字、Muse 1,542字で契約内だったが、
  一覧要約はQwen 299字、Muse 314字で両方とも400字の下限に届かなかった。
- 終盤事実は、Qwenが一覧版に十年逃亡を残した一方で必要時の証言を欠落させた。Museは詳細版と
  高リスク事実に逃亡と証言を残した一方、一覧版で十年を落とし、将来の約束を`completed`扱いした。
  両方とも原文の「長くて十年間」という上限表現を単なる「十年間」へ変えた。

この初回結果から、Qwenをローカル系統の主生成器として維持し、Museを巻全文の代替生成器にはしない。
Museの追加価値は
短い根拠窓に対する高リスク事実の独立判定に限定して再評価する。通常運用はモデルを明示的に停止して
逐次切替し、両モデルの同時生成と131,072 contextでの同時常駐を採用しない。

### Phase 2: 固定10巻A/B比較

各候補を同じ入力・プロンプト・sampling条件で3回ずつ実行し、次を記録する。

- モデル名、量子化、runtime、context、出力上限、乱数条件。
- 初回応答時間、総処理時間、tokens/sec、最大メモリ使用量、異常終了。
- 要約文字数、人物数、追加・削除・変更人物、機械品質ゲート。
- 事実表にない行動、時系列・因果誤り、人物正規名の揺れ、理由のない人物削除。
- 3回の結果の揺れと、Codex補助QAによる採否。

### Phase 3: 役割決定

- Qwen3.6-27Bが安定して合格する場合は、最終執筆または意味的QAへ採用する。
- Gemma 4-31Bだけが校正に有効な場合は、生成と独立QAを別モデルに分ける。
- Muse Glimmerは、構造化事実抽出、詳細あらすじ、一覧用短縮要約、人物辞典、
  高リスク主張監査をQwenと同じ順序で比較した。初回仮判定では巻全文の抽出・生成を速度と契約遵守から
  不採用とし、短い根拠窓の高リスク主張監査だけを追加評価候補として残す。3回再現性試験までは
  本番採用・恒久不採用の確定判断にしない。
- 現行35B-A3Bとの差が小さい、または全候補で誤りが残る場合は移行しない。
- 採用時だけ環境変数、起動手順、障害時のWindows復帰手順、設計ADRを更新する。

### Phase 4: 段階導入

1. 10巻1冊だけで公開前監査まで再実施する。
2. 合格後、1〜3巻の3冊へ広げ、巻をまたいだ人物正規名を確認する。
3. それでも合格した場合だけ、1〜18巻の夜間再生成へ進む。
4. 各段階で不合格なら旧版を復元し、次段階へ進まない。

## 6. 受入条件

- Mac上で131,072 contextと必要な出力上限をOOMなしで完走する。
- 10巻の3回試行で、事実表にない主要行動を追加しない。
- `皓茉莉花`、`芳子星`、`封大虎`などの正規名・別名が同一人物へ統合される。
- 既存人物を削除する場合、本文根拠と除外理由を差分で説明できる。
- 機械品質ゲートとCodex補助QAの両方に合格する。
- 不採用時にSQLiteとサマリembeddingを旧版へ復元できる。
- Mac停止時はWindows推論環境へ戻せ、撮影・OCR・検索索引を停止させない。

## 7. 完了条件

候補ごとの実測値、3回の生成差分、Codex補助QA結果、採否、採用する役割、
本番切替・復帰手順が記録されていること。単にMacでモデルが起動しただけでは
移行完了としない。
