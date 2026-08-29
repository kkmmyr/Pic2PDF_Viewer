# OCR設計書

> status: living | last-verified: 2026-08-29

<!-- contract-owner: ocr-publication -->

縦書き小説をSurya OCR 2でテキスト化し、入力完全性検査、ページ品質検査、画像照合QAを
通過した結果だけを `novel.db` へ公開する設計である。yomitokuは独立照合・比較・
後方互換用エンジンとして残す。

2026-08-19からは[ADR-0021](../../基本設計/ADR/0021_sol-image-ocr-campaign.md)に基づき、
固定manifestの原画像をGPT-5.6 Solで読み取る版管理付きcampaignを別経路として段階導入する。
現行Suryaの機械性能評価、B-35 formal holdout、Sol画像OCRの運用品質比較は混同しない。

- 現在の公開条件と運用上の意味は本書を正本とする。
- 機械判定値は `scripts/maintenance/ocr_quality_policy.json` を正本とし、本書へ複製しない。
- 未完了作業は [小説OCR品質改善 実装計画](../../../log/計画/小説OCR品質改善_実装計画.md)、
  実測経緯は [OCR品質改善 技術知見](../../../log/技術知見/OCR品質改善_技術知見.md) を参照する。
- OCR結果の取り込み先は [小説RAG パイプライン設計](小説RAG_パイプライン設計.md) と
  [検索QA設計](小説RAG_検索QA設計.md) を参照する。
- sourceの正本は`doujin` / `comic` / `novel`の3値である。本書のOCR公開pipelineは
  `novel`（`kindle_novel/images`）だけを対象とし、`doujin`（ADR-0003当時の旧名`generated`）と
  `comic`は対象外である。

## 1. アーキテクチャ

```text
kindle-pdf/main_novel.py
  -> kindle_novel/images/{書籍名}/*.png
  -> POST /api/ocr/run
  -> rebuild_jobs / job_state.py / job_targets.py / job_executor.py
  -> ocr_run_store.py（入力SHA固定・未完了ページ再開）
  -> extractor.py -> $OCR_PYTHON ocr_worker.py --manifest <一時JSON>
  -> Surya OCR 2 + yomitoku独立照合
  -> ocr_page_resultsへページ単位チェックポイント
  -> awaiting_qa
  -> 全ページの画像照合（OK / 修正 / 保留）・run承認
  -> pages / pages_fts / books.ocr_done_atを同一公開処理で更新
```

Sol画像OCR campaignは次の別経路を使う。

```text
medaroserver 数値名PNG -> immutable campaign manifest（book/page/SHA）
  -> 冊子単位に最大3 workerへ分割 -> GPT-5.6 Sol 独立候補A/B
  -> 第三workerの列coverage・読順検査 -> resolved OCR artifact
  -> schema・manifest・画像SHA・全標本集合検証 -> ocr_runs / ocr_page_resultsへimport
  -> 冊子完全性・画像照合QA -> ocr_publicationsのactive run切替
  -> pages / pages_fts / books.ocr_done_atを同一transactionで更新
```

Sol workerはSQLiteへ直接接続しない。worker認証情報とCodex認証cacheはmedaroserverへ配置せず、
manifestで許可された画像と成果物だけを保護された経路で受け渡す。

旧 `ocr_service.py` とスレッド常駐方式は撤去済みである。ジョブキュー、スキップ条件、
API契約は [詳細設計書_バックエンド編](../詳細設計書_バックエンド編.md) を正とする。

### Windows OCR agent

`OCR_AGENT_ENABLED=true` のLinux本番では通常workerは `mode=ocr` をclaimせず、Windows agentが
共有トークンで1件ずつclaimする。Linux側が入力連番・SHA-256、`ocr_runs`、job/run対応を固定し、
Windows側は登録済み画像URLだけを取得してページ結果・heartbeat・完了状態をAPIへ返す。
Windowsから本番SQLiteを直接開かない。

### 主要環境変数

| 変数 | 既定値 | 意味 |
|---|---|---|
| `OCR_PYTHON` | OS別OCR venv | OCR workerを実行するPython |
| `OCR_PACKAGE_PATH` | Windows: `D:\61.tool\common\ocr` / Mac: `~/Developer/KRAuto/ocr` | subprocessへ `OCR_PATH` として渡すパッケージパス |
| `OCR_YOMITOKU_DEVICE` | `auto` | yomitokuの実行デバイス。`auto`は`cuda` → `mps` → `cpu`の順で解決 |
| `OCR_ENGINE` | `surya2` | `surya2` / `yomitoku` |
| `SURYA_INFERENCE_URL` | `http://127.0.0.1:8768/v1` | OpenAI互換推論URL |
| `SURYA_MODEL` | `surya-ocr-2` | 推論モデル名 |
| `SURYA_MODEL_REVISION` | `unversioned` | `ocr_runs.model`へ保存する固定版識別子。新規runでは空値・`unversioned`を拒否する |
| `SURYA_REQUEST_TIMEOUT_SEC` | `600` | 1ページのタイムアウト |
| `SURYA_MAX_ATTEMPTS` | `3` | 画像候補の最大試行数 |
| `OCR_WORKER_INACTIVITY_TIMEOUT_SEC` | `2100` | workerのstdout無通信をhangとみなす期限。超過時はterminate後、15秒で終了しなければkillする |
| `OCR_QUALITY_MIN_INK_COVERAGE` | `0.85` | OCR bboxの文字候補成分最低coverage |
| `OCR_CROSSCHECK_ALL_PAGES` | `true` | Surya合格ページもyomitokuで再読する |
| `OCR_CROSS_ENGINE_MIN_SIMILARITY` | `0.85` | エンジン間の最低一致率 |
| `OCR_AGENT_ENABLED` | `false` | Windows agentへOCRを委譲する |
| `OCR_AGENT_HEARTBEAT_TIMEOUT_SEC` | `300` | agent heartbeat期限 |

`yomitoku`の実行デバイスは、`OCR_PYTHON` / `OCR_PACKAGE_PATH`が指す外部OCR環境で
`OCR_YOMITOKU_DEVICE`を解決する。WindowsのNVIDIA環境では`cuda`、Apple Siliconでは`mps`を
使用し、`auto`（既定値）は`cuda`、`mps`、`cpu`の順で利用可能なデバイスを選択する。
MacでMPSを利用する場合は、MPS対応済みのyomitoku（v0.11.0以降）とPyTorchを使用する。
`mps`を明示したのにMPSが利用できない場合、またはMac上の外部ラッパーがデバイス指定を受け付けない
場合は、CPUへ黙って切り替えずworkerを失敗させる。
デバイス値の検証と新旧ラッパーAPIへの変換は`yomitoku_runtime.py`へ集約し、
`ocr_worker_engines.py`は補助照合と後方互換OCRのどちらからも同じ初期化関数を呼ぶ。

### 責務境界

| ファイル | 責務 |
|---|---|
| `backend/routers/ocr.py` | run / stop / status / QA API |
| `backend/services/novel_db/extractor.py` | OCR subprocess呼び出し |
| `backend/services/novel_db/ocr_worker.py` | standalone CLI、manifest読込、engine選択のprotocol shell |
| `backend/services/novel_db/ocr_worker_protocol.py` | task・page・progressの型、JSONL payload生成・出力 |
| `backend/services/novel_db/ocr_worker_engines.py` | 画像読込、Surya/yomitokuのページ処理、候補選択 |
| `backend/services/novel_db/ocr_provenance.py` | 実行版manifest、source/model SHA、候補本文/raw出力SHAの生成・検証 |
| `backend/services/novel_db/ocr_candidate_selection.py` | primary/externalの文字量差をQAリスクとworkerで共有する純関数 |
| `backend/services/novel_db/ocr_worker_session.py` | 環境設定、server世代、再起動policy、task進行のorchestration |
| `backend/services/novel_db/ocr_job_application.py` | run準備、worker process結果の保存、失敗分類、QA準備のapplication service |
| `backend/services/novel_db/surya_types.py` | OCR・layout・品質・再起動policyの型 |

親processはworkerのJSONLを別threadで読み、最後のstdout eventから
`OCR_WORKER_INACTIVITY_TIMEOUT_SEC`を超えた場合にworkerを回収して失敗とする。page結果が一部返っていても
呼出し全体を成功扱いせず、後続の公開・FTS更新へ進めない。generatorの途中破棄時も同じ回収処理を行い、
孤児processを残さない。既定値は1ページの最大3試行を許容する値とし、隔離試験では短い期限へ上書きする。
| `backend/services/novel_db/surya_parsing.py` | 公式prompt、HTML/layout/bbox解析 |
| `backend/services/novel_db/surya_quality.py` | coverage、品質flag、補助OCR照合 |
| `backend/services/novel_db/surya_server.py` | llama-serverのhealth check・起動・終了 |
| `backend/services/novel_db/surya_transport.py` | OpenAI互換HTTP payload・response decode |
| `backend/services/novel_db/surya_runtime.py` | variant・layout fallback・品質選択workflow |
| `backend/services/novel_db/ocr_run_store.py` | SHA検証、run再開、チェックポイント |
| `backend/services/novel_db/ocr_page_classification.py` | ページ種別・layout候補 |
| `backend/services/novel_db/ocr_qa_staging.py` | 完全性検証、page分類、risk反映、必須QA page選定、`awaiting_qa`遷移 |
| `backend/services/novel_db/ocr_qa_review.py` | page review入力検証、採用候補検証、page単位のQA状態遷移 |
| `backend/services/novel_db/ocr_qa_queries.py` | QA run一覧・詳細、SHA照合付き画像path解決 |
| `backend/services/novel_db/ocr_qa_publication.py` | run承認条件、採用本文検証、books・pages・FTS・runの原子的な正式公開 |
| `backend/services/novel_db/ocr_publication_history.py` | legacy snapshot、active run履歴、Sol昇格・rollbackの原子的切替 |
| `backend/services/novel_db/ocr_publication_backup.py` | 公開・rollback前のSQLite Online Backup、manifest公開、publication noteへの世代参照付加 |
| `backend/services/novel_db/sol_ocr_campaign.py` | immutable manifest・pilot標本・worker割当の生成検証、画像export |
| `backend/services/novel_db/sol_ocr_holdout.py` | 既出pilot・B-35除外、fresh holdoutの品質非参照選定・封印・一度限りledger |
| `backend/services/novel_db/sol_ocr_import.py` | Sol page artifactのschema・SHA検証、idempotent checkpoint import、legacy差分report |
| `backend/tools/sol_ocr_v2.py` | 列証跡付きraw候補を自己SHA付きv2候補へ完全集合で正規化 |
| `backend/tools/sol_ocr_holdout.py` | fresh holdoutの作成・再検証・sealed/opened/retired ledger操作 |
| `backend/services/novel_db/ocr_qa.py` | QA公開関数のimport互換facade |
| `backend/services/novel_db/job_state.py` / `job_targets.py` / `job_executor.py` | job状態、対象解決、mode別application serviceへのdispatch |
| `backend/services/novel_db/surya_ocr.py` | package・standaloneの既存Surya import契約を保つ期限付きfacade |
| `backend/services/novel_db/ocr_staging.py` | run store・classification・QAの既存import契約を保つ期限付きfacade |
| `backend/services/novel_db/job_worker.py` | queue workerと既存monkeypatch pointを保つfacade |
| `D:\61.tool\common\ocr\ocr_engine.py` | yomitokuラッパー |

フロントエンドは`features/ocr/api.ts`をstatus / run / stop、QA、ground truthのHTTP境界、
`useOcrStatus`、`useOCRQaController`、`useOCRGroundTruthController`をQuery/mutation/input状態の
所有者とし、各Panelは表示とevent配線だけを行う。runの単冊指定`target_dir`は
request bodyではなくOpenAPI契約のquery parameterとする。status / run / stopを含む
OpenAPI生成型を`features/ocr/types.ts`から参照する。

### 互換facadeとテスト所有

- application codeは`surya_ocr.py` / `ocr_staging.py`を経由せず、責務所有moduleから直接importする。
- `surya_ocr.py`は`python ocr_worker.py`と同じdirectoryをimport rootにするstandalone利用、
  `ocr_staging.py`は既存拡張・保守コードのimport互換のためR3では残す。両facadeとも公開symbol identityを
  testで固定し、内部利用ゼロを維持したままR6で外部利用・rollback手順を再確認して撤去判断する。
- test所有は`test_surya_parsing.py`（prompt・HTML/layout解析）、`test_surya_quality.py`
  （coverage・外部OCR・crosscheck）、`test_surya_runtime.py`（session policy・fallback・transport）、
  `test_ocr_worker.py`（JSONL worker）、`test_ocr_staging.py` / `test_ocr_publication.py`
  （QA・原子的公開）とする。`test_surya_ocr.py`はfacade契約だけを検証する。

## 2. Surya OCR 2実行契約

- OCR jobは対象冊子ごとにrunと未処理taskを準備し、全冊分のtaskを1回のworker processへ渡す。
  workerから返るpageはbook名でrunへ対応付け、未知のbook名を受理しない。
- worker processまたはpage保存で例外が発生した場合は、準備済みの全runを同じ理由で`failed`にし、
  job失敗として再送出する。run準備前の失敗を未準備runへ波及させない。
- worker完了後は対象冊子ごとに入力SHAとpage完全性を検証して`awaiting_qa`へ進める。
  1冊のQA準備失敗はそのrunだけを`failed`にして後続冊を継続し、全冊の進捗更新後に
  `OCR quality gate failed: ...`として集約する。この段階ではcanonical `pages`へ公開しない。
- jobの`current_detail`に出すstage、book、page、attempt、server generation、detailの順序と
  区切りを維持し、workerのprogress eventをjob進捗へ写像する。
- QA開始は入力画像SHA・page数・page結果の完全性を再検証し、分類・risk flag反映後に
  全pageを`required`としてrunを`awaiting_qa / pending`へ遷移させる。B-35正式holdoutの
  機械単独総合合格前は、候補一致、通常散文、試し読み除外を理由に`not_required`へしない。
  canonical `books` / `pages`は変更しない。
- page reviewは`awaiting_qa` runだけを対象とし、state・page/layout分類・採用engine・補正文を
  検証して1pageだけを更新する。failed narrativeはCodex確認済み補正文なしで承認しない。
- run承認は`required`・`rejected`・未分類page/layoutが0件であること、入力SHAが不変であること、
  narrativeの採用本文が空でないことを正式公開前に検証する。非narrative pageは画像を保持し、
  canonical本文を空文字として公開する。
- 正式公開ではbook作成または更新、全page upsert、余剰page削除、FTS rebuild、runの
  `completed / approved`遷移を単一SQLite transactionで行い、途中失敗時は全変更をrollbackする。
- workerのstdoutは1行1JSONの`page` / `progress` / `fatal` event専用とし、
  server・modelのlogはstderrへ分離する。field、event順序、終了codeを内部分割で変更しない。
- `ocr_worker.py`はpackage importと`python ocr_worker.py --manifest ...`のstandalone実行を
  両方維持し、手動診断用の画像directory引数も互換経路として残す。
- worker所有serverだけをsession policyに従って再起動する。外部管理serverでは再起動を
  `server_restart_skipped`として通知し、workerから停止しない。
- server世代を切り替えてもtask indexを巻き戻さず、page eventの重複・欠落を許可しない。
- 1pageの画像復号・OCR・外部照合が失敗しても、そのpageを`worker_error`として出力し、
  manifest内の後続pageを継続する。manifest不正や未対応engineだけを`fatal`とする。
- 公式GGUF、mmproj、`llama-server.exe` のパスとSHA-256を固定し、自動更新しない。
- worker所有serverは有限ページ数、連続不合格、移動窓の不合格率超過で再起動する。
  外部管理serverはworkerから停止しない。世代、開始ページ、終了理由を監査ログへ残す。
- 公式のHTML+bbox、layout JSON、block HTMLの各promptを改変せず、画像→指示文の順で送る。
- OpenAI互換payloadは`temperature=0`、`top_p=0.1`に加えて`seed=0`を固定し、
  全画面・block・部分再OCRで同じ画像とpromptの候補を再現可能にする。
- 1並列・context 16,384を基準とし、長い本文を4,096 tokenで打ち切らない。
- キャプチャPNGを加工・上書きしない。再試行画像はメモリ上だけで生成する。
- `raw_output`、検索用 `full_text`、bbox、品質指標を分離して保存する。
- Surya合格ページも既定でyomitokuが独立再読する。候補一致は正解保証に使わない。
- selected本文が30文字未満なのにprimaryまたはexternal候補が300文字以上ある場合は、
  candidateの合否や反復の有無にかかわらず`candidate_content_conflict`を記録する。
  非narrative分類と長文candidateが衝突する場合は`page_type_text_conflict`も記録し、
  挿絵・空ページとして自動確定せず原画像確認へ送る。
- normal proseでprimaryに異常反復があり、externalが256文字以上かつ反復なしの場合は、
  externalのconfidence合否にかかわらずレビュー候補へ切り替える。採用結果には
  `external_recovered_primary_repetition` flagを残して必須QAへ送り、自動公開へ昇格させない。
- 異常反復は、同一長文行・複数行blockに加えて、改行を含まない生成ループも検査する。後者は
  空白・句読点を除いた内容文字の12文字n-gramが同一ページ内で8回以上現れた場合に不合格とする。短い台詞、
  擬音、通常の章見出しだけでは不合格にせず、候補選択・QA risk・公開前検査で同じ判定器を使う。
- normal proseでprimaryが合格し、externalがconfidence等で不合格でも、primaryが256文字以上かつ
  externalが30文字・2%以上長く、externalに反復がない場合はexternal本文をレビュー候補として採用する。
  この判定値はQAリスク検出と同じ純関数を使用し、`external_low_confidence_more_complete_candidate`
  flagを保持して必須QAへ送る。候補採用だけでconfidence不合格を品質合格・自動公開へ昇格させない。

### ページ品質ゲート

1. PNGが復号でき、`001.png`から欠番のない連番であること。
2. `div[data-label][data-bbox]` が解析でき、bboxが正規化座標0〜1000内であること。
3. ページOCRがlayout JSONを返した場合はタスク種別ドリフトとして検出し、layout→block経路へ
   切り替える。block OCRが再びlayout JSONを返す候補は本文として保存しない。
4. 局所エッジから得た文字候補をbboxが既定割合以上覆うこと。暗画素数だけでは判定しない。
5. 20文字以上の正規化block完全重複、12〜80文字の同一列4回以上連続、本文6,000文字超を
   反復・幻覚候補として不合格にする。
6. 非空出力に解析可能blockがなければ `malformed_output` とし、その候補のSurya再試行を止める。
7. 空白または非本文blockだけのページは本文ゼロを許容し、理由をflagへ残す。
8. 全候補不合格なら原画像のbbox単位block OCRを1回行う。最終不合格は `failed` とし公開しない。
9. 構造化ページの装飾coverage不足と、256文字以下の疎ページには限定例外を認めるが、
   監査flagとyomitoku照合を必須にする。不正bbox、重複、空本文は例外にしない。

confidenceは補助情報であり、列・文章欠落を直接表さない。yomitokuは最低値だけでなく中央値、
文字数加重平均、低confidence文字比率、構造、候補一致率を併用する。

## 3. 入力完全性と画面番号

- `ocr_page_results.page_no`、`pages.page_no`、検索結果はPNG由来のキャプチャ画面番号を正とする。
- Kindle紙面ページ番号はリフローにより画面送りと一致しない。紙面ページ番号として表示しない。
- OCR入力は拡張子`.png`かつstemが数字だけの通常ファイルに限定する。桁数は固定しない。
  `008_debug_vis.png`、`cover.png`等は対象外とし、数値名PNGだけで1始まりの連番を検査する。
- 正式書籍だけを `kindle_novel/images/{書籍名}/` に置き、診断・中断画像は外へ分離する。
- OCR投入前に連番、復号、同一解像度、SHA完全重複、白紙候補、先頭・中間・末尾、Kindle終端を
  確認する。重複・白紙候補は数値だけで削除しない。
- 過去runの画面数や紙面ページ数を期待撮影画面数へ流用しない。
- `capture_state=captured`、`ocr_done_at`、`indexed_at`、OCR run状態は別の完了条件である。
- 通常の範囲限定Surya作業では `POST /api/ocr/run` に対象を明示し、1冊ずつ直列投入する。
- Sol campaignだけはimmutable manifestを冊子単位で最大3 workerへ分割できる。同じ冊子を
  複数workerへ割り当てず、成果物importと正規版切替はメインsessionが直列実行する。
- page artifactは`sol-ocr-page-v1`とし、campaign/pilot digest、sample・worker、model、prompt版、
  book/page、画像SHA、転記本文、判読注記、処理日時以外を受理しない。同じpage・SHA・本文の再送は
  idempotentに扱い、異なる本文の再送は競合として自動上書きしない。
- `sol-ocr-page-v1`は2026-08-19の初回pilot監査専用とし、新規pilot・全冊実行には使用しない。
  再開時は`sol-ocr-page-v2`で、同じ原画像を互いの本文を見ない独立session A/Bが右から左へ
  overlap付き列帯単位で転記し、各候補本文・列数・列先頭末尾anchor・候補SHAを別artifactへ保存する。
- A/Bと異なる第三sessionは原画像を左から右にも走査し、候補ごとの列coverage、読順、台詞境界、
  固有名詞、ルビ混入を検査する。checkerは画像にない本文を生成せず、A/Bの一方を選ぶか
  `needs_review` / `fail`にする。選択候補のcoverageが`complete`、読順が`pass`、重大欠落0の場合だけ
  `canonical_eligible=true`とする。A/Bが一致してもchecker検査を省略しない。
- v2 importは候補A/B、checker、resolved envelopeのSHA参照、producer/checker sessionの相違、
  prompt/policy SHA、campaign/pilot digest、画像SHAを検証し、manifestの全sample ID集合とartifact集合が
  完全一致しない限りDB transactionを開始しない。campaign・promptが異なるrunを再利用しない。
- 初回pilotとそこから調整した結果は`purpose=tuning`へ固定する。prompt/policy固定後、初回pilotと
  B-35 formal holdoutのpage key・画像SHAを除外した品質非参照のfresh holdoutを封印する。
  合格閾値を開封前に固定し、一度だけ評価する。既存OCRは候補生成・checker選択へ渡さず、評価時だけ
  提示順をblind化して比較する。開封後の標本は次回正式評価に再利用しない。
- fresh holdoutの画像exportは、manifest検証とledgerの`opened`記録が完了した後だけ許可する。
  export時にも全画像SHAとroot内相対pathを再検証し、`retired_to_tuning`後の再exportを拒否する。
- 既存版と再撮影版が併存する場合、旧画像・旧OCR・DBを検証付きバックアップへ退避し、
  新版だけを運用対象にする。旧版は復旧専用で保持する。

## 4. ステージング、QA、公開

OCR完了と公開承認を分離する。全ページ処理後はまず全pageを`required`として
`awaiting_qa`へ遷移し、原画像と候補を確認する。ページごとの運用判定は次の3段階とする。

- `OK`: 原画像と採用する機械OCR候補が一致する。API上は`qa_state=approved`とする。
- `修正`: 原画像照合済みの補正文を`selected_engine=codex`と`corrected_text`へ保存し、
  API上は`qa_state=approved`とする。
- `保留`: 固有名詞、崩れた文字、読順、分類を確定できない。API上は`qa_state=rejected`とし、
  解消するまでrunを公開しない。

確認時は次の理由を日本語で表示し、primary / externalの文字数と候補本文を同一画面で比較できるようにする。

- 前付、品質flag付きページ、各書籍の先頭・中間・終盤本文、挿絵混在、固有名詞を含むページ
- ページ種別 `narrative` / `toc` / `illustration` / `colophon_or_ad`
- layout種別 `normal_prose` / `structured` / `mixed_illustration` / `full_width` / `image_only`
- 本編後の第2書名・目次・人物紹介・試し読み境界、反復、UI混入、候補間の大幅な文字量差
- selected空本文と長文candidateの衝突、非narrative分類と長文candidateの衝突

公開時の不変条件は次のとおり。

1. QA未承認runは `books` / `pages` / `pages_fts` / LanceDBを変更しない。
2. `corrected_text`が非空なら `selected_engine=codex` を同じQA更新で保存する。
3. `required` / `rejected` / 未知のQA状態が残るrunは公開しない。
4. 公開本文、FTS、`books.ocr_done_at` は同一公開処理で整合させる。
5. 公開・rollbackは`BEGIN IMMEDIATE`で書き込み順を予約した後、canonical変更前にSQLite Online
   Backupを取得し、`integrity_check=ok`、SHA-256、run ID、操作種別をmanifestへ記録する。
   世代は`NOVEL_DB_DIR`の兄弟にある
   `ocr-publication-backups/`へ一時ディレクトリから原子的に公開し、backupまたはmanifest作成の
   失敗時は予約transactionをrollbackして旧公開本文と索引を保持する。publication noteには検証済み世代の
   参照を付加する。参照切れを避けるため自動削除は行わず、本番では世代サイズと空き容量を監視し、
   日次server backupへ退避済みの世代だけを別承認で整理する。
6. raw候補、補正文、入力画像SHA、model revision、承認者・日時を監査可能に保つ。
7. 初回Sol昇格前に、現在のcanonical本文を`engine=legacy / model=pre-sol-snapshot`の合成runへ
   保存する。既存approved runは現在のcanonical本文と一致する保証がないため流用しない。
   合成runはcanonical `pages.full_text`を`ocr_page_results.published_text`へそのまま固定し、
   後からpage分類規則が変わってもrollback時に旧公開本文を再計算しない。
8. `ocr_publications`は冊子ごとにactive履歴を1件だけ持ち、切替時に旧activeをretireする。
   rollbackは履歴を削除せず、legacy runを再activateする新しいpublication eventとして記録する。
9. active切替、全page upsert、余剰page削除、FTS、`ocr_done_at`は同一transactionで行う。
   冊子の一部だけを公開しない。既存OCRのない冊子はlegacy runを作らず、初回Sol版を起点とする。
10. 本番切替前にSQLite Online Backupを取得して復元検証する。DB内の過去の診断画像由来余剰行は
    backupには保持するが、数値名PNG manifestにもとづくlegacy版・比較・rollback正本には含めない。

Solとlegacyの差分は文字編集距離、増減文字数、空本文、反復、ページ別外れ値として報告するが、
正解本文がない差分をCERまたは精度と呼ばない。CER比較は同一画像SHAのverified ground truthだけで行う。

## 5. 正解コーパスとB-35品質ゲート

正解コーパスは原画像から人手または画像照合担当が転記し、`draft` と `verified` を分ける。
OCR候補のコピー、公開本文、`corrected_text`自身を独立した機械性能の正解として扱わない。
画像SHAが一致しないentryは評価対象にしない。

### 機械ゲートの意味

| ゲート | 意味 |
|---|---|
| コーパス構成 | 最低entry数、文字数、ページ種別・layout別標本が揃っている |
| 加重CER | 通常散文全体の文字誤り率が基準以内 |
| ページ最大CER | 一部ページの大幅劣化が平均に隠れていない |
| 列欠落疑い | 削除量・削除率・bbox列間隔の複合判定で疑いが0 |
| 固有名詞 | 画像SHAへ固定した語と出現回数が完全再現される |

閾値は `scripts/maintenance/ocr_quality_policy.json` だけから読み込む。
`benchmark_ocr_ground_truth.py --fail-on-gate` は項目別実測・閾値・未達entryをJSONへ保存し、
全合格0、品質未達1を返す。機械候補とCodex補助後の運用品質は別レポートにする。

比較器は次の責務へ分割する。旧 `benchmark_ocr_ground_truth.py` はCLIと既存の動的importを
維持するfacadeであり、引数、JSON schemaとキー順、stdout、終了コードを変更しない。

| module | 責務 |
|---|---|
| `ocr_benchmark_cli.py` | 引数解析、engine dispatch、report保存、終了コード |
| `ocr_benchmark_engines.py` | corpus/QA I/O、Tesseract、yomitoku、NDLOCR adapter |
| `ocr_benchmark_columns.py` | Paddle・Suryaの列単位adapter |
| `ocr_benchmark_text.py` | NFKC等の評価正規化、CER、編集操作 |
| `ocr_benchmark_report.py` | corpus選択、ページ・group集計、stdout summary |
| `ocr_benchmark_gate.py` | policy schema検査、複合gate、列欠落、固有名詞判定 |

### B-35固有の正式holdout

B-35の完了判定には、調整に使わない3シリーズ以上・通常散文20画面以上、固有名詞10語・
50出現以上、候補品質を見ない事前選定、全画像SHA・選定manifest・QAパッケージdigest固定、
一度だけの開封を要求する。holdoutを見て規則や閾値を変えた場合は調整用へ降格し、新しい
未調整holdoutを用意する。

正式holdoutは `b35-holdout-v1` manifestを正本とする。manifestは用途、封印日時、
品質を参照しない選定入力・出力digest、policy digest、entryごとのrun・画面・series ID・
画像SHA・QA package SHA、固有名詞注釈を持ち、manifest自身のcanonical JSON SHAで封印する。
`b35-holdout-ledger-v1`台帳はmanifest SHAごとに `sealed → opened → retired_to_tuning` の
単方向eventを保持する。benchmarkは全entry、全package、policy、ground truthを先に照合し、
評価engineを起動する前に`opened`をatomic記録する。開封記録後は処理失敗時も未開封へ戻さず、
同じmanifestの再評価を既定拒否する。品質ゲートが不合格ならレポート確定時に
`retired_to_tuning`を追記し、同じholdoutを次の正式判定へ使用しない。overrideは通常benchmark経路へ設けない。

汎用corpus benchmarkはformal manifestなしでも従来どおり実行できる。正式holdoutを指定した
場合だけ、3シリーズ以上、normal prose 20画面以上、固有名詞10語・50出現以上、SHA差替え、
package欠落、開封済み再利用をfail closedで検査する。manifestと台帳の検査・更新は
ground truth、OCR QA、公開本文を変更しない。正式holdoutの機械単独品質が全policyへ合格するまで、
B-35、自動公開、Codex最終確認省略を完了扱いにしない。

正式holdoutの品質評価では、固有名詞注釈はpolicy JSONに残る汎用corpus用注釈ではなく、
封印済みmanifestの画像SHA・語集合を使用する。コーパス構成もmanifestで検証済みの3シリーズ・
normal prose 20画面を正本とし、汎用corpus向けのページ種別・layout別件数を二重適用しない。
最低entry数・総正解文字数・layout別正解文字数と、CER・ページ最大値・列欠落・固有名詞再現率の
品質閾値は引き続き封印時のpolicy JSONを使用する。これにより、候補品質と無関係な別コーパスの
注釈・構成で一度限りのholdoutを消費することを防ぐ。

### 候補支持付き固有名詞補正

文字位置合議後の固有名詞補正は、巻・ページ・正解本文を含まないシリーズ単位の語彙台帳と、
独立OCR候補の同位置一致を組み合わせる。台帳は出版社等の公式情報または人手確認済み資料から作り、
`run_id` と語だけを保持する。ページ番号、画像SHA、正解本文、期待出現位置等のページ固有情報を
含む台帳は読み込み時に拒否する。

自動置換は、合議本文と台帳語が同長で1文字だけ異なり、かつ少なくとも1つの独立OCR候補が
同じ整列位置で台帳語を完全一致させた場合に限る。台帳だけ、候補間多数決だけ、正解本文との一致だけでは
置換しない。条件を満たさない近似語は本文を変更せず `unresolved_proper_noun` としてQAへ送る。
適用した語、位置、完全一致候補、異形支持候補はレポートへ保存する。

### API表示用CERの増分集計

`GET /api/ocr/ground-truth`のCERは空白だけを除去する既存契約を維持し、NFKC等を行う
B-35 benchmark比較器とは共有しない。verified entryごとに正解本文・OCR本文の正規化後SHA、
編集距離、正解文字数を`ocr_ground_truth_pages`へ保存する。一覧はSHAが一致する保存値を合算し、
正解本文またはOCR本文が変わったentryだけを再計算する。cache欠落・不一致時は古い値を返さず、
同じ要求内で再計算・保存してから応答する。draft化では保存指標を消去する。

DB移行直後のcache未設定entryにも同じ経路を適用する。初回計算はUnicode対応のbit-parallel
Levenshteinで既存の編集距離と完全一致させ、以後はページ単位cacheを使用する。API schema、
集計順序、空文字・改行・約物の扱いは変更しない。

### 評価値の非代替性

- oracleは候補集合の到達可能性を測る診断値で、実際の選択器や公開候補の合格値ではない。
- 行認識モデルのvalidation、ONNX同値性、候補間一致、候補距離はページ品質を代替しない。
- Codex画像QA済み本文を同じground truthと比較した0%は正解化実績で、未知ページ性能ではない。
- QA・公開不変条件の検査はB-35のCERゲートで代替できず、逆も同様である。

### 公開・rollbackの障害不変条件

`approve_and_publish_run`と`activate_published_run`は、書籍metadata、canonical `pages`、
`pages_fts`、`ocr_publications`のactive切替、run状態を同一SQLite transactionで更新する。
既存canonical本文のsnapshot後、page置換後、FTS再構築後、active publicationのretire後を含む
任意のDB例外ではtransaction全体をrollbackし、実行前の本文・FTS・`ocr_done_at`・active履歴を
保持する。失敗した承認をapproved/completedとして記録せず、成功済みrunの再承認は
公開transaction先頭の`state='awaiting_qa'`条件付きno-op updateでwrite lockを取得してから処理し、
逐次・同時のどちらの再承認も拒否して二重publicationを作らない。

OCR agentのheartbeat timeout、部分ページ、worker出力不正はstaging/runを失敗または未完了の
状態へ留め、canonical本文へ到達しない。これらのDB不変条件は自動testで固定するが、backup失敗、
SQLite Online Backupの生成・復元、backup失敗時の無変更は自動testで固定する。実ディスク不足は
user namespace内の容量制限tmpfs、実process hangは親process watchdog、本番と同じfilesystem上の
世代公開はactive release自身からの復元検査で確認する。監査世代は期待したbackup rootとrun IDを
照合した場合だけ検証後に削除し、canonical DBや通常のbackup世代を自動削除しない。

## 6. Codex補助QAの委任境界

Lunaは公開状態を変えない読み取り専用補助に限定する。モデル名や速度ではなく、出力が
公開本文を確定・変更できるかで境界を決める。

| 作業 | Luna | Solまたは人 | 自動確定 |
|---|---|---|---|
| 指標・候補差分の要約、QA優先順位 | 可 | 形式不正・説明不能時 | 原データ非変更なら可 |
| OCR候補と原画像の比較、修正案 | 提案のみ | 修正案・不一致があれば必須 | 不可 |
| ページ・layout分類候補 | 説明のみ | 非通常散文・不一致時に必須 | 不可 |
| 全文転記、難layout、固有名詞・約物確定 | 不可または予備候補のみ | 必須 | 不可 |
| `corrected_text`、run承認、FTS同期、公開 | 不可 | 原画像確認後のみ | 不可 |

Luna出力は入力画像SHA、候補本文SHA、モデル、推論設定、処理時間、差分、昇格理由を持つ
監査成果物として保存し、本文DBへ直接書かない。自由文、SHA不一致、timeout、非0終了、空出力は
Solへ昇格する。モデル・prompt・画像切り出し・CLIが変われば別版として再評価する。

Sol確認の縮小は、固定コーパスと正式holdoutの全ゲート、同一画面3回の反復、100画面の
出力契約成功率99%以上を満たした版だけで検討する。解禁初期は10%を無作為監査し、重大な
欠落・意味変更・分類誤り1件で全件確認へ戻す。

### 実行版・原候補・工程時間の監査保存

新規OCR runは、実際にページを処理したworkerが生成する`runtime_manifest_json`を保存する。
manifestはschema version、OCR engine、固定model revision、Python/OS/CPU、PyTorch・YomiToku等の
package version、CUDA/MPS/device、worker・wrapper・pipeline source SHA、Git commitとdirty状態を持つ。
model/mmprojのローカル資材が指定された場合はファイルSHAも保存する。同じrunの途中でmanifestが
変化した場合はページ保存を拒否し、異なる実行環境の結果を1 runへ混在させない。既存runは
空manifestのまま読み取り可能とするが、新規runの`model`が空または`unversioned`なら開始しない。

ページ結果は採用後の`full_text`/`raw_output`とは別に、`primary_text`、`external_text`、
`primary_raw_output`、`external_raw_output`を不変の原候補として保存する。
`candidate_manifest_json`には候補ごとのstate、文字数、block数、quality flag、本文SHA、raw出力SHAを
記録する。保存時に本文・raw出力からSHAを再計算し、不一致、存在しない候補の採用、採用本文と
原候補の不一致を拒否する。候補選択後も非採用候補を上書き・削除しない。

工程時間は次の粒度で保存し、OS/GPU比較では同じ項目だけを比較する。

- run: `started_at`、`ocr_finished_at`、`qa_started_at`、`qa_finished_at`と、worker/server初期化時間を
  `timing_json`へ保存する。
- page: 画像読込、primary OCR、external OCR、候補選択、総処理時間を
  `processing_timing_json`へミリ秒で保存する。
- QA: 画面表示開始時刻、保存までのactive確認時間、Codex補正文の編集時間をページへ保存する。
  値は非負整数とし、ブラウザ再読込等で開始時刻が失われた場合は推測値を作らずnullを許す。
- 公開可能になるまでのwall clockはrunの`started_at`から`qa_finished_at`までとし、OCR計算時間、
  QA待ち時間、人手確認時間を混ぜた単一の速度値として扱わない。

## 7. `YomitokuEngine`

`YomitokuEngine`は通常のPyTorch経路で実行し、workerから渡されたデバイスを
`OCR(device=...)`へ明示する。Macではまず通常モードを使用する。`--lite`は文字検出器を
ONNX Runtimeへ切り替える経路があり、MPSで全体が実行されるとは限らないため、MPS性能評価の
初期条件には含めない。MPS非対応演算子をCPUへフォールバックさせる場合は、実行ログに残し、
ページ処理時間の比較でMPS実行と混同しない。

通常の縦書き小説ページでは `paragraphs` / `lines` ではなく `words` が返り、本文列は
幅38〜48pxの長いword、ルビは幅18〜33pxの短いwordになる実測がある。

### ルビ除去

word幅ヒストグラムの谷を自動検出し、谷がない場合はmedian比へfallbackする。
本文とルビの幅分布が近い書籍では誤除去の可能性があるため、他書籍での回帰を残す。

### 断片結合

長い本文列より短い断片が多い場合だけ、X位置のbinへ分けて断片を結合する。
通常ページで無条件に結合しない。

### 正規化

ASCIIピリオド・中黒の連続を三点リーダーへ、連続ハイフンをダッシュへ正規化する。
評価用正規化と公開本文の校正を混同せず、意味や括弧種別を自動変更しない。

## 8. 既知の制限

- 低confidence列、イタリック、心内語は認識精度が低い。
- ルビと本文の幅差が小さい書籍、ルビなしページの除去精度は未検証である。
- 両候補が同じ列・固有名詞を誤る場合、候補比較だけでは検出できない。
- B-35正式holdoutの封印・一度だけ開封は機械強制するが、新しい未調整holdoutでの
  機械単独総合合格は未達である。
- Google Document AI Enterprise OCR `pretrained-ocr-v2.1.1-2025-01-31`は、2026-08-22の
  開封済み30画面pilotでルビ混入と縦列読順崩壊を確認したため、正規本文の生成元にしない。
  利用する場合は外部候補としてstagingに隔離し、列coverage・約物・ルビを原画像で独立確認する。
  pilot差分率はverified ground truthに対するCERではなく、自動公開条件へ転用しない。
- Unlimited-OCR BF16は、MLX-VLM 0.6.15の固定5枚で全ページが生成反復し、総合CER
  690.7200%、ページ最大1,069.3122%だったため本番候補にしない。最大RSS約7.42GB、swap 0なので
  64GB unified memory不足による不合格とは扱わない。反復除去後の本文を採用値へ転用しない。

GPUセットアップは [GPU環境セットアップ](../../環境構築/GPU環境セットアップ.md)、
Mac補助評価は [Mac OCR補助確認設計](Mac_OCR補助確認設計.md)、削除済みSearchablePDF設計は
[凍結記録](../../../archive/OCR_旧SearchablePDF設計.md) を参照する。
