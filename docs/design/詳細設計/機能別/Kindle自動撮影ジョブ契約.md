# Kindle 自動撮影ジョブ契約

> status: living | last-verified: 2026-09-05

<!-- contract-owner: kindle-capture -->

Linux backend、Windows capture agent、シリーズ実行scriptをまたぐjob契約の正本とする。
購入データ・ASIN紐付け・画面表示は[Kindle購入カタログ設計](Kindle購入カタログ設計.md)、
利用者の前提・操作・受入条件は[Kindle自動撮影取込 要件](../../要件定義/Kindle自動撮影取込_要件.md)を参照する。
Windows UI Automation、撮影矩形、ページ送り、package生成の内部設計は
[kindle-pdf詳細設計](../../../../kindle-pdf/docs/detailed_design.md)が所有する。

<a id="kindle-capture-contract"></a>
## 1. job状態と所有権

カタログの`book_type`は入力の初期値であり、撮影方式・登録先の正本ではない。
開始確認で利用者が確定した`source`をjobへ保存し、撮影・登録はそのsourceに従う。

画面から作成した `capture_jobs` は Linux DB が正本となる。Windows エージェントは 1 件ずつ claim し、claim 応答の `identity`（ASIN、正式・正規化タイトル、著者、シリーズ、巻）を使って対象書籍を照合する。

状態遷移は `queued → claimed → locating_book → downloading（必要時）→ positioning → capturing → awaiting_files → succeeded` とし、各実行状態から `failed` へ遷移できる。既存 Windows エージェントとの段階導入互換性のため、`claimed → waiting_user → capturing` も読み書き可能な旧経路として維持する。

claim と状態更新時に `heartbeat_at` を更新し、agent は長時間工程中に heartbeat API を呼ぶ。次回 claim 時に、`KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC`（既定 300 秒）を超えた active job を `agent_heartbeat_timeout` で `failed` へ回収してから次の queued job を選ぶ。同一 agent が期限内に再 claim した場合は、現在の active job を返す。

成果物は Samba 上の論理専用受信箱へ `.partial` 名で送信し、完了後に
`.ready` へ rename する。既存環境では
`pic2pdf-input/.kindle-capture-inbox` を利用し、同人誌監視の対象から除外する。
Linux は `.ready` だけを検証し、安全な相対パス、許可拡張子、件数・容量上限に加えて、
version 2 manifest のjob identity、SHA-256、画像復号・寸法・連番を実ファイルから再計算し、
撮影完了証跡、撮影前カナリア、登録前画像QAは形式と内部整合を検証してから正式配置する。
終端観測フレームとカナリア画像はpackageに含めないため、意味判定はWindows側で行う。
Windows側の合否だけを信用せず、証跡欠落・不一致・blocking候補ありの場合は正式画像領域とDBを更新しない。登録は `awaiting_files` かつclaimしたagent所有のjobだけに許可し、正式画像の置換と `succeeded` 更新を同じ完了処理で確定する。失敗時は既存の正式画像とDBを保持する。

現行Windows agentは、起動済みKindleへの接続、ASINの一意照合、必要時のdownload、位置決め、撮影、転送、登録を1冊ずつ直列実行する。旧 `waiting_user` は後方互換契約として読み書き可能に残すが、現行agentは使用しない。内部の入力方式やUI control識別を横断契約に含めない。

撮影後・共有前に件数を検証し、`expected_screens`指定時は指定件数、未指定時は
小説50画面・漫画10画面を最低件数とする。未満なら`capture_incomplete`として
一時成果物を破棄し、既存の正式画像を置換しない。

## 2. 撮影品質とmanifest

正式撮影前には同じsource・ページ送り方向・撮影矩形で2画面のカナリアを実行する。
撮影後は最大32ページを等間隔に標本化し、内容の異なる複数ページの外周で同一座標の
構造化タイルが反復する画面オーバーレイを検査する。隣接2タイル以上が標本の50%以上で
反復する高信頼候補は`capture_incomplete`として拒否し、20%以上50%未満は
`repeated_screen_overlay_candidate` warningとしてversion 2 manifestへ残す。
完全重複、低容量、白紙・疎な画面、隣接dHash近似重複、小説上下端の内容密度は
誤検知校正中のためwarningに留め、自動削除や登録拒否には使用しない。

等間隔標本から外れる短時間通知は、全ページを3画面だけ保持するrolling windowで検査する。
各画面hashが異なり、幅1024へ正規化した右下隅の64pxタイル2枚が全3画面で
輝度分散8以上、Canny edge率1.5%以上、画素MAD最大6以下を同時に満たした場合だけ
`transient_bottom_right_overlay_candidate` warningとする。連続windowは同じ候補へ集約し、
対象ページ、正規化bounds、最大MADを証跡へ残す。これは登録拒否へ使わず、単一・2画面、
右下以外、通知位置が動くUIは検出対象外とする。

未調整holdoutの数値は[追加実測履歴（凍結）](../../../archive/検証/Kindle購入カタログ_追加実測履歴_2026-09-05.md)へ分離した。
完全重複以外のraw warningは、確定した実陽性の人手labelなしにblockingへ昇格しない。実障害は
修正前画像と確定labelを別の回帰コーパスへ追加して再評価する。

## 3. 画像品質の監査世代

warning証跡は次の2テーブルへ保存する。

- `capture_quality_audits`: 成功job、source、ASIN、正式`book_id`、QA / warning policy version、
  quality証跡SHA-256、作成日時、旧世代化日時と後継jobを持つ監査世代。warning 0件でも1行を作る。
- `capture_quality_warnings`: 監査世代内の同一codeを1行へ集約し、finding件数、重複除去済みfiles、
  元finding JSON、`is_read`、`read_at`を持つ。登録時は常に未確認で開始する。

ready package検証では`kindle-image-warning-v1`の既知code、`severity=warning`、連番PNGへの参照、
metrics objectを再検証する。段階更新中の旧agent用v1組と、短時間右下通知を含む
`kindle-image-warning-v2` / `kindle-repeated-overlay-v2`組を受け付け、新warning codeはv2だけに
許可する。v2 overlay証跡は全ページ走査数と短時間候補数に加え、3枚以上の連続PNG、
正規化右下bounds、隣接tile数、MAD上限も検証する。正式画像公開後の
`succeeded`更新と同じSQLite transactionで監査世代と
warningを挿入し、失敗時はDBと正式画像を従来どおりrollbackする。同じsource・`book_id`の再撮影が
成功した場合は旧監査世代を削除せずsupersedeし、新世代だけを通常APIへ返す。新世代はwarning 0件でも
作るため、旧画像の候補が現画像へ残らない。将来の再監査はpolicy versionまたはquality証跡digestが異なる
新世代として保存し、旧世代をsupersedeする。新世代の既読状態は引き継がない。

UIは登録成功と分離した「要確認候補」とし、書籍・code単位で件数をまとめ、対象ページを既存readerで
開けるようにする。失敗toast、自動削除、OCR開始の自動停止には流用せず、章扉・表紙・挿絵・奥付等の
正常例を含む旨を明示する。

<a id="kindle-series-runner"></a>
<a id="4-シリーズ直列実行"></a>
## 4. シリーズ直列実行

`scripts/capture_kindle_series.py` は購入カタログAPIだけを正本として、対象を巻順に並べ、
常に1冊分のjobだけを作成する。APIもjob作成transaction内で全source・全ASINの未完了jobを
最大1件に制限する。jobが `succeeded` になり、対象ASINの `capture_state=captured` を
再取得できた場合だけ次へ進む。`failed`、監視timeout、API不整合、割り込み、登録状態不一致では
後続jobを作成しない。監視側の停止は実行中jobを暗黙にcancelしない。

`capture_kindle_series.py`は旧CLI・import pathを保つfacadeとし、実装責務を次へ分ける。

- `kindle_series_inventory.py`: catalog itemの絞り込み、source・巻数決定、並び順。
- `kindle_series_session.py`: manifest digest、session state、atomic永続化、breaker。
- `kindle_series_screen_count.py`: 成功実績の選別、source別中央値、warning contract。
- `kindle_series_orchestrator.py`: 1冊ずつのjob作成・監視・限定復旧・登録確認。
- `kindle_series_http.py`: 購入カタログAPI transport。
- `kindle_series_cli.py`: 引数検証、依存組み立て、exit code変換。

orchestratorはHTTP実装へ依存せず`CaptureApi` protocolだけを参照する。session breakerは
job作成前に検査し、inventory・CLI・HTTP adapterからKindle UIを直接操作しない。

既定はdry-runで、実行には `--apply` とsession stateを要求する。state schema v2は対象manifest digest、
完了ASIN、ASIN別撮影画面数、品質warning、復旧回数、停止理由をatomic置換JSONへ保存し、既存stateは `--resume-session` を
明示した場合だけ、同じmanifestかつrunning状態で再開する。resume時は完了ASINと
画面数の1対1対応、warningのASIN・source・撮影数と観測値の一致を再検査する。必須fieldがない
schema v1や不整合stateは暗黙移行せずresumeを拒否し、実行状況を確認してから新規stateを作る。

画面数外れ値policy `kindle-series-screen-count-v1` は、対象inventory内で最新の
`succeeded` jobが確認できる登録済みASINと、実行中sessionの完了ASINをreferenceとする。
`comic` / `novel` は混ぜず、同sourceの正の画面数が3冊以上ある場合に限り、新しい
画面数が中央値の0.5倍未満または2倍超なら
`series_screen_count_outlier_candidate` warningを生成する。warningにはpolicy version、
ASIN、source、撮影数、reference冊数・最小・中央値・最大、比率を固定する。長編・短編や
特典巻の正常差を考慮し、初期policyは登録取消、session breaker、後続job停止に使わない。
撮影成功応答の画面数が正の整数でない場合はwarningとして集計せず、API不整合としてfail closedする。

Kindle processの自動復旧は `--recover-kindle-crash` 指定時だけ許可する。撮影開始前・撮影枚数0・
process消失・許可error codeを同時に満たし、再起動後に同一ASINを一意照合でき、他の未完了jobが
ない場合だけ、新しいjobを最大1回作る。processが残るUI不調、download・位置決め・撮影・転送・
登録失敗では復旧せずfail closedとする。現行runnerはerror種別にかかわらず1冊目の失敗で停止し、
連続download失敗を跨いだ自動継続は行わない。

## 5. backendの登録・補償境界

- **責務分割**: `capture_jobs.py`は互換facade、
  `capture_job_repository.py`は状態transaction、`capture_package_validator.py`は
  version 2 manifest・パス・サイズ・hash・画像復号・寸法の再計算、撮影完了証跡の内部整合、
  旧warning / overlay policy v1組と短時間右下通知を含むv2組の互換検証、
  `capture_registration.py`は完了workflowを調停する。
  `capture_registration_repository.py`は完了対象jobの取得と所有・状態確認、
  条件付き`awaiting_files → succeeded`更新を担当する。
  `capture_publication.py`はstaging copy、既存target退避、正式publish、meta更新、
  package archiveと逆順補償を担当し、catalog DBを直接参照しない。
- **作成排他**: `capture_job_repository.create()` は `BEGIN IMMEDIATE` 内で
  全source・全ASINの未完了jobが0件であることを確認してからINSERTする。
  runner側の事前確認とは独立した最終防衛線とする。
- **claim**: `BEGIN IMMEDIATE` と条件付き更新で 1 件だけ取得し、カタログ DB から ASIN、正式・正規化タイトル、著者、シリーズ、巻を `identity` に合成する。
- **時刻**: `started_at` は `capturing` 開始時、`completed_at` は `failed` / `succeeded` 確定時だけ設定する。
- **エラー**: agent 所有権と許可状態遷移を transaction 内で検証し、異なる agent、terminal job、逆向き遷移を拒否する。
- **補償**: 正式画像配置、`meta2.db`更新、packageの`processed/`移動、
  capture job成功更新の順に実行する。途中で失敗した場合は画像とmetaを戻し、
  packageを`.ready`へ復元してjobを`awaiting_files`のまま維持する。
  ready検証、staging copy、既存target退避、target publish、meta更新、package archive、
  job更新直前を障害注入境界とし、条件付きjob更新が1行以外の場合も同じ補償を行う。
- **再撮影置換**: 正式画像が既にある場合は、metaの同一`book_id`が同じASINを
  保持するときだけ置換を許可する。旧画像は
  `PIC2PDF_DATA_DIR/.capture-replacement-backup/<時刻>_<job短縮ID>/`へ世代退避し、
  新画像・meta・package・job更新の失敗時は旧画像を同じ正式パスへ戻す。
  同名でもASINが異なる、または既存metaでASINを確認できない場合は置換しない。


## 6. agent設定と再開境界

| 設定 | 意味 |
|---|---|
| `KINDLE_CAPTURE_INBOX_DIR` | `.partial`から`.ready`へ成果物を公開する専用受信箱 |
| `KINDLE_CAPTURE_AGENT_TOKEN` | agent APIの共有トークン。未設定時はAPIを503で無効化する |
| `KINDLE_CAPTURE_HEARTBEAT_TIMEOUT_SEC` | active jobの期限。既定300秒、次回claim時に回収する |

撮影中はagentだけがKindleを操作する。途中状態を暗黙に再開せず、`awaiting_files`の
完了APIだけは冪等再試行できる。それ以前のjobは失敗として新しいjobの作成を要求する。
UI操作・再接続の実装は[kindle-pdf詳細設計](../../../../kindle-pdf/docs/detailed_design.md)を参照する。
