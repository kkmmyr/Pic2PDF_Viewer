# ADR-0019: Apple Siliconのローカル推論にMLXを追加する

- **Status**: Accepted
- **Date**: 2026-08-17
- **決定者**: プロジェクトオーナー
- **関連**: [ADR-0009](0009_llm-backend-llama-server.md) / [ADR-0018](0018_sol-primary-post-ocr-generation.md) / [小説RAG データ設計](../../詳細設計/機能別/小説RAG_データ.md) / [MacローカルLLM移行・比較計画](../../../log/計画/MacローカルLLM移行・比較計画.md)

## コンテキスト

M1 Max・64GBユニファイドメモリのMacで、Qwen3.6 35B-A3B、Gemma 4 12B、
bge-m3をOllama経由で比較・補助実行していた。Apple Silicon向けのMLX版は重みを
Metalから直接利用できる一方、既存アプリはOllama `/api/generate`、
llama.cppのOpenAI互換API、Ollama `/api/embed`だけを実装していた。

MLX移行でモデル名だけを変えると、thinking指定、sampling名、embedding応答形式が
一致しない。特にbge-m3のMLX配布物はpooling設定ファイルを含まず、既定のmean poolingでは
既存Ollamaベクトルと別空間になる。またQwenの現行Ollama登録にはモデルカードの設定に加え
`presence_penalty=1.5`があり、これを省くと長文要約が出力上限まで続く差を実測した。

Windows本番のQwen `llama-server`とLinux上の公開DBは安定稼働中であり、Mac向けの変更で
既定経路やrollbackを失うべきではない。OCR後の公開成果物はADR-0018によりSol主生成へ
段階移行しているため、MLX採用は対話QA・ローカル比較・オフライン代替の範囲で判断する。

## 検討した選択肢

| 選択肢 | 概要 | 判断 |
|---|---|---|
| A. MacでもOllamaを継続 | API変更なし | Apple Silicon専用runtimeの速度・常駐量の利点を使えず、bgeを含む比較目的を満たさない |
| **B. MLXを選択可能なbackendとして追加** | Macだけenvで切替、既定値は維持 | 採用。実測比較とrollbackを両立できる |
| C. 全環境の既定をMLXへ変更 | backendを一本化 | MLXはApple Silicon専用でWindows/Linux本番を実行できないため不採用 |
| D. OpenAI互換だから`LlamaServerBackend`をそのまま流用 | 新クラスを追加しない | thinkingとsamplingのボディ契約が異なり、設定欠落を検出しにくいため不採用 |

## 決定

1. 共通LLMモジュールへ`MlxBackend`を追加し、`/v1/chat/completions`のSSEを既存の
   Ollama互換イベントへ正規化する。`enable_thinking`はトップレベルへ送り、
   `repeat_penalty`は`repetition_penalty`へ変換する。`top_p`、`top_k`、`min_p`、
   `seed`、presence/frequency penaltyも明示的に転送する。
2. 小説RAGに`NOVEL_DB_LLM_BACKEND=mlx`、`NOVEL_DB_GEMMA_BACKEND=mlx`、
   `NOVEL_DB_EMBED_BACKEND=mlx`と`NOVEL_DB_MLX_BASE_URL`を追加する。
   `NOVEL_DB_LLM_MODEL`、Gemma系の各model設定、`NOVEL_DB_EMBED_MODEL`には、
   MLX選択時だけローカルディレクトリまたはHugging Face IDを設定する。
   Windows/Linux互換のため既定値は`llama_server` / `ollama` / `ollama`のまま維持する。
3. MLX serverは`127.0.0.1`だけへbindし、`--max-num-seqs 1`で起動する。
   生成モデルはQwen/Gemmaのどちらか1本を同じtext-generation cacheで逐次利用し、
   bge-m3は別embedding cacheへ常駐させる。長文処理中に別生成モデルへ切り替えない。
4. bge-m3はFP16版とCLS poolingを使用する。`1_Pooling/config.json`が無い状態の
   mean poolingは不採用とし、既存索引との交差検索一致を切替前ゲートにする。
5. Mac上の旧Ollama登録は、同一入力・samplingで固定ケース、役割別タスク、長文、
   検索互換を比較したモデルだけ削除できる。Windows本番のGGUFと`llama-server`は残す。

## 根拠と実測

- Qwen3.6 35B-A3B 4bitは終盤固定ケース3/3、構造化JSON、第1ブロックの形式・ページ範囲を
  合格した。第1ブロックはMLX約169秒、Ollama約187秒だった。
- 同じ保存済み事実表からの要約4工程はMLX約519秒、Ollama約544秒で、文字数ゲートは
  1,136字 / 561字と合格した。両runtimeとも一覧版で終盤を投獄と誤る既知のモデル誤りを残した。
- 77ページ・62,569 tokenの同一判定はMLX約272秒、Ollama約286秒で完走したが、両方とも
  「牢へ戻る」と「最長10年逃亡・将来証言」を矛盾して併記した。これはメモリ不足やruntime差ではなく
  Qwenの長距離推論限界として扱う。
- Qwenの常駐量はMLX約20GB、Ollamaの表示は24GBで、64GB環境で追加swapなしに完走した。
- bge-m3 FP16 + CLSは50入力の同一文cosineが平均0.999985・最小0.999968で、6クエリの
  旧/新/交差Top-5・Top-10順位がすべて一致した。50件はMLX約3.28秒、Ollama約6.24秒だった。
  mean poolingは平均cosine約0.701、同一空間のTop-10一致率約53%で不採用とした。
- Gemma 4 12B 4bitは不採用とした。終盤固定ケースはOllamaが3/3正解したのに対し、
  MLXは3回とも「牢へ戻る」と誤った。MLXは約22〜24秒、Ollamaのwarm実行は約10.3〜10.4秒だった。
- 実運用の人物抽出でも、8ページをOllamaは約5.31秒で`茉莉花`だけとしたが、MLXは
  `茉莉花, 珀陽`と不在人物を混入し、その後に`<image|>`を含む875 tokenを出して約47.7秒かかった。
  GemmaのMLXモデルは比較用に残すが、Macの既定はOllamaとし、旧登録を削除しない。
- Gemma MLXの常駐RSSは約11.5GiBで、試験前後のswap使用量は約4.19GiBのまま増えなかった。
  失敗は64GB不足ではなく、現行の変換ウェイト / chat template / runtime組合せの品質・終端互換である。

## 結果（Consequences）

### ポジティブ

- MacのQwenとbge-m3は品質・索引互換を維持しつつ、同等以上の速度と小さい常駐量で利用できる。
- 既存のWindows本番とrollbackを変更せず、環境変数だけでruntimeを切り替えられる。
- bge-m3は既存LanceDBを再構築せず段階移行できる。

### ネガティブ・受容したコスト

- MLX runtimeとモデルはrepo外の専用venv・ローカルディレクトリで別途管理する。
- 現行Gemma MLXは品質・速度ゲート不合格のため、Gemma用Ollama runtimeとの混在運用が残る。
- 将来Gemma MLXを再評価する場合、Qwen/Gemmaの逐次入替には再ロード時間が発生する。
- MLX上で別生成モデルを比較する際は、リクエスト中のモデル切替を避ける運用制約がある。
- samplingの転送漏れでも品質が変わるため、モデル変更だけでなくrequest bodyを回帰テストする必要がある。
- MLXへ変えてもQwenの長距離事実統合の誤りは解消しない。公開要約のSol主生成方針を維持する。

### 後続検証による補足（2026-08-22）

ポジティブ欄の「bge-m3は既存LanceDBを再構築せず段階移行できる」は、同じbge-m3の
runtimeをOllama系からMLXへ切り替えて既存vectorとのAPI・次元互換を保つ判断を指す。
保存済みLanceDB内容の完全性を保証した記述ではない。後続の検索基盤監査では、対象snapshotの
`chunks`に重複32行とSQLiteからのID欠落2,781件を確認したため、このtableは移行元として再利用しない。
page-level ICU検索を導入する場合は、対象pageを別tableへ完全再構築してSQLiteとの件数・ID一致を
確認する。[小説RAG 検索・QA設計 §10](../../詳細設計/機能別/小説RAG_検索QA設計.md#10-日本語検索基盤の比較検証ゲート)を
後続判断の正本とし、本ADRのMLX runtime採用判断そのものは変更しない。

## 将来の再評価条件

- MLX serverが複数生成モデルの安全な並行cacheまたは明示的なrequest queueを提供する。
- モデル変換、chat template、pooling、sampling既定値が更新され、固定比較の結果が変わる。
- 131,072 token級でswap増加、OOM、著しい速度低下が再現する。
- Apple Silicon以外を含めて推論runtimeを一本化する必要が生じる。

## 追補: Nemotron Labs 3 Puzzle 75B（2026-08-17）

75.3B total / 9.3B activeのNemotron Puzzleを64GB Macで比較する場合、既存採用版の
`mlx-vlm 0.6.13`ではなく、異種MoE幅に対応した`mlx-lm` feature branchが必要になる。
このruntimeは固定commit `0f88e16`の専用venvへ隔離し、mixed 4/6-bit checkpointも
固定revision `695829721099e64aeaae22fa2f81d7740815a49e`で取得する。

配布者のM2 Max 64GB実測がpeak約49.7GBであり、既存Qwen / bge-m3 serverとの同時常駐には
安全余裕がない。そのため、Nemotronはlocalhost限定の比較serverとして排他起動し、Qwen / bge-m3を
停止してからロードする。現行`MlxBackend`と`mlx_lm.server`はthinking指定のbody契約も異なるため、
品質・メモリ・API互換ゲートが完了するまでは`NOVEL_DB_*`既定値と自動公開へ配線しない。
この追補はQwen=MLX / bge-m3=MLX / Gemma=Ollamaという本ADRの採用構成を変更しない。

同日のM1 Max 64GB実測では単独serverの起動とOpenAI互換streamingには成功したが、他用途の
ComfyUIを残した条件でsystem-wide swapは8.74GBから最大33.79GBへ増え、空きメモリ指標は
最小9%まで低下した。さらに74〜75ページ固定ケースはnon-thinkingと`low_effort`が最終合意を誤り、
通常thinkingは2,048 tokenの反復で終端しなかった。したがって64GB適合性を「ロード可能」に限定し、
実用上のメモリ余裕と小説品質は不合格とする。32,768 token以上の試験と本番配線には進まず、
checkpointと専用runtimeだけを将来の再評価用に残す。

## 追補: Nemotron 3.5 Lightning 30BのMLX再評価（2026-08-18）

75Bより小さい30B-A3BをM1 Max 64GBで再評価した。既存Ollama
`nemotron-3.5-lightning:30b-a3b-q4_K_M`を基準とし、同じBF16配布元から
`mlx-lm 0.31.3`で変換されたaffine group 64の4bit版と6bit版を、
同じ74〜75ページ、同じJSON形状、同じsamplingで比較した。4bitと6bitの
`config.json`およびchat templateの差は量子化幅だけである。

Nemotron-Hのprompt cacheを有効にした最初の試行では、後続の無関係な乱数質問へ
直前回答の一部を返すcache汚染を再現した。cacheを0へすると正しく別回答になったため、
以下の比較はすべて`--prompt-cache-size 0 --prompt-cache-bytes 0`で取り直した。
MLX変換は`mtp.*`補助重みを除外しており、現行MLX経路ではOllamaの
`draft_num_predict=2`相当のMTP speculative decodingも利用できない。

| runtime / 量子化 | direct | thinking | 実測 |
|---|---|---|---|
| Ollama Q4_K_M | 9.216秒、意味不合格 | 3/3で中核3判定に合格 | 59.413〜91.418秒。理由の言語・人物名まで含む契約は2/3 |
| MLX 4bit | 9.546秒、意味不合格 | 0/3。3回とも同じ誤判定 | 43.690〜44.251秒、各2,359 output token |
| MLX 6bit | 14.291秒、意味不合格 | 8,192上限では0/3、すべてJSONなし | 237.164〜250.933秒、3回のthinking内容も同一 |
| MLX 6bit診断 | — | 12,288上限の1回は中核3判定に合格 | 9,205 output token、268.377秒 |

保存済み初回評価器はOllama requestへ`think=true`を明示し、固定ケース成果物にも
10,172文字の`message.thinking`が残っている。MLX再評価も
`chat_template_kwargs.enable_thinking=true`を明示しており、前回比較がnon-thinkingだったという
訂正は不要である。ただし初回の第1ブロックthinking失敗はraw応答が保存されていなかったため、
2026-08-18にNVIDIA公式例と同じ`temperature=1.0 / top_p=0.95 / max_tokens=16000`、
Ollama native `think=true`で再監査した。

現行NVIDIA NIMの同系30B例には`reasoning_budget=16384`もあるが、今回固定したLightning 4bit / 6bitの
chat templateは`enable_thinking`だけを参照し、`reasoning_budget`と`low_effort`を実装していない。
Ollama native Thinking APIにも当該モデル向けの独立budget指定はないため、別checkpointまたはruntimeへ
更新するまではローカル最適化条件に含めない。

8〜27ページは入力21,229 tokenに対してthinkingが16,000 tokenを使い切り、559.465秒後に
`finish_reason=length`、必須マーカー欠落となった。24〜27ページへ縮めても414.988秒・
16,000 token・最終本文0文字で失敗した。対してdirectは20ページの2工程を225.731秒、
4ページを63.734秒で完走した。4ページdirectには話者・時点誤りが残ったが、その誤りを
26〜27ページ・4項目の列挙Schemaへ分解した局所照合はdirect 9.201秒、thinking 132.680秒で
ともに全問正解した。よってNemotronのthinkingは短い入力という条件だけでは使用せず、
固定fixtureでdirectが落ちる曖昧な最終状態判定へ限定する。汎用抽出は短いblockのdirectと
決定的・型付き照合を先に用いる。

MLX 4bitの常駐は約16.9GiB、6bitのphysical footprintは約24GBであり、6bit試験後も
空きメモリ指標95%、system-wide swap約3.0GBまで回復した。したがって4bitの誤判定と
6bitの冗長thinkingは64GB不足ではない。4bitは量子化精度不足、6bitは正解可能だが
MLX上で出力上限・時間・cache無効化・MTP非対応の運用コストが大きいと判断する。

Nemotron 30BのMLX切替は採用せず、短窓thinkingで3/3だったOllama Q4_K_Mを比較用に保持する。
6bitは8,192 tokenの通常ゲートを通らず、既存Ollama版も第1ブロックで話者・場面・根拠ページ・
正規名を誤っているため、MLX 6bitを第1ブロックや巻全体へ拡大しない。Macの採用構成は
Qwen=MLX / bge-m3=MLX / Gemma=Ollamaのまま変更しない。

## 追補: Ornith 1.5 35B-A3BのMLX導入・smoke（2026-08-21）

`ornith-ai/Ornith-1.5-35B-A3B-MLX-4bit`を固定revision
`19504d912fa8fc7622bf6b1de3db5d5d890b1f02`でrepo外へ取得した。配布物14件、
19,530,936,278 bytes（18.2GiB）で、4 shard、tokenizer、画像のSHA-256と通常Git objectを
配布メタデータへ照合した。safetensorsの1,757 tensor、index、data offsetも一致し、
checkpointにcustom Pythonはない。stock `mlx-lm 0.31.3 / mlx 0.32.0`が実装する
`qwen3_5_moe`を使用し、`--trust-remote-code`は付けない。

公式モデルカードはThinkingを既定とし、通常タスクへ`temperature=0.6 / top_p=0.95 /
top_k=20`、公開benchmark再現へ`temperature=1.0`を示す。MLX-LM upstreamでは
Qwen3.5系hybrid modelのprefix cache再利用不整合と、M1 Max 64GB・40K〜75K prompt・
並行2 requestでのMetal resource limitが未解決である。初期評価はこの条件を踏まえ、
localhost限定、同時実行1、`--prompt-cache-size 0 --prompt-cache-bytes 0`、
`prefill-step_size=2048`、KV/activation追加量子化なし、Thinking有効で実施する。
正しさを優先し、速度だけを理由にyank済みの`mlx-lm 0.31.0`へ戻さない。

M1 Max 64GBでの短答は正答し、101 prompt tokenを32.287 token/s、145 completion tokenを
50.911 token/sで処理し、peakは19.777GBだった。`mlx_lm.benchmark`の512 prompt /
128 generation token・3回平均はprefill 304.922 token/s、decode 51.780 token/s、
peak 20.176GBで、試験前後のsystem-wide swapは1,358.25MiBのまま増えなかった。
OpenAI互換APIは256 output tokenではThinkingが枠を使い切って`finish_reason=length`となったが、
512では289 tokenで`stop`し、`reasoning`と最終`content`を分離した。既存SSE正規化も
173 completion token・`stop`で完走した。

ただし「最終回答を1行だけ」という短答契約に対し、standalone、API、SSEのすべてで説明文を
追加した。さらに現行`MlxBackend`は`mlx_vlm.server`向けのトップレベル`enable_thinking`、
Ornithで使う`mlx_lm.server`は`chat_template_kwargs.enable_thinking`を受け取る。
server既定をThinking有効にしたsmokeでは通信できたが、request単位の切替互換を示すものではない。
このため64GBへのロード・生成・API適合は合格、厳密形式と小説RAG品質、本番backend契約は未合格とし、
`NOVEL_DB_*`既定値、自動公開、Qwen=MLX / bge-m3=MLX / Gemma=Ollamaの採用構成を変更しない。

## 追補: Ornith 1.5の本番採用評価プロトコル（2026-08-21）

本番採用の可否は、smokeの正答や速度だけでは決めず、次の段階ゲートを順番に適用する。
評価中はLinux本番`novel.db`を`sqlite3 -readonly`で参照するだけとし、公開要約、人物辞典、
fact checkpoint、LanceDB、`NOVEL_DB_*`を更新しない。生応答にはreasoning、最終content、
finish reason、token数、wall-clock、sampling、入力SHA-256を分離して監査保存する。

1. **固定短窓**: 10巻74〜75ページの`format_page_blocks`結果
   （SHA-256 `7a44d23a1bdb263c7a67bcc3efa1405f1c3eeec33e076ff12efd3644e00e0f4e`）を使う。
   期待値は主promptへ渡さず、評価器だけが`final_action=continue_fleeing_up_to_10_years`、
   `old_fact_status=contradicted / partially_contradicted`、
   `erroneous_summary_status=contradicted`を保持する。Thinking有効でseedを変えた3回すべてが、
   4-key JSON、enum、意味、日本語の正規名、`finish_reason=stop`へ合格しなければ停止する。
   non-thinking 1回は現行既定経路の診断値として保存するが、Thinking 3回ゲートの代用にしない。
2. **限定第1ブロック**: 固定短窓に合格した場合だけ、8〜27ページ
   （SHA-256 `47f62bc67042c39dbf09d0b9213041d8a6a048c98a41a5d0e3341292f6c15007`）へ進む。
   現行`FACT_EXTRACTION_PROMPT`と`CHARACTER_FACT_EXTRACTION_PROMPT`をnon-thinkingで順に実行し、
   `[BOOK_FACTS]` / `[CHARACTER_FACT:正規名]`、自然停止、許可ページ、重複、正規名、parserを検査する。
   ページ範囲内というだけでは合格にせず、既知の話者・場面・時点ずれを原文窓と手動照合する。
3. **API/backend契約**: 第1ブロック合格後に、`mlx_lm.server`へ
   `chat_template_kwargs.enable_thinking`をrequest単位で送る実装と回帰testを追加する。
   thinking on/off、非stream / SSE、usage、stop / length、timeout、異常応答のfail closedを確認するまで
   `MlxBackend`や環境変数へOrnithを本番配線しない。
4. **4ブロック・長文**: API契約合格後だけ、8〜27、28〜49、50〜69、70〜84ページの全ブロック、
   隔離コピー上の詳細版・一覧版・人物辞典へ進む。全ブロック機械ゲートと固定高リスク箇所を通過した場合だけ、
   32,768、65,536、131,072 tokenの順に長文を拡大する。Metal error、未終端、継続的なswap増加、
   memory pressure悪化、重大な主体・時系列・限定条件誤りのいずれかで停止する。

固定条件はcheckpoint revisionと`mlx-lm 0.31.3 / mlx 0.32.0`、Thinking時の公式通常sampling
`temperature=0.6 / top_p=0.95 / top_k=20`、最大8,192 output token、cache 0、同時実行1、
prefill step 2,048である。段階途中のprompt調整で固定fixtureへ正解を漏らさず、条件を変えた結果は
別試行として扱う。本番候補への昇格には、固定短窓3/3、全ブロック契約、重大誤り0、既存Qwenとの差分監査、
手動承認をすべて必須とし、自動公開は別判断とする。

### Gate A実測と採否（2026-08-21）

固定74〜75ページをLinux本番DBからread-onlyで取得し、上記条件を変更せずGate Aを実行した。

| 経路 | 厳格JSON | 意味・正規名 | 終端 | wall time / completion |
|---|---:|---:|---:|---:|
| non-thinking診断 | 1/1 | 1/1 | 1/1 `stop` | 9.660秒 / 173 token |
| Thinking、seed 3種 | 0/3 | 生contentでは判定不能 | 3/3 `stop` | 32.564〜33.720秒 / 各1,206 token |

Thinkingの最終contentは3回とも、正しい4-key objectを単独の`json`コードフェンスで囲んだため、
生contentへの`json.loads`が失敗した。フェンスだけを限定的に除く診断では、中核3判定、`仁耀` / `珀陽`、
途中の「牢へ戻る」と最終的な「最長10年逃げ続ける」の区別は3/3で一致した。しかし正規化は事前の
合格条件に含めておらず、結果確認後にゲートを緩めない。seedを変えてもreasoningと最終contentは
3回同一で、sampling上の多様性も観測できなかった。

non-thinkingは機械ゲートに合格したが、「牢へ戻る」という途中の意図を根拠なく「仮の返事」と説明した。
最終状態の判定は正しくても理由に軽微な過剰解釈があるため、Thinking 3回の代替合格とはしない。

以上からGate Aは**不合格、本番採用保留**とする。fail closedによりGate Bの8〜27ページ、Gate Cの
backend実装、Gate Dの4ブロック・1冊・長文は実行しなかった。本番DB、公開物、checkpoint、LanceDB、
`NOVEL_DB_*`、Qwen=MLX / bge-m3=MLX / Gemma=Ollamaの採用構成は不変である。評価server停止後は
port `11440`と関連processが残っていないこと、system-wide swapが試験前後とも1,208.81MiBであることを
確認した。監査成果物は
`~/Library/Application Support/Pic2PDFViewer/experiments/ornith-1.5-35b-a3b-mlx-production-eval-20260821/fixed/`
へ保存し、`summary.json`のSHA-256は
`09cf7398dfba5f17fe5371f02b3e4154321a9398261e7f4b7386473f837c1741`である。

再評価する場合は、単独JSONコードフェンスだけを除去するadapter仕様を先に設計・testへ固定し、
`mlx_lm.server`向け`chat_template_kwargs.enable_thinking`対応と併せて別プロトコルとしてGate Aから
再実行する。今回の結果を正規化後の合格へ遡及変更しない。

### Gate A2 / A3再評価プロトコル（2026-08-21、実行前固定）

旧Gate Aの不合格を維持したまま、runtime差と出力正規化の責務を分離して再評価する。
公式`mlx_lm.server`のrequest fieldsと実装には`response_format` / JSON Schemaによる制約生成がなく、
`chat_template_kwargs`だけがrequest単位のThinking切替に使われる。対して導入済み
`mlx-vlm 0.6.15`は`response_format=json_object / json_schema`を`llguidance`へ接続し、
Thinking終了後だけschemaを適用する修正を含む。この差を隠すために同じbackend名へ統合せず、
既存`MlxBackend`を`mlx_vlm.server`用、新規`MlxLmBackend`を`mlx_lm.server`用として分ける。

1. **Gate A2 — MLX-LM限定adapter**: `format="json"`時だけ最終contentを完了までbufferし、
   生のJSON object、または前後が空白だけで中身が1個の小文字`json`コードフェンスを受理する。
   fence以外の文字を除去・補完せず、複数fence、説明文付きfence、別言語fence、array / scalar、
   duplicate key、`NaN` / `Infinity`、1MiB超過、構文不正、未終端、`finish_reason != stop`を
   `LLMError`として応答を一切返さずfail closedにする。受理後はUTF-8の正規JSON objectを1回だけ返す。
   この経路の合格は「モデルのraw厳格JSON」ではなく「限定adapter込みのAPI契約合格」と記録する。
2. **Gate A3 — MLX-VLM native structured output**: 同じcheckpointを`mlx_vlm.server 0.6.15`で
   単独起動し、トップレベル`enable_thinking=true`と`response_format=json_schema`を送る。
   adapterを通さない生contentが厳格JSON objectであることを3/3必須とする。continuous batchingの
   structured-output不整合報告を避けるため`--max-num-seqs 1`とし、KV量子化を使用しない。
3. 両経路とも旧Gate Aと同じ入力SHA-256、prompt、sampling、seed、意味・正規名・enum・自然停止の
   判定を使う。adapter unit testとrequest body testをGPU起動前に完走させる。どちらか一方が3/3なら
   その合格経路だけでGate Bへ進めるが、両方合格時は生成時点でschemaを拘束するA3を本番候補として
   優先する。両方不合格ならserverを停止し、Gate B以降へ進まない。
4. 非公式`mlx-openai-server`はOpenAI互換Schemaとreasoning parserを備える代替候補だが、
   runtime追加と依存差を伴うためA2 / A3がともに不合格の場合だけ別ADRで検討し、今回導入しない。

この再評価に必要な共通client実装と回帰testはGate A2の契約そのものなのでGPU試験前に追加するが、
`NOVEL_DB_*`への配線、既定runtime変更、自動公開は従来のGate C以後に据え置く。本番DB、公開物、
checkpoint、LanceDBを変更せず、raw応答とadapter後応答を別々に監査保存する。

A3の初回起動に使った`mlx-vlm 0.6.13`は、`vision_config=null`のtext-only checkpointにも
Qwen3.5のvision towerを生成し、存在しない393 parameterを要求して推論前に停止した。これはupstream
issue #1812と同一で、PR #1879により0.6.14へ修正済みである。checkpointやconfigを加工せず、
公式PyPIの0.6.15へ更新する。dry-runで既存`mlx 0.32.0 / mlx-lm 0.31.3`が不変であることを確認し、
追加依存は`websockets 17.0.1`だけとした。A3の3回評価は0.6.15で新規に開始し、0.6.13の
起動失敗を試行数へ含めず、互換性診断として別記録する。

### Gate A2 / A3実測と本番候補runtime（2026-08-21）

固定74〜75ページを両経路で3回ずつ再評価した。A2は生contentが3回とも単独`json` fenceだったため
raw厳格JSONは0/3だが、事前固定した限定adapter、意味、enum、正規名、自然停止は3/3だった。
A3はnative `json_schema`によりadapterなしの生content、意味、enum、正規名、自然停止が3/3だった。

| 経路 | 契約 | wall time / completion | 判定 |
|---|---|---:|---|
| A2 `mlx_lm.server` | raw 0/3、限定adapter後3/3 | 27.753〜33.480秒 / 各1,206 token | adapter込み合格 |
| A3 `mlx_vlm.server 0.6.15` | native厳格JSON 3/3 | 26.034〜37.697秒 / 1,130〜1,910 token | 合格・優先 |

A3の理由文には軽微なOCR風表現や不自然な日本語があったが、中核3判定は正しかった。生成中から
schemaを拘束でき、client側wrapper補正を必要としないA3だけをGate Bの本番候補runtimeとして選んだ。
両経路とも常駐は約18.5〜19.0GiB、試験中のsystem-wide swapは1,192.81MiBから増えなかった。

### Gate B実測・不合格と限定救済診断（2026-08-21）

固定8〜27ページ、現行prompt、`temperature=0.1 / repeat_penalty=1.15`、seed `20260813`、
request単位`enable_thinking=false`で、書籍事実と人物別事実を現行SSE backend経由で順番に実行した。

| 段階 | prompt / completion | wall time | 終端 / content |
|---|---:|---:|---|
| 書籍事実 | 16,681 / 8,192 token | 214.303秒 | `length` / 13,380字 |
| 人物別事実 | 8,552 / 8,192 token | 183.516秒 | `length` / 13,460字 |

書籍事実は118項目すべてが末尾へ中身のない次page markerを追加し、先頭根拠は8〜20ページまでで
21〜27ページへ到達しなかった。末尾の`- [page 20]`だけの項目により厳格validatorも停止した。
原文照合では、10ページの連続発言を芳子星と珀陽の間で入れ替える話者誤り、珀陽を`彼女`とする
主体誤り、`最好`、`心地而感到`、`常识`、`夕方法与夜`、`的人都`等の中国語混入を確認した。
人物別結果も3名の途中で切れ、同じ誤りと言語混入を複製した。旧Nemotronで確認した特定3誤りの
文字列だけは再現しなかったが、同じ種類の話者・page帰属誤りが別表現で残ったため合格へ読み替えない。

MLX processは約19.05GiB、空きメモリ指標95%、swap増加0であり、原因は64GB不足ではない。
出力上限だけを16Kへ増やしても、未到達ページ、話者誤り、言語混入、118件の不正markerを解消しないため
再試行しない。Gate Bは不合格とし、Gate C、残り3ブロック、隔離1冊、長文、本番配線へ進めない。

ただしruntimeのstructured outputが改善可能性を持つかを切り分けるため、Gate Bの合格条件を変更しない
独立の**Gate B2診断**を次の条件で1回だけ行う。

1. 8〜27ページを8〜11、12〜15、16〜19、20〜23、24〜27の固定5窓へ分ける。
2. A3のnative `json_schema`を使い、各窓を最大12事実、単一page enum、明示subject、180字以下の
   action / reason-result、公開正規名配列へ拘束する。人物別の第二生成は行わず、正規名配列から
   決定的に人物事実を再編できる形にする。
3. 公式通常sampling `temperature=0.6 / top_p=0.95 / top_k=20 / min_p=0`、Thinking有効、
   seed固定、最大8,192 token、同時実行1を使う。全窓がraw厳格JSON、`stop`、page範囲、件数、
   日本語、重複、全範囲coverageを満たすことを必要条件とする。
4. 9〜10、18〜19、26〜27ページの話者・場面・時点を原文照合する。どれか1窓でも未終端、
   中国語混入、重大な主体・時系列誤りなら救済不成立とし、Ornithを日本語小説RAGへ採用しない。

公式モデルカードのmetadataは`language: en`で、公開評価もagentic coding中心である。同系統Ornith 1.0には
公式samplingと`min_p=0`でも長めの実タスクで未終端となる報告があり、sampling変更だけを解決策としない。
MLX-VLM公式が示す`json_schema`の`maxLength`制約を使い、モデル能力と言語適合性を構造の暴走から分離する。
Gate B2が合格しても、Gate Bの現行pipelineが合格したことにはならず、別設計・回帰test・既存Qwen比較・
手動承認なしに本番設定や公開データを変更しない。

### Gate B2実測・救済不成立（2026-08-22）

事前固定した5窓を1回ずつ実行した。12〜15ページと16〜19ページだけがnative厳格JSON、`stop`、
各4ページcoverageへ合格し、8〜11、20〜23、24〜27ページは8,192 completion tokenまで
Thinkingが続いて最終contentを1文字も返さなかった。

| 窓 | prompt / completion | wall time | reasoning / content | 判定 |
|---|---:|---:|---:|---|
| 8〜11 | 3,527 / 8,192 token | 159.648秒 | 23,295 / 0字 | `length`、不合格 |
| 12〜15 | 3,430 / 5,234 token | 102.354秒 | 10,697 / 2,175字 | 12事実、合格 |
| 16〜19 | 3,427 / 7,656 token | 148.673秒 | 17,665 / 1,951字 | 12事実、合格 |
| 20〜23 | 3,734 / 8,192 token | 160.653秒 | 16,579 / 0字 | `length`、不合格 |
| 24〜27 | 4,000 / 8,192 token | 161.288秒 | 22,351 / 0字 | `length`、不合格 |

結果は2/5窓、24事実、coverage 12〜19ページだけで、Gate B2を不合格とする。失敗3窓では
JSON Schemaの本文生成まで到達していないため、主因はschema破損や64GB不足ではなく回答前Thinkingの
停止不良である。20〜23ページのreasoningは`三カ国会談`の綴りを繰り返し自己訂正し、24〜27ページでは
台帳にない人物を`苑翔景`や`鉦春雪`へ対応付けようとする推測を繰り返した。

成功した24事実も原文と手動照合し、18ページで原文の「芳子星は皓茉莉花の科挙推薦人」を
「皓茉莉花が芳子星の推薦人」と逆転する重大誤りを確認した。17ページで承諾した黒槐国行きを
18ページへ置くpage帰属違い、`脱獄の手助い証拠`などの不自然な日本語も残る。構造、coverage、
意味の複数条件に不合格であり、事前規則どおりOrnithを日本語小説RAGへ採用しない。Gate C / D、
巻全体、本番配線、自動公開へ進まず、既存Qwen構成を維持する。

成果物はローカル隔離先`gate-b2-structured-short-blocks/`へ保存した。`summary.json`のSHA-256は
`f4118631ce8b56db050a645430e1b504fc717eeff61ed099bb4a13f724df5e4b`である。

### 追加原因診断: Thinking budget（2026-08-22、実行前固定）

MLX-VLM 0.6.15にはThinking中のtoken数を数え、上限超過時に`</think>`を強制して回答へ遷移する
`thinking_budget`が実装されている。Ornithの配布chat templateはThinking有効時に`<think>`を
prompt末尾へあらかじめ開くため、budget検出条件にも合う。一方、upstreamにはモデルが独自に開始した
Thinkingではbudgetが効かない報告もあるため、効力を推測せず実測する。

Gate B2の採否を後付け変更しない**Gate B3原因診断**として、同一fixture、prompt、schema、sampling、
seed、5窓を維持し、唯一`thinking_budget=4096`を追加する。最大8,192 tokenの半分を回答用に予約し、
再試行はしない。全5窓が`stop`、raw厳格JSON、coverage、機械意味検査へ合格した場合だけ全事実を
手動照合する。これはruntime制御の有効性を測る診断であり、合格してもB2不合格や上記意味誤りを消さず、
3 seed再現、既存Qwen比較、人手承認なしに本番採用へ昇格させない。不合格なら追加GPU試験を終了する。

参考:

- [MLX-VLM公式README: Thinking Budget](https://github.com/Blaizzy/mlx-vlm#thinking-budget)
- [server batchingでbudgetを強制する修正PR #1228](https://github.com/Blaizzy/mlx-vlm/pull/1228)
- [budgetが適用されないモデル形状のupstream報告 #1819](https://github.com/Blaizzy/mlx-vlm/issues/1819)

### Gate B3実測・停止改善と品質不合格（2026-08-22）

同一5窓へ`thinking_budget=4096`だけを追加したところ、全窓が4,902〜5,110 completion token、
97.706〜100.554秒、`stop`でJSON本文まで完了した。各窓12事実、8〜27ページのcoverageも得られ、
MLX-VLM 0.6.15がOrnithのpre-open Thinkingへbudgetを実際に適用できることを確認した。

| 窓 | completion | wall time | reasoning / content | 構造判定 |
|---|---:|---:|---:|---|
| 8〜11 | 5,110 token | 100.554秒 | 11,594 / 2,170字 | 簡体字`进`混入で不合格 |
| 12〜15 | 5,057 token | 98.917秒 | 10,340 / 2,122字 | 合格 |
| 16〜19 | 4,987 token | 97.706秒 | 11,203 / 1,947字 | 合格 |
| 20〜23 | 4,980 token | 99.526秒 | 7,126 / 1,990字 | 合格 |
| 24〜27 | 4,902 token | 98.025秒 | 11,469 / 1,816字 | 合格 |

ただし機械意味検査は、10ページの芳子星による「唯一で完璧な正答」と珀陽の「両方好き」、
26ページで明かされる新人文官への衝突命令を抽出できず不合格だった。60事実の原文手動照合でも次の
重大誤りを確認した。

- 8ページで皓茉莉花の戦争への葛藤と「白楼国を平和にしたかった」という理由を、珀陽をsubjectとする
  事実へ混在させた。
- 18ページで「芳子星は皓茉莉花の科挙推薦人」を再び逆転し、「皓茉莉花は芳子星の推薦人」とした。
- 25ページの新人文官による衝突理由へ、本人の命令ではなく皓茉莉花側の「四日かけた準備」を誤帰属した。
- 26ページで華副三司使を正規名`苑翔景`へ誤対応し、同一人物疑惑の事実にも誤った人物台帳リンクを付けた。
- `进入`、`黑曜城`、`髪の格子ない`、`晴らみせる`など、日本語として不適切な表記が残った。

reasoning末尾は全窓で文や検討の途中に切れ、強制`</think>`後にJSONへ遷移していた。これは停止時間を
有界化する運用機能として有効だが、未完の推論を正答へ修復する機能ではない。Gate B3は60事実と全pageを
返しても、言語・主体・関係・因果・重要事実の条件で不合格とする。追加GPU試験、3 seed、Qwen比較、
Gate C / D、巻全体、本番配線へ進めない。checkpointは将来のupstream更新比較用に保持し、serverは停止する。

評価終了後にMLX-VLM serverを正常終了し、TCP 11440のlistenerとOrnith関連processが0件であることを
確認した。system-wide swapは1,176.81MiBで、評価開始前から増加していない。

成果物`gate-b3-thinking-budget-4096/summary.json`のSHA-256は
`d07e08709ad7098d0ced3d3ce419c844d4acf8910de46c8c120063188832519c`である。

### 不採用後の解決診断: 根拠引用先行Gate B4（2026-08-22、実行前固定）

Gate B3で停止性と意味精度を分離できたため、Ornithの汎用事実抽出不採用と既存Qwen維持は変更しない。
その上で、ユーザーから別途依頼された原因解決調査として、誤りが集中した8、10、18、25、26、27ページを
1ページずつ固定質問で監査するGate B4を隔離実行する。目的はOrnithを一般抽出器へ戻すことではなく、
高リスク主張の**原文根拠選択器**という狭い役割が成立するかを測ることである。

各requestはnative厳格JSON Schemaで最大4件の`evidence_records`だけを返す。各recordは固定page、
ページ本文から改変せず連続コピーした20〜360文字の`evidence`、その引用内に実在する`subject_span`、
引用だけから言える160文字以下の`claim`を持つ。人物台帳と`canonical_characters`は入力・出力から外し、
役職名を既存人物へ推測対応させる経路を遮断する。評価器は`evidence in source_page`、
`subject_span in evidence`を決定的に検査し、JSON、自然停止、日本語、重複、固定意味条件も独立判定する。

samplingは公式推奨の`temperature=0.6 / top_p=0.95 / top_k=20 / min_p=0`、seed固定、
`enable_thinking=true`を維持する。単ページ化により推論量を減らし、`max_tokens=4096`、
`thinking_budget=2048`で回答領域を予約する。再試行、後付けprompt変更、non-thinking救済は行わない。
コミュニティ実装ではOrnith系をnon-thinkingにすると反復・署名echoへ崩れる報告があり、公式もreasoningを
既定としているため、B4ではnon-thinkingを解決策として採用しない。

6/6ページが自然停止、厳格JSON、全引用一致、主体包含、固定意味条件へ合格した場合だけ全claimを手動照合し、
高リスク根拠選択器として既存Qwenとの比較候補に残す。合格しても汎用抽出、巻全体、本番配線、DB保存形式を
変更しない。1ページでも失敗、引用の改変、関係逆転、因果混入、重要根拠欠落があれば救済不成立として終了する。

調査根拠は次のように区別する。

- 公式: [Ornith README（reasoning既定と推奨sampling）](https://github.com/ornith-ai/Ornith-1/blob/main/README.md)、
  [MLX-VLM Thinking Budget](https://github.com/Blaizzy/mlx-vlm#thinking-budget)、
  [llguidance（JSON Schema等の文法制約）](https://github.com/guidance-ai/llguidance)
- 一次研究: [span単位の根拠整合を扱うPsiloQA](https://aclanthology.org/2025.findings-emnlp.626/)
- 非公式・利用者報告: [mere-runのOrnith runtime知見](https://github.com/sawfwair/mere-run/blob/main/docs/runtime/text.md)、
  [llama.cpp grammar利用者議論](https://github.com/ggerganov/llama.cpp/discussions/6651)

JSON Schema / grammarは出力可能tokenを構文上制約する仕組みであり、本文との意味的一致を証明するものではない。
そのためB4の中心はschema追加ではなく、原文引用の完全一致検査と意味ゲートの分離である。

### Gate B4実測・直接引用方式の不成立（2026-08-22）

事前固定した6ページを各1回実行し、6/6が`stop`、raw厳格JSON、reasoningと最終contentを返した。
所要時間は18.833〜44.582秒、completionは897〜2,406 token、合計179.996秒・9,318 tokenだった。
8ページと25ページのreasoning末尾は文の途中で終わり、2,048 token予算による強制遷移と整合するが、
いずれもJSON本文は完成した。停止・構文問題は再発していない。

一方、全12recordのうち原文`evidence`へ完全一致したのは5件、`subject_span`が引用内に存在したのは6件、
両方を満たしたのは27ページの来現に関する1件だけだった。ページ合格は0/6、固定意味条件は10/14である。

- 8ページは意味上正しいclaimを返したが、引用内の`戦争`を`戰爭`へ改変した。
- 10ページは4件のclaim自体は正しかったが、全件で引用外の話者名を`subject_span`へ置いた。1引用では
  原文改行も除去し、連続spanではなくなった。
- 18ページは珀陽が茉莉花を国外へ出す点だけを返し、子星が茉莉花の科挙推薦人である関係を欠落した。
  reasoningでは2引用を列挙していたのに、最終JSONは1件だけだった。
- 25ページは`なにか`を`なかが`、`座りこむようにして`を`座りこむとして`等へ多数改変し、
  行為主体を求めた`subject_span`も茉莉花にした。
- 26ページは衝突命令を正しく要約したが、引用を`立ち上がらせろ`から`立ち上げませろ`へ改変し、
  暗茉莉花の同一人物疑惑を欠落した。ここでもreasoningは2件を予定し、最終JSONは1件だった。
- 27ページは`いる`→`ある`、`似ている`→`似てる`、`犀輿は`→`犀輿是`等の改変と、引用外の長い
  `subject_span`を生成した。犀輿の荷物検査提案は拾ったが、来現が許可した対象をclaimへ残さなかった。

人物台帳を入力から外した結果、華副三司使を`苑翔景`へ結ぶ誤対応と新人文官への四日間の準備理由混入は
再発しなかった。ただしこれは当該推測経路を閉じた効果であり、引用改変と重要論点欠落を補えない。
開始前後のsystem-wide swapはともに1,168.81MiBで、終了後memory freeは96%、TCP 11440と関連processは
0件だった。今回も64GB不足ではなく、現checkpoint / 4bit / runtime組合せの日本語転記・指示追従・
複数論点保持の品質問題である。MLX単体または量子化単体へ原因を限定する比較根拠はない。

直接引用をモデルに再生成させる案は不採用とする。次の一般解は、アプリが原文spanへ安定IDとoffsetを付け、
モデルにはSchema enumの`evidence_id`だけを選ばせ、アプリが原文を決定的に復元する方式である。
これで転記改変は構造上排除できるが、B4で観測した重要論点欠落とclaimの意味は別検査が必要である。
Ornithについては事前規則どおり追加GPU試験を終了し、この方式を実装する場合も先に既存Qwen / Sol経路で
固定評価する。本番設定、DB、索引、公開成果物は変更しない。

成果物`gate-b4-evidence-first/summary.json`のSHA-256は
`0ed2020205e6f46aabbfaa17998e2fa57f74a7d5adb54010cfaba10944f6cbba`である。
