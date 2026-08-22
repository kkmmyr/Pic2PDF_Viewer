# MacローカルLLM移行・比較計画

> frozen: 2026-08-22 | outcome: 初期MLX移行完了、追加モデル比較完了
>
> 過去の比較計画と実測記録。現在の決定は
> [ADR-0019](../../design/基本設計/ADR/0019_apple-silicon-mlx-inference.md)、
> 現行手順は[GPU環境セットアップ](../../design/環境構築/GPU環境セットアップ.md)を参照する。

> 状態: 初回モデル比較・MLX runtime比較完了（Ornith日本語小説RAGは不採用、比較checkpointのみ保持）
> 作成日: 2026-07-28
> 最終更新: 2026-08-22
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
| 1 | Qwen3.8-27B Dense | Ollama Q4_K_M | 現行3.6に対する事実保持・構造安定性・完成文品質の世代差 |
| 2 | Qwen3.6-35B-A3B | 現行相当の4bit | Windowsとの差がモデルか実行環境かを分離する基準 |
| 3 | Qwen3.6-27B Dense | MLX 6bit、収まらない場合4bit | 最終要約・人物説明の事実保持と文章品質 |
| 4 | Gemma 4-31B Dense | MLXまたはGGUF 4bit/6bit | 別系統モデルによる独立校正・事実性確認 |
| 5 | Muse Glimmer 30B Dense | GGUF Q6_K_XL | Meta系の別モデルによる構造化抽出・日本語要約・独立検証 |
| 6 | NVIDIA Nemotron 3.5 Lightning 30B-A3B | GGUF Q4_K_M / MLX affine 4bit・6bit | 新規MoE系の短窓検証・構造化抽出・指示遵守、runtime差 |
| 7 | Nemotron Labs 3 Puzzle 75B-A9B | MLX mixed 4/6-bit | 64GB適合性、世代更新後の短窓推論・長文根拠保持・JSON終端 |
| 8 | Ornith 1.5 35B-A3B | 公式MLX affine 4bit | Qwen3.5 MoE派生の速度・Thinking品質・厳密形式・小説RAG適合性 |

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

Nemotron 3.5 Lightning 30B-A3Bは2026年8月公開の新規候補で、約3B activeの
Mamba/MoE/attention hybrid、thinking切替、tool calling、長文contextを備える。公開ベンチマークは
日本語小説のページ根拠付き抽出を直接保証しないため、Qwenの置換候補とはせず、固定短窓と第1ブロックの
早期ゲートから評価する。64GBではOllama公式Q4_K_Mを単独常駐させ、本番既定値へ配線しない。
Ollama版の短窓thinkingが他候補より良かった記録を再確認するため、MLX 4bitと6bitも同じ本文・
prompt・sampling・seed群で比較する。MLXで軽くなること自体を採用理由にせず、prompt cache汚染、
MTP非対応、thinking終端、出力token量、physical footprintを別々に記録する。

Nemotron Labs 3 Puzzle 75B-A9Bは75.3B total / 9.3B activeで、Nemotron 3 Superから
圧縮されたMamba 2・Attention・LatentMoE混成モデルである。M2 Max 64GBで実測済みの
mixed 4/6-bit MLX変換を第一候補とし、既存Qwen / bge-m3 serverを停止した単独常駐で評価する。
通常の`mlx-lm`は異種expert幅へ未対応なので、監査済み固定feature branchを専用venvへ隔離する。
モデル取得・起動だけでは採用せず、旧30B-A3Bと同じ74〜75ページ固定ケース、JSON終端、
32,768 token以上の段階的長文入力を早期ゲートにする。本番既定値と公開物には配線しない。

Ornith 1.5 35B-A3BはQwen3.5系の約35B total / 約3B active MoEへself-improvement trainingを
重ねたreasoning modelである。公式MLX 4bit版は18.2GiBで、M1 Max 64GBへのロード余裕と
MoEの速度を期待できる。一方、公開評価はagentic coding中心で日本語小説を直接保証せず、
Qwen3.5 hybridのprefix cache不整合とlong-context resource limitも未解決である。
まずcache 0・同時実行1・Thinking有効の短答 / API / benchmarkだけを行い、その後に固定小説ケース、
構造化出力、長文の順で拡大する。起動成功だけでQwenを置き換えず、本番設定へ配線しない。

Qwen3.8-27Bは世代更新による現行Qwen3.6-35B-A3Bの置換可否を、速度よりも完成物の
事実性で判定する。短窓と巻全体は両方とも`think=false`に揃え、Thinkingの有無で
結果が変わる余地を比較条件から外す。初回比較は公開物を変更せず、合格時だけ複数回試験へ進む。

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
- [NVIDIA Nemotron 3.5 Lightning公式モデルカード](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)
- [Nemotron 3.5 Lightning Ollamaライブラリ](https://ollama.com/library/nemotron-3.5-lightning)
- [Nemotron 3.5 Lightning MLX 4bit](https://huggingface.co/mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit)
- [Nemotron 3.5 Lightning MLX 6bit](https://huggingface.co/Vontra/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-MLX-6bit)
- [MLX-LM](https://github.com/ml-explore/mlx-lm)
- [MLX-LM hybrid modelのprompt cache課題](https://github.com/ml-explore/mlx-lm/issues/980)
- [MLX-LM prompt cache prefix不整合](https://github.com/ml-explore/mlx-lm/issues/1494)
- [NVIDIA Nemotron Labs 3 Puzzle 75B-A9B公式モデルカード](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-3-Puzzle-75B-A9B-FP8)
- [Nemotron Puzzle MLX mixed 4/6-bit](https://huggingface.co/tekosML/Nemotron-Labs-3-Puzzle-75B-A9B-MLX-4bit-experts-6bit)
- [Ornith 1.5 35B-A3B公式モデルカード](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B)
- [Ornith 1.5 35B-A3B公式MLX 4bit](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B-MLX-4bit)
- [Ornith 1.5 MLXコミュニティ実測](https://www.reddit.com/r/oMLX/comments/1vtg1rv/ornith_seems_to_be_better/)
- [MLX-LM Qwen3.5 hybrid prefix cache課題](https://github.com/ml-explore/mlx-lm/issues/980)
- [MLX-LM Qwen3.5 MoE long-context resource limit](https://github.com/ml-explore/mlx-lm/issues/1644)
- [MLX-LM HTTP server仕様](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- [MLX-LM request単位Thinkingの報告](https://github.com/ml-explore/mlx-lm/issues/1352)
- [MLX-VLM](https://github.com/Blaizzy/mlx-vlm)
- [MLX-VLM structured output + Thinking修正](https://github.com/Blaizzy/mlx-vlm/pull/1299)
- [MLX-VLM同時structured outputのprocessorずれ報告](https://github.com/Blaizzy/mlx-vlm/issues/1574)
- [非公式mlx-openai-server](https://github.com/cubist38/mlx-openai-server)
- [Qwen3公式non-thinking生成設定](https://huggingface.co/Qwen/Qwen3-8B)
- [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Ollama Modelfileパラメーター](https://docs.ollama.com/modelfile)

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

#### Nemotron 3.5 Lightning導入・早期ゲート実測（2026-08-14）

Homebrew Ollamaを0.30.11から0.32.9へ更新し、公式
`nemotron-3.5-lightning:30b-a3b-q4_K_M`を既存モデルとは別に登録した。Ollama表示は32.9B、
Q4_K_M、25GB、context 1,048,576、completion・tools・thinking対応で、model IDは
`e7a64ff15fb1`である。配布CDNの接続リセットが続いたため未取得範囲だけを100MB分割で補完し、
全体SHA-256がmanifestの`5c19f628...f63b3`と一致した後に登録した。既存モデルは削除していない。

茉莉花官吏伝10巻をサーバーDBから読み取り専用で参照し、公開物を変更せず評価した。74〜75ページの
固定ケースは、directが13.752秒で最終行動を誤判定し、理由文内でも自己矛盾した。thinkingありは
108.496秒で最長10年の逃亡継続、旧事実の矛盾、誤要約の矛盾をすべて正解した。

一方、8〜27ページの事実抽出はthinkingありで約8分28秒後も必須`[BOOK_FACTS]`を返さなかった。
directは98.610秒でページ付き事実2,941字を返したが先頭マーカーを欠落した。決定的アダプターで
マーカーだけを補って人物再編まで進めると145.695秒、104 recordを生成し、参照ページは入力範囲内だった。
しかし原文抜き取り照合で話者の取り違え、別場面へのページずれ、前ページの命令を次ページへ付ける誤りを
確認した。人物見出しも18件、既存正規化後16件となり、役職別名と重複が残った。

32,768 contextでは25GB・100% GPU、空きメモリ54%、swap 0で、64GBへの単独常駐性は合格した。
品質ゲートは不合格のため4ブロックと要約生成へ拡大しない。巻全体の主生成・事実抽出には採用せず、
短窓thinkingもMuseの同ケース45.63秒より遅いため、現時点で第二検証役としての追加価値は確認できない。
登録は比較用に残すが、本番設定と自動公開へ配線しない。

#### Qwen3.8-27B / Qwen3.6-35B-A3B比較実測（2026-08-15）

Ollamaを0.32.12へ更新し、`qwen3.8:27b`を既存モデルと別に登録した。表示は
27.3B、Q4_K_M、17GB、context 262,144、completion・vision・tools・thinking対応である。
茉莉花官吏伝10巻の同じOCRページ、4ブロック、プロンプト、32,768 context、seed 20260813、
`think=false`を両モデルに使った。本番DBと公開要約は変更していない。

74〜75ページの固定ケースは、Qwen3.6 directが15.818秒、Qwen3.8 directが54.893秒で、
どちらも最長10年の逃亡継続と旧事実・誤要約の矛盾を正しく判定した。過去のQwen3.6の
固定ケース失敗は現行プロンプトでは再現せず、短窓だけでQwen3.8の品質優位は確認できない。

4ブロック抽出と詳細・一覧要約の合計は、Qwen3.6が1,881.574秒（約31分22秒）、
Qwen3.8が5,832.220秒（約97分12秒）で、Qwen3.8は約3.10倍の時間を要した。Qwen3.6は
第3・第4ブロックの人物抽出が各8,192 tokenで上限となり同一文を反復した。Qwen3.8は
この反復崩壊を避けた一方、50〜69ページの抽出に未入力の70〜71ページ事実を生成し、
許可外の6項目を決定的ゲートで項目ごと除外した。

Qwen3.6の詳細・一覧要約は1,206字 / 551字、Qwen3.8は6,514字 / 596字だった。
Qwen3.8の詳細版は「長くて10年間逃げる」と将来の証言を明記した点でQwen3.6より保持が良いが、
4,096 token上限で文途中となり、仁耀の計画を珀陽の計画とする帰属誤りも残った。
Qwen3.8の一覧版は仁耀が珀陽を殺害しようとしたと誤り、最長10年の逃亡と将来証言を落とした。
Qwen3.6も黒の皇帝を珀陽と同定し、一覧版で「牢に戻る」を最終状態にしたため、両者とも公開不可である。

局所的にはQwen3.8の構造安定性と詳細保持に改善があるが、完成要約の主体・最終状態・終端性と
総処理時間を含めると、現行Qwen3.6の置換品質には達しない。比較用モデルは残すが、
本番既定値と自動公開に配線しない。一方、Qwen3.8の詳細版は初稿・校正版がともに
`num_predict=4096`に達し、Qwen3.6の校正版も入力32,012 + 出力756 tokenが
`num_ctx=32768`と一致した。したがって途中切れをモデル能力のみに帰属せず、設定再評価を先行する。

##### Qwen3.8設定改善の局所A/B（2026-08-15起票）

最初から97分の巻全体を再実行せず、保存済み事実表から詳細・一覧要約だけを次の3条件で比較する。

1. 現行の`temperature=0.1〜0.2`、`top_p=0.95`、`repeat_penalty=1.15`を保ち、詳細・校正の
   `num_predict=8192`と校正の`num_ctx=65536`だけを試す。
2. Qwen3系公式のnon-thinking候補である`temperature=0.7`、`top_p=0.8`、`top_k=20`、
   `min_p=0`に`repeat_penalty=1.15`を組み合わせ、条件1と比較する。
3. 条件2に人物・役割同定表、中間状態と最終状態の区別、2,000〜4,000字の詳細版候補、
   未完文と`done_reason=length`の拒否を加える。

主体、仁耀の殺害対象、最長10年の逃亡、将来証言、文末完結をすべて通した条件だけを巻全体へ拡大する。
事実抽出の許可外pageは、OllamaのJSON Schemaでブロック内pageを列挙にする構造化出力を次段階で試す。
Q4_K_Mの設定改善後も品質不足の場合だけ、より高精度な量子化を検討する。

実施結果（2026-08-15）: 3条件とも不合格。条件Aは詳細の途中切れを解消したが8,600字超へ冗長化し、
一覧は1,024 token上限で未完となった。条件Bは一覧を550 / 548字で自然停止させた一方、仁耀の
黒の皇帝殺害、最長10年の逃亡、将来証言を落とした。条件Cは役割表と最終状態を明記して約24分38秒へ
短縮したが、詳細1,207 / 1,398字、一覧1,181 / 839字で文字数契約を外れ、「大陸統一を目指す珀陽の構想」
という帰属誤りと保護作戦の目的変形も残った。局所ゲートを通過しないため、3回再現性試験、巻全体再生成、
高精度量子化には進まない。Qwen3.8は比較用登録に留め、公開文はSol経路を優先する。

#### Qwen / Gemma / bge-m3のMLX移行実測（2026-08-17）

M1 Max 64GB、macOS 26.6.1、`mlx-vlm 0.6.13`の専用venvで、次の固定revisionを
repo外へ取得し、全safetensorsを配布メタデータのSHA-256と照合した。

- `mlx-community/Qwen3.6-35B-A3B-4bit` — `38740b847e4c...`
- `mlx-community/gemma-4-12B-4bit` — `7d7c99c4d1b1...`
- `mlx-community/bge-m3-mlx-fp16` — `a37eddded9a6...`

Qwenは現行Ollama登録の`top_k=20 / top_p=0.95 / min_p=0 /
presence_penalty=1.5 / repeat_penalty=1.15`へ揃えた。終盤固定ケースは両方3/3、
第1ブロックはMLX約169秒 / Ollama約187秒、保存済み事実表からの要約4工程は
約519秒 / 約544秒だった。62,569 prompt tokenの77ページ一括判定もMLX約272秒 /
Ollama約286秒で完走したが、両方が同じ最終状態矛盾を返した。MLX常駐は約20GB、
Ollama表示は24GBで、試験中の追加swapはなかった。runtime差は小さく、長文誤りは
64GB不足ではなくQwen自体の限界と判定したため、MacのQwenはMLXを採用する。

bge-m3は配布物にpooling設定がなく、既定meanでは同一文cosine平均約0.701、
新旧Top-10一致率約53%となったため不採用とした。`1_Pooling/config.json`をCLSへ固定すると、
50入力の同一文cosine平均0.999985・最小0.999968、6クエリの旧/新/交差Top-5・Top-10が
すべて一致した。50件はMLX約3.28秒 / Ollama約6.24秒で、再indexなしでMLXを採用する。

GemmaはOllamaが終盤固定ケース3/3だったのに対し、MLXは3回とも誤答した。
人物抽出8ページもOllamaが`茉莉花`を約5.31秒で返した一方、MLXは不在の`珀陽`を加え、
続けて`<image|>`を含む875 tokenを出して約47.7秒を要した。MLX常駐RSS約11.5GiB、
swap増加なしのためメモリ不足ではない。現行変換/runtimeのテキスト互換不良として
Gemma MLXを不採用にし、MacでもOllama `gemma4:12b`を保持する。

したがってMacの採用構成は**Qwen=MLX / bge-m3=MLX（CLS）/ Gemma=Ollama**の混在とする。
各モデルの旧Ollama登録は個別ゲートで扱い、Qwenとbge-m3だけをアプリ統合smoke後に削除できる。
Windows本番のQwen GGUF / llama-serverはrollbackとして維持する。詳細は
[ADR-0019](../../design/基本設計/ADR/0019_apple-silicon-mlx-inference.md)を参照する。

#### Nemotron Labs 3 Puzzle 75B MLX導入・早期ゲート実測（2026-08-17）

community mixed 4/6-bit変換を固定revision `695829721099...`で42.007GiB取得し、9 shardと
tokenizerのSHA-256を配布メタデータへ照合した。Puzzle対応`mlx-lm`は固定commit `0f88e16`の
専用venvへ隔離し、branch差分を監査した上で単体test 12件に合格した。checkpoint内のcustom Pythonと
`--trust-remote-code`は使っていない。既存Qwen / bge-m3を停止した排他serverはhealth、短答、
OpenAI互換streamingに成功し、warm短答は1.564秒だった。

他用途のComfyUIを停止しない実機条件では、server起動前後でsystem-wide swapが8.74GBから
最大33.79GBへ増え、空きメモリ指標は最小9%になった。OOMは起きず64GBへロードできたが、同時に
別のML workloadを使う安全余裕はない。

茉莉花官吏伝10巻74〜75ページの固定ケースでは、non-thinkingが134.142秒、入力2,568 / 出力35 tokenで
最終合意を「牢へ戻る」と誤判定した。thinkingは187.346秒、出力2,048 token上限まで`OCR`を反復し、
最終JSONを返さなかった。`low_effort`は48.073秒で終端したが、同じ誤判定に加えて指定enumを外した。
形式・意味の早期ゲートが不合格のため、32,768 token、4ブロック、巻全体要約には拡大しない。
本番既定値はQwen=MLX / bge-m3=MLX / Gemma=Ollamaを維持し、Nemotronのcheckpointとruntimeだけを
再評価用に残す。既存OllamaのNemotron 3.5 Lightningも別モデルとして保持する。

#### Nemotron 3.5 Lightning 30BのOllama / MLX再比較（2026-08-18）

ネット上の公式情報とMLX-LM実装を先に調査し、Mamba 2・MoE・Attention hybrid、30B total /
約3B active、公式sampling `temperature=1.0 / top_p=0.95`を確認した。MLX-LMは
long promptとcacheを提供するが、hybrid modelのcache制約とprefix不整合が未解決であり、
Nemotron-Hの`mtp.*`補助重みは変換時に除外される。ローカルでもcache有効時に
無関係な乱数promptへ直前回答の一部を返す汚染を再現したため、全比較をcache 0で取り直した。

4bitは公式`mlx-community`変換revision `55ac8c892611...`、6bitは
同じBF16元モデルをstock affine group 64で変換したrevision `bd2a75d36c78...`を使った。
4bit 4 shard、6bit 5 shard、tokenizerのSHA-256はすべて配布元値と一致した。6bitの設定・
chat templateは4bitと量子化幅以外に差がなく、25,667,608,448 bytes、実効6.50 bits/weightである。

74〜75ページ固定ケースの結果は次のとおりだった。

| runtime / 条件 | JSON | 中核意味判定 | wall time / output |
|---|---:|---:|---:|
| Ollama Q4_K_M direct | 1/1 | 0/1 | 9.216秒 / 154 token |
| Ollama Q4_K_M thinking | 3/3 | 3/3 | 59.413〜91.418秒。理由の言語・正規名まで含む契約は2/3 |
| MLX 4bit direct | 1/1 | 0/1 | 9.546秒 / 169 token |
| MLX 4bit thinking、8,192上限 | 3/3 | 0/3 | 43.690〜44.251秒 / 各2,359 token |
| MLX 6bit direct | 1/1 | 0/1 | 14.291秒 / 168 token |
| MLX 6bit thinking、8,192上限 | 0/3 | 0/3 | 237.164〜250.933秒 / 3回とも上限 |
| MLX 6bit thinking、12,288診断 | 1/1 | 1/1 | 268.377秒 / 9,205 token |

MLX 6bitは約24GB footprintで単独ロードでき、試験後は空きメモリ指標95%、
system-wide swap約3.0GBまで回復した。したがって4bitの誤答は量子化精度不足、
6bitの冗長thinkingはMLX経路の生成効率・終端運用の問題であり、64GB不足ではない。
6bitは上限を増やせば正解可能だが、Ollamaより大幅に遅く、cacheを使えずMTPもない。
通常の8,192 token早期ゲートを通らないため第1ブロックへ拡大せず、NemotronのMLX切替を
不採用とする。既存Ollama Q4_K_MとMLX checkpointは比較用に保持し、Macの採用構成は変更しない。

#### Nemotron 3.5 Lightning 30BのThinking利用再監査（2026-08-18）

前回評価器と保存JSONを再確認し、固定74〜75ページはOllama `think=true`と
10,172文字の`message.thinking`、MLX比較は`chat_template_kwargs.enable_thinking=true`を
実際に使っていたことを確認した。初回8〜27ページのThinking raw応答だけは未保存だったため、
NVIDIA公式例と同じ`temperature=1.0 / top_p=0.95 / max_tokens=16000`で取り直した。

固定ケースはdirect 1回が中核0/1、Thinking 3回が3/3だった。8〜27ページの汎用抽出は
Thinkingが559.465秒・16,000 tokenで`length`、24〜27ページへ縮めても414.988秒・16,000 token・
最終本文0文字で失敗した。directは20ページを225.731秒、4ページを63.734秒で完走したが、
自由抽出には話者・時点誤りが残った。その誤りを26〜27ページ・4項目の列挙Schemaへ分解すると、
direct 9.201秒とThinking 132.680秒の双方が全問正解した。

このためPhase 2へNemotronの巻全体試験を追加しない。比較用の最適経路は、短block direct抽出、
決定的検査、型付き局所照合を先に実行し、正解固定fixtureでdirectが不合格となる曖昧な最終状態判定だけ
Thinkingへ送る。MLX切替、本番既定値、自動公開は変更しない。

#### Ornith 1.5 35B-A3B MLX導入・GPU smoke（2026-08-21）

公式`ornith-ai/Ornith-1.5-35B-A3B-MLX-4bit`をrevision
`19504d912fa8fc7622bf6b1de3db5d5d890b1f02`へ固定し、14ファイル・19,530,936,278 bytesを
取得した。全LFS SHA-256 / Git object、4 shardの1,757 tensorとindexを照合し、custom Pythonなし、
stock `mlx-lm 0.31.3 / mlx 0.32.0`の`qwen3_5_moe`実装で扱えることを静的確認した。

公式通常sampling `temperature=0.6 / top_p=0.95 / top_k=20`、Thinking有効、cache 0、
同時実行1、prefill step 2,048、追加KV / activation量子化なしでM1 Max 64GBを試した。
短答は正答し、prefill 32.287 token/s、decode 50.911 token/s、peak 19.777GBだった。
512 prompt / 128 generation tokenのbenchmark 3回平均はprefill 304.922 token/s、
decode 51.780 token/s、peak 20.176GBで、system-wide swapは1,358.25MiBから増えなかった。

OpenAI互換APIは256 output tokenではThinking後の最終文が`length`で切れ、512では
289 completion token・`stop`となり、`message.reasoning`と`message.content`を分離した。
既存SSE正規化も173 completion token・usage付き`stop`で完走した。ただし3経路とも
「最終回答は1行だけ」という指定へ説明文を追加したため、厳密形式は未合格である。

現行`MlxBackend`は`mlx_vlm.server`用のトップレベル`enable_thinking`を使い、今回の
`mlx_lm.server`は`chat_template_kwargs`を使う。server既定Thinking有効のsmoke成功を
request単位のon/off互換とみなさない。runtime・64GB・APIの早期ゲートだけを合格とし、
次は74〜75ページ固定ケースとJSON契約を先に評価する。`NOVEL_DB_*`、自動公開、既存採用構成は
変更せず、巻全体試験にはまだ進まない。

#### Ornith本番採用の段階ゲート（2026-08-21）

本番採用評価は、固定74〜75ページのThinking 3回、8〜27ページのnon-thinking事実抽出、
`mlx_lm.server`向けbackend契約、4ブロック・隔離1冊、32K→64K→131K長文の順に進める。
前段不合格時は後段を実行しない。固定短窓は4-key JSON、enum、中核3判定、日本語正規名、自然停止を
3/3必須とし、第1ブロックはmarkerとpage範囲だけでなく既知の話者・場面・時点ずれを原文照合する。

試験は固定revision、`mlx-lm 0.31.3 / mlx 0.32.0`、cache 0、同時実行1、prefill step 2,048、
最大8,192 output tokenで行う。Thinkingは公式通常sampling
`temperature=0.6 / top_p=0.95 / top_k=20`とseed 3種を使用する。Linux本番DBはread-only、
成果物はローカル実験ディレクトリ、公開物・checkpoint・索引・環境変数は不変とする。
本番候補への昇格は重大誤り0、既存Qwenとの差分監査、人手承認までを必要条件とし、自動公開は含めない。

#### Ornith Gate A実測・停止判断（2026-08-21）

74〜75ページ固定ケースでは、non-thinking診断が厳格JSON・中核3判定・日本語正規名・自然停止へ
1/1で合格した（9.660秒、173 completion token）。ただし理由文は途中の「牢へ戻る」という意図を
「仮の返事」と説明しており、軽微な過剰解釈を手動監査で検出した。

Thinking 3回はすべて意味上の期待値と`仁耀` / `珀陽`に一致し、32.564〜33.720秒、
各1,206 completion tokenで自然停止した。一方、最終objectを3回とも`json`コードフェンスで囲み、
生contentの厳格JSONは0/3だった。フェンスを除く診断結果で事後的に合格条件を変更せず、Gate A不合格、
本番採用保留とする。fail closedにより8〜27ページ、backend契約、4ブロック、隔離1冊、長文は実行しない。
本番DB・公開物・索引・環境変数は変更せず、評価serverも停止済みである。

再試験候補は、単独JSONコードフェンスだけを扱うadapter仕様と回帰test、および
`chat_template_kwargs.enable_thinking`のrequest単位対応を先に確定した別プロトコルである。
現行結果を正規化後の3/3合格へ読み替えない。

#### Ornith Gate A2 / A3再評価（2026-08-21、実行前固定）

公式・upstream実装の再確認により、`mlx_lm.server`は`chat_template_kwargs`を受け取る一方で
`response_format`を生成制約へ使わず、`mlx_vlm.server 0.6.15`は`llguidance`による
`json_object / json_schema`制約とThinking併用修正を持つことを確認した。旧Gate Aを変更せず、
次の独立2経路を同じ固定fixtureで再試験する。

| Gate | runtime / 経路 | 事前固定した合格条件 |
|---|---|---|
| A2 | `mlx_lm.server` + 新規`MlxLmBackend` | raw objectまたは単独の小文字`json` fenceだけを厳格adapterが受理し、正規化後JSON・意味・正規名・enum・`stop`が3/3 |
| A3 | `mlx_vlm.server 0.6.15` + native `json_schema` | adapterなしの生contentが厳格JSONで、意味・正規名・enum・`stop`が3/3 |

A2 adapterはJSON全体を完了までbufferし、説明文、複数・別種fence、array / scalar、duplicate key、
非有限数、1MiB超過、構文不正、未終端、`length`を応答前に拒否する。同期・async、Thinking on/off、
usage有無をunit testし、GPU試験前に回帰testを通す。A3は`--max-num-seqs 1`、KV量子化なしで実行し、
同時requestのstructured-output processorずれを評価条件から除く。

いずれかが3/3なら合格した経路だけでGate Bへ進む。両方合格時は生成中からschemaを拘束できるA3を
本番候補として優先する。両方不合格ならfail closedで停止する。`NOVEL_DB_*`、公開物、索引、
checkpointは変更せず、非公式`mlx-openai-server`は両経路不合格時の別検討に留める。

A3の初回起動では0.6.13がtext-only Ornithにもvision tower 393 parameterを要求して停止した。
upstream issue #1812 / merged PR #1879と一致し、修正を含む公式0.6.15へ更新した。
`mlx 0.32.0 / mlx-lm 0.31.3`は維持され、追加は`websockets 17.0.1`だけである。configや重みを
加工せず0.6.15でA3を開始し、0.6.13の起動失敗は品質3試行へ数えない。

#### Gate A2 / A3合格とGate B不合格（2026-08-21）

A2は限定adapter後の厳格JSON・意味・正規名・自然停止が3/3、A3はadapterなしのnative
`json_schema`で同条件が3/3となった。両方合格時の事前規則どおりA3をGate Bへ採用した。
A2は27.753〜33.480秒・各1,206 completion token、A3は26.034〜37.697秒・
1,130〜1,910 completion tokenだった。常駐は約18.5〜19.0GiBでswap増加はなかった。

しかし固定8〜27ページの現行事実抽出は、書籍事実が214.303秒、人物別事実が183.516秒で
それぞれ8,192 tokenへ達し`length`となった。書籍事実118項目の先頭根拠は8〜20ページだけで、
全項目が末尾へ空の次page markerを付けた。芳子星・珀陽の話者入れ替え、主体誤り、簡体字・中国語の
混入もあり、上限拡大だけでは解消しない。Gate Bを不合格とし、Gate C / Dと本番配線を停止する。

公式カードは対象言語を`en`とし、評価対象もagentic coding中心である。最後の限定診断として、
現行Gate Bの判定を変更せず、固定20ページを4ページ×5窓へ分割し、A3 native schemaで各窓を
最大12事実・単一page・短い明示subject/action/reasonへ拘束するGate B2を1回だけ実施する。
公式`0.6 / 0.95 / top_k 20 / min_p 0`、Thinking、seed固定で全窓の自然停止、日本語、coverage、
既知高リスク窓を確認する。1窓でも不合格ならOrnithの日本語小説RAG採用を終了し、既存Qwenを維持する。

#### Ornith Gate B2不合格とbudget原因診断（2026-08-22）

Gate B2は12〜15、16〜19ページの2窓だけが合格し、8〜11、20〜23、24〜27ページは
8,192 completion tokenまでThinkingが続いてcontent 0字となった。全体は24事実、coverage 12〜19ページで、
5/5窓と全20ページを必要とする条件へ不合格だった。失敗reasoningには用語綴りの自己訂正ループと、
台帳外人物を既存正規名へ推測対応させる過程があった。

成功24事実の原文照合でも、芳子星と皓茉莉花の科挙推薦人関係を逆転した重大誤り、黒槐国行き承諾の
page帰属違い、不自然な日本語を確認した。構造だけでなく意味条件にも不合格のため、事前規則どおり
Ornithの日本語小説RAG採用を終了し、Qwen既定を維持する。Gate C / D、10巻A/B、巻全体、公開更新は行わない。

インターネット調査で確認したMLX-VLM 0.6.15の公式`thinking_budget`だけは、停止原因の分離に直接対応する。
同じ5窓へ`thinking_budget=4096`だけを追加するGate B3を1回実行し、上限時に`</think>`へ強制遷移できるかを
確認する。Gate B2の採否を変更する試験ではなく、全窓が構造・coverage・意味へ合格しても3 seed再現、
Qwen比較、手動承認までは本番候補へ戻さない。1窓でも失敗すれば追加GPU試験を終了する。

Gate B3は全5窓が`stop`、各12事実、8〜27ページcoverageへ改善し、4,096 tokenのThinking予算が
0.6.15で有効なことを確認した。しかし8〜11ページに簡体字`进`が混ざり、固定意味検査3件が欠落した。
60事実の原文照合では、8ページの主体混在、18ページの推薦人関係逆転、25ページの衝突理由誤帰属、
26ページの華副三司使→`苑翔景`誤登録が残った。停止性だけを解消しても日本語意味精度は救済できないため、
Gate B3も不合格とし、追加GPU試験、3 seed、Qwen比較、Gate C / D、巻全体、本番配線を終了する。
checkpointはupstream runtimeまたは変換更新時の比較用に保持し、既存Qwen採用構成を維持する。
評価serverは正常停止し、TCP 11440と関連processが残っていないことを確認した。

#### 不採用後の根拠引用先行診断（Gate B4、2026-08-22）

B3の不採用判定を覆さない解決調査として、誤りが集中した8、10、18、25、26、27ページだけを
単ページ・固定質問で再評価する。モデルには人物台帳を渡さず、固定page、本文からの連続引用、引用内の
主体表記、引用だけから言えるclaimを最大4件返させる。評価器側で引用の完全一致と主体包含を決定的に検査し、
推薦人方向、衝突命令、別人物の理由混入、役職名の誤対応、同一人物疑惑を固定意味条件で監査する。

公式samplingとThinkingを維持し、`max_tokens=4096 / thinking_budget=2048`、seed固定、1回、再試行なしとする。
6/6ページと全claimの手動照合へ合格した場合も役割は高リスク根拠選択器に限定し、既存Qwen比較前に
本番候補へ戻さない。不合格ならOrnith固有の追加GPU試験を終了する。本番DB、索引、公開成果物、
`NOVEL_DB_*`は変更しない。

Gate B4は6/6が`stop`とraw厳格JSONへ到達したが、12引用中の原文完全一致は5件、主体包含は6件、
両方の合格は1件だけで、ページ単位は0/6だった。固定意味条件も10/14で、18ページの推薦人関係、
25ページの衝突主体、26ページの同一人物疑惑、27ページの荷物検査許可が欠落した。人物台帳由来の誤リンクは
遮断できたが、直接引用の生成と複数論点保持が成立しないため、Ornith固有の追加GPU試験を終了する。

今後の共通pipeline改善候補は、原文spanへアプリ側で安定ID / offset / SHA-256を付け、LLMにはSchema enumの
IDだけを選ばせる根拠ID先行方式とする。原文はIDから決定的に復元し、曖昧一致補正を禁止する。各claimを
個別検証し、人物正規化を後段へ分けた上で、まず既存Qwen / Solの固定ケースで比較する。これはOrnithの
本番候補復帰を意味しない。

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
- Nemotron 3.5 Lightningは短窓thinkingだけ合格したが、directの固定意味判定と汎用抽出の
  出力契約・話者・ページ根拠・人物正規名で不合格となった。公式16,000 tokenへ広げても
  20ページと4ページのThinking抽出が未終端だったため、巻全体へ拡大せず本番経路へ配線しない。
  型付き2ページ局所照合はdirect 9.201秒で合格し、Thinking 132.680秒の追加効果がなかったため、
  入力分割とSchema拘束をThinkingより先に適用する。MLX 4bitは同じ短窓を3/3誤り、MLX 6bitは
  12,288上限なら1回正解したが9,205 output token・268.377秒を要した。64GBには入るがOllamaより
  非効率なのでMLXへ切り替えない。将来runtime・量子化・prompt adapterが改善した場合だけcache 0の
  早期ゲートから再試験する。
- Nemotron Labs 3 Puzzle 75BのMLX mixed 4/6-bitは64GBへロードできたが、system-wide swapの
  大幅増加、固定短窓の最終状態誤り、thinking反復、enum違反により早期ゲート不合格とする。
  32,768 token以上へ拡大せず、本番経路へ配線しない。upstream runtimeまたは変換更新時だけ再試験する。
- Ornith 1.5 35B-A3B MLX 4bitは約20.18GB peak、decode約51.8 token/sで64GB適合とAPI smokeに
  合格した。固定74〜75ページは意味上3/3正しかったが、Thinking最終contentのJSONコードフェンスにより
  事前固定した厳格契約へ0/3となり、Gate Aで本番採用を保留した。8〜27ページ以降はfail closedで未実施。
  単独JSONフェンスを限定除去するadapterと`mlx_lm.server`向けthinking契約を事前に実装・回帰testし、
  別プロトコルでGate Aから再合格するまでは現行`MlxBackend`へ本番配線しない。
- Qwen3.8-27Bは人物抽出の反復崩壊を抑えたが、許可外ページ事実、完成文の主体誤り、
  最終合意の欠落、途中切れが残った。Qwen3.6より約3.10倍遅く、完成品質も上回らないため、
  初回仮判定では現行Qwen3.6を置き換えず、本番経路へ配線しない。設定改善の3条件もすべて不合格で、
  役割表を明示しても帰属誤りが残ったため、Q4_K_Mより高精度な量子化と巻全体再試験には進まない。
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
