# 小説 RAG 構築パイプライン設計

> status: living | last-verified: 2026-08-02

novel タブの本文を検索・QA 可能にするための **DB 構築パイプライン**（OCR 取込 → チャンク分割 → embedding → 文脈生成 → キャラ抽出 → 書籍サマリ）の現在形設計。検索・QA 側は [検索QA設計](小説RAG_検索QA設計.md) を参照。

**スキーマ・環境変数・ディレクトリレイアウト・API 一覧・LLM backend / port は [データ設計](小説RAG_データ.md) が正本**。本書は重複記載せず、各ステップの入出力・skip 条件・統合フローに集中する。設計の経緯（三段改善史・チャンク実験・PDF 経路撤去）は [設計過程（凍結）](../../../archive/小説RAG_設計過程.md)、実機ベンチ・モデル選定は [技術知見](../../../log/技術知見/小説RAG_技術知見.md)。

すべて `backend/services/novel_db/` 配下。CLI は `backend/scripts/`。

---

## 1. パイプライン全体像

書籍 1 冊は「OCR → チャンク/embedding → サマリ+キャラ辞典 → チャンク文脈 →（キャラ関係）」の順で構築される。各ステップは**独立したジョブ**として実行でき、途中失敗からの再開・部分再構築が効く。UI の各ボタン / CLI が `rebuild_jobs` にジョブを投入し、単一 worker が直列実行する（§7）。

```
images/*.png ──[ocr]──────────► pages.full_text (+ pages_fts)         … builder.ocr_book
      │                              │
      │                              ▼
      │           [rebuild]  chunks + LanceDB chunks(embedding)        … builder.rebuild_from_pages
      │                              │
      │        [full_build] ────────┤ books.summary + books.catalog_summary + book_characters
      │                              │                         … full_builder（事実抽出→個別執筆→校正）
      │                              │
      │  [generate_contexts] ───────┤ chunks.contextual_text + 再embed  … full_builder.build_book_contexts
      │                              │
      └──[extract_characters CLI]──► pages.main_characters              … character_extractor
                                     │
             [generate_relations] ──► character_relations (C-12)        … relation_extractor
```

各ジョブが対象とする「未処理書籍」の判定条件は §7 の `_resolve_targets` を参照。

---

## 2. ステップ 1: OCR 取込（`job_worker` / `ocr_staging` / `extractor` / `ocr_worker`）

`images/{書籍名}/NNN.png` を Surya OCR 2 でページ単位に処理し、
品質結果を staging へ保存する。処理完了後は `awaiting_qa` とし、
必須ページのQAとrun承認が完了した1冊分だけを `pages` テーブルへ書き込む。
yomitoku は独立照合と `OCR_ENGINE=yomitoku` の比較・後方互換用として残す。

- **subprocess 分離**: `extractor.iter_ocr_pages` が対象ページmanifestを一時JSONで渡し、`ocr_worker.py` をOCR venvのPythonで1回起動する。workerは1ページごとにJSON Linesを返し、stderrはbackendログへ流す。
- **Surya推論**: Windows上のCUDA対応 `llama-server` へOpenAI互換APIで接続する。到達不能時は設定済みの実行ファイル・model・mmprojからworkerが所有サーバーを1回だけ起動する。
- **worker内部**: PNGをバイト列として読み、SHA-256を計算してPillowで復号する。Suryaのraw HTML/bboxを解析し、不合格時だけ入力条件を変えて最大3候補を比較する。`OCR_ENGINE=yomitoku` の後方互換経路だけは OpenCV で復号する。
- **チェックポイント**: `ocr_staging` が `ocr_runs` / `ocr_page_results` にページ単位で保存する。再実行時は画像SHAが同じ `passed` ページをスキップする。
- **二段階保存**: 全ページの結果を staging へ保存して `awaiting_qa` に進める。この時点では公開済み本文を変更しない。必須ページの承認・補正と run 承認後だけ `_store_ocr_pages` と同等の更新を1トランザクションで行い、`books.ocr_done_at` とFTSを同期する。
- **直接呼出し互換経路**: `builder.ocr_book` は旧CLI向けに残る直接保存APIで、チェックポイント・二段階確定を行わない。管理画面とjob queueは必ず上記のステージング経路を使用する。
- **PDF モード（後方互換）**: `extractor.extract_pages(pdf)` は PyMuPDF `get_text("blocks")` で縦書きブロックを取得しブロック内改行を除去して連結する。旧 Searchable PDF 由来の書籍向けで、現行の取込は画像 OCR 経路が主。

## 3. ステップ 2: チャンク分割 + embedding（`builder.rebuild_from_pages`）

`pages.full_text` を入力に `chunks`（SQLite）と LanceDB `chunks` テーブルを再構築する。**`pages` は一切変更しない**（OCR 済みの本文を前提）。

- **チャンク分割（`chunker.chunk_page`）**: 全文 ≤ 800 字なら 1 チャンク。超える場合は末尾 100 字以内の句点境界（`。」!?`）優先で切り、50 字オーバーラップ。`char_count < 30` のページ（章扉・ヘッダのみ）はスキップ。
- **embedding（`embedder.embed_batch`）**: Ollama `/api/embed`（httpx）で bge-m3（1024 次元）。builder は 16 件バッチ。`options.num_gpu` に `NOVEL_DB_EMBED_NUM_GPU`（既定 CPU）を渡し llama-server に VRAM を譲る。次元・件数不一致は `EmbeddingError`。
- **保存**: 既存 chunks を LanceDB（`chunk_id IN (...)`）と SQLite の両方から削除 → `chunk_page` の結果を `chunks` に INSERT、embedding を LanceDB に `add`（本文・page_no・char_count・page_count を同梱）。完了時に `books.indexed_at` を更新。progress_callback で `embedding done/total` を通知。
- **ページ単位再構築（`page_index_builder.rebuild_page_from_pages`）**:
  画像照合後に1ページだけ本文を補正した場合、
  対象ページのSQLite `chunks`とLanceDBベクトルだけを再生成する。他ページのchunk IDと
  embeddingは保持する。FTS5はexternal-contentテーブルから古い語を確実に除くため
  `pages_fts`全体を`rebuild`するが、embedding計算は対象ページに限定する。運用時は
  `build_novel_db.py --book "<書籍名>" --page <画面番号>`から実行する。2026-07-28の
  本番6ページ再構築では、全件で対象外ページのchunk件数・ID合計が不変で、
  書籍全体のchunk総数も再構築前後で一致した。
- **入力の責務**: ページ単位再構築は`pages.full_text`、`char_count`、
  `index_eligible`を変更しない。OCR runの承認・画像照合補正を先に完了し、公開済み
  `pages`を正本として索引だけを同期する。`page_no`は紙面ページではなくキャプチャ画面番号。
- **ページ単位再構築の失敗安全性**: 新本文のチャンク分割とembeddingを変更前に完了し、
  旧LanceDB行を退避してから更新する。更新開始時に`books.indexed_at=NULL`を確定して
  不完全状態を可視化する。SQLiteまたはLanceDB更新に失敗した場合はSQLiteをrollbackし、
  追加したLanceDB行を削除して退避行を復元する。復元の成否にかかわらず
  `indexed_at`はNULLのままとし、通常の書籍単位`rebuild_from_pages`を復旧手段とする。
  更新前から対象chunk IDのSQLite件数とLanceDB件数が一致しない場合は変更せず中止し、
  ページ単位処理で不整合を上書きせず書籍単位再構築へフォールバックする。
- **クロスページ実験 `chunk_book`**: 全ページ連結 + bisect で page_id 解決する実験実装（1200 字 / overlap 120）。本番未採用、`eval_chunk_strategy.py` 用に残置（判断経緯は [設計過程](../../../archive/小説RAG_設計過程.md)）。

## 4. ステップ 3: 書籍サマリ + キャラクター辞典（`full_builder` + `summarizer`）

`full_builder.build_book_full()`は、本文から完成文を一度に生成せず、**事実抽出 → 要約・人物の個別執筆 → 編集校正 → 品質ゲート → 一括確定**の順で処理する。処理時間より、本文根拠の維持、後半の変化の取りこぼし防止、読みやすい日本語を優先する。

> **段階移行先（未実装）**: B-36の比較結果を受け、OCR後の公開成果物は
> [Sol主生成・選択的独立評価設計](小説RAG_Sol生成・評価設計.md)へ段階移行する。
> 1冊1回のSol主生成、ローカル決定的ゲート、高リスク主張だけの別Solセッション評価、
> 人手承認後の一括確定を採用する。固定パイロット合格までは本節のQwen経路を既定として維持し、
> Sol候補を公開DBへ書き込まない。

LLM呼び出しごとのtemperature・出力長・context長は用途別定数として各機能側に残す。一方、Ollama互換options辞書のキー組み立ては`llm_options.make_llm_options()`に集約し、キー名の表記揺れや型なし辞書の複製を避ける。

- **Step 1**: `rebuild_from_pages`（§3、常実行）。
- **Step 2a 事実抽出**: `summarizer`が採用本文を`[page N]`付きでQwenへ渡し、
  まず出来事の発端・行動・理由・結果・関係変化を`[BOOK_FACTS]`として抽出する。
  続けて、この書籍事実だけを入力に人物名と立場・行動・変化を
  `[CHARACTER_FACT:人物名]`へ再編する。書籍事実と人物事実を一度に生成すると、
  長編では書籍事実だけで出力上限へ達し人物マーカーが欠落するため、2回に分離する。
  本文は長文コンテキスト中央の取りこぼしを抑えるため、入力上限まで詰めず、
  約3万文字を上限としてページ境界で時系列ブロックへ分ける。各ブロックの
  書籍事実・人物事実を後段へすべて渡し、事実抽出では完成した紹介文を書かせない。
- **公開版人物名ヒント**: 再生成時は同じ巻の`book_characters.name`だけを公開版人物名台帳として
  事実抽出へ渡す。台帳名は本文に実際に登場するときだけ正規名として優先し、公開版の人物説明や
  他巻・後続巻の知識は入力しない。台帳内容を事実とみなした補完とネタバレ混入を防ぎながら、
  既存人物の抽出漏れと`皓茉莉花`/`茉莉花`のような見出し揺れを抑える。
- **事実チェックポイント**: 各ブロックの抽出完了後、ページ範囲、本文SHA-256、
  使用モデル、抽出スキーマ版、生の書籍・人物事実、ページ根拠を正規化した事実レコードを
  `fact_extraction_blocks`へUPSERTして独立commitする。本文ハッシュには公開版人物名台帳も
  prompt contextとして含める。同じブロック番号でも本文、人物名台帳、モデル、抽出スキーマ版の
  いずれかが異なる場合は再抽出する。後段の執筆・校正が失敗しても
  一致する完成ブロックは次回再利用する。ブロック数が減った場合は余剰行を削除する。
- **ページ根拠検査**: 書籍事実と人物事実の全箇条書きに1件以上の`[page N]`を必須とし、
  `[page 18, page 20]`のように同じ角括弧へ複数根拠をまとめた表記も受理する。
  記載された全ページを個別に抽出し、1件でも入力ブロック内に存在しない出力は保存せず失敗とする。
  公開版人物名ヒントが当該ブロックに登場せず、モデルが人物見出しへ`該当事実なし`・`言及なし`・
  `登場なし`を明示した場合は、根拠のない事実として扱わず、その空の人物候補だけを除外する。
- **Step 2b 詳細あらすじ執筆**: `books.summary`用の詳細あらすじは事実表だけから独立生成する。中心人物、因果、時系列、対立、転機、結果、関係変化、巻の意味を自然な複数段落へ編集する。
- **Step 2c 一覧向け短縮要約**: 詳細あらすじの双方向根拠検査合格後、事実表と合格済み詳細版から400〜700文字の`books.catalog_summary`を別に生成・校正する。中心人物、発端、中心課題、主要な対立または転機、結果、重要な関係変化を残し、詳細版を単純切り詰めしない。
- **Step 2d 人物別執筆**: 事実表の人物名を`character_names.normalize_character_entries`で正規化する。
  同じ巻の公開版人物名と完全一致する表記を優先し、公開版正規名から一意に導ける短縮形、または
  `A（B）`・`AことB`のように事実メモ内で明示された別名だけを公開版正規名へ統合する。
  文字列の部分一致だけで別人を統合しない。本文に根拠がある人物を登場ページ数順で最大20名選び、
  人物ごとに関連ページと事実メモを渡して、他人物と混在させず個別に説明を生成する。
- **全巻を覆う人物入力**: 関連本文が入力上限を超える場合、先頭からの単純切り捨ては禁止する。初出と最終出現を必ず含め、全登場範囲を時間帯に分けて各区間から情報量の多いページを選び、その後に残容量を埋める。終盤の選択や関係変化を入力から落とさない。
- **編集校正**: 詳細あらすじ、短縮要約、人物説明を用途別の編集プロンプトへ渡し、主語不明、因果の飛躍、曖昧な代名詞、電文調、重複、名詞句の連結を修正する。校正は事実表にない設定や心理を追加してはならない。校正版が品質ゲートを通らない場合は、合格している初稿へ戻す。
- **Step 2e 双方向RAG検証**: 校正後の詳細あらすじを句点単位の主張へ分解する。各主張について、
  FTS5 + bge-m3 + RRFの書籍内ハイブリッド検索上位ページと、構造化事実表から文字bigramが
  近い事実の根拠ページを候補にする。要約自体が構造化事実表から執筆されるため、候補順は
  事実表の直接根拠を先、ハイブリッド検索による補完を後とし、各主張の上位2候補は全体の
  文字数制限より先に証拠本文へ採用する。段落や出来事がページ境界を跨ぐ場合に備え、直接候補の
  優先順を維持したまま、本文が存在する前後1ページも補助候補へ加える。候補ページを重複排除し、
  最大64ページ・90,000文字の証拠本文と、全主張、書籍事実を
  1回の独立検証プロンプトへ渡す。各主張を`supported / contradicted / unsupported`で判定し、
  逆方向に主要な発端・対立・転機・結果・関係変化が要約から欠落していないかも検査する。
  全主張が`supported`かつ重要事実の欠落なしの場合だけ合格とする。
  短縮要約は、書かれた全主張に同じ根拠検査を行う一方、用途上意図した詳細の省略を
  coverage不合格にはしない。監査ログの`content_type`で`detailed / catalog`を区別する。
- **引用可能ページの境界**: 主張別候補は検索上の優先順位として検証モデルへ示す。
  同じ検証プロンプトへ本文を全文提示した別主張の候補ページも、当該主張を直接裏付ける場合は
  引用を許可する。構造化事実表にページ番号だけ存在しても、本文を検証プロンプトへ提示して
  いないページは引用不可とする。検索候補の主張への割当誤差と、本文未提示ページの引用を区別する。
- **検証モデル配線**: 既定の`NOVEL_DB_VERIFIER_BACKEND=qwen`は執筆用Qwenサーバーを
  検証時に直列再利用し、64GB Macへ別の大規模モデルを常駐させない。
  比較時は`ollama`または独立`llama_server`と`NOVEL_DB_VERIFIER_MODEL`を指定し、
  Gemma等の別系統モデルへ切り替えられる。独立モデルを使う場合も執筆と検証を同時実行せず、
  実測メモリとswapが許容範囲であることを運用条件とする。
- **Gemma4の位置付け**: Gemma系の主比較対象は`gemma4:31b`とし、12Bの結果は予備比較として
  保持する。10巻の固定誤り1件では、Qwen3.6 35B-A3Bが仁耀の最終行動を「牢へ戻る」と誤判定した
  一方、Gemma4 31Bは「最長10年間逃げ続ける」を選び、誤要約を`contradicted`、矛盾を含む事実メモを
  `partially_contradicted`にできた。12Bが事実メモ内部矛盾を見落とした点も31Bでは改善した。
  ただし31BにもJSONコードフェンス混入と日本語校正時の軽い意味変更が残るため、既定検証モデルや
  校正の自動確定役へは昇格しない。Qwen執筆後にモデルをアンロードし、31Bを独立した第二検証役として
  直列実行する主候補とする。64GB Macでの固定試験は実行時20GB・100% GPU・16,384 context、
  事実監査と校正の合計84秒だった。採用判断は、正解を固定した10〜20件以上で事実判定、出力契約、
  意味保存、所要時間を比較して行う。
- **Gemma4の役割別比較結果**: 10巻の隔離試験では、31Bによる詳細あらすじは889字で28分31秒、
  一覧用短縮要約は490字で22分30秒を要した。日本語は自然でQwenの「牢へ戻る」という誤断定を
  避けたが、正しい最終合意を明記せず、主体・時制の意味変更も残った。事実抽出第1ブロックの
  人物事実、茉莉花1名の人物辞典初稿、64ページ一括の巻全体検証は、それぞれ20分の評価上限内に
  完了しなかった。このためGemma4 31Bを事実抽出・執筆・人物生成の代替にはせず、Qwenと機械ゲートを
  主系統として維持する。Gemmaには、否定、最終行動、時系列、主語、不可逆な状態変化などの
  高リスク主張だけを小さな本文窓と共に渡し、直列の独立検証へ限定する。巻全文の一括検証は行わず、
  主張単位または少数主張の束へ分割する。一覧用短縮要約の第二案生成は任意の夜間比較に留める。
- **Codex LunaのB-36比較結果**: `gpt-5.6-luna`で、10巻の隔離スナップショットから同じOCR本文、
  8〜84ページの77ページ、4ブロック境界、対象人物10名を使って、Qwenが担当した事実抽出・詳細版・
  短縮版・人物辞典・事実確認を比較した。74〜75ページの固定誤りでは、途中の「牢に戻る」と
  75ページの「最長10年間逃げ続ける」への最終同意を分離でき、最終行動、事実メモの部分矛盾、誤要約の
  矛盾判定をすべて正しく返したため、固定ケースは合格とした。巻全体でも主要な発端・転機・結果・
  関係変化と最終状態を保持したが、詳細版・短縮版の「珀陽に拘束」は、作戦主体の珀陽と物理的実行者の
  天河を単純化している。事実表には推測と事実の境界確認も残るため、巻全体は条件付き合格・公開不可とする。
  出力は読み取り専用の隔離比較だけで、公開DB、OCR本文、ページ索引、画像へ書き込まない。役割別の推論時間を
  計測しておらず、Qwenの保存済み成果物にも再現可能な役割別時間がないため、速度比較の結論は出さない。
  Lunaを本番系へ昇格する前に、主体ラベル、事実・推測ラベル、巻全体の独立検証、役割別タイマーを追加する。
- **Codex Luna構造化再計測の採否**: 上記固定ケースを判定定義付きで再実行すると37.377秒で合格したが、巻全体の
  事実抽出は許可外`actor_role`、詳細・短縮版はSchema外ラベルまたは主体誤り、人物辞典は正規名・人物同定の課題、
  根拠監査は主体誤り・欠落・監査応答Schema違反を返した。したがってfail closedを適用し、LunaをQwenの代替生成、
  補助初稿、または自動公開役へ昇格しない。採用候補は固定ケースと、主体・否定・最終状態・不可逆状態を少数主張に
  分割した手動確認付き補助QAに限定する。Lunaの工程別時間は保存したが、Qwen側に同一形式の時間記録がないため、
  速度比較は未確定である。
- **Compact厳密化Lunaブロック抽出の検証条件**: Lunaへ巻全文や下流生成を一括委任せず、既存Qwenと同じ
  8〜27、28〜49、50〜69、70〜84ページの4ブロックを、それぞれ新規・独立コンテキストで事実抽出させる。
  各実行前に、目的、入力SHA-256、許可Schema、正規名台帳、許可された主体役割、途中状態と最終状態の区別、
  完了条件、禁止事項を状態契約JSONへ外部保存する。Compactまたはセッション終了後の継続は会話要約を正本にせず、
  状態契約、ブロック入力、機械検証済み出力だけから再開する。各ブロックは許可外ページ、正規名、列挙値、
  根拠なし事実、Schema違反をfail closedとし、合格した事実だけを統合する。詳細あらすじ・一覧用短縮要約・
  人物辞典の主生成と編集は既存Qwenを直列利用し、Lunaへ戻して自己監査させない。比較では公開DBを変更せず、
  Luna抽出の初回契約成功率、主体・時系列・最終状態、Qwen完成文の網羅性と根拠性、工程時間を保存する。
- **Compact厳密化Luna抽出とQwen主生成の検証結果**: 2026-08-02の10巻隔離試験では、LunaへOCRを
  ブロック単位で直接渡し、状態契約、厳格JSON Schema、先頭・末尾ページ網羅、固定高リスク判定を機械検証した。
  ブロック1は初回末尾欠落後の有界再試行、ブロック2・3は初回で合格したが、ブロック4は最終行動を正しく
  `continue_fleeing_up_to_10_years`とした一方、拘束の`plan_owner`を皓茉莉花とし、末尾ページも欠落したため
  不合格となった。自動経路は4ブロック中3ブロックの合格でfail closedとし、Qwen比較を完走する場合だけ、
  原文照合済みの別Luna出力をブロック4の`human_reviewed_salvage`として分離利用した。Compact用プロンプトは
  設定したが、独立した1ブロック実行ではCompact自体が発動していないため、改善要因をCompactへ帰属しない。
  効果が確認できたのは、外部状態契約、新規コンテキスト、OCR直接入力、出力件数抑制、末尾網羅ゲートである。
  Qwen3.6 35B-A3Bの二段階生成は、根拠の`[page N]`記号が初稿・校正版へ漏れて初回不合格となり、通常の
  日本語注記へ変換した再試行で詳細1,637字、一覧529字を合計470.43秒で生成した。詳細版は珀陽の作戦と
  黎天河の物理的拘束を分離し、「牢へ戻る」を最終結果にしなかったが、「最長10年」を「10年」と断定し、
  中国字が混入した。一覧版は拘束実行者を省略し、戦争回避を完了済みへ強めたため、両成果物を公開不可とする。
  本番候補では全ブロック機械合格、事実表の日本語正規化、最大期間・確信度・主体を対象にした意味ゲートを必須とする。
- **検証fail closed**: 検証応答のJSON形式不正、主張IDの欠落・重複、検証本文に未提示のページの引用、
  根拠ページなしの`supported`、`contradicted / unsupported`、重要事実の欠落はすべて不合格とする。
  候補要約が検証の最大64主張を超えた場合もモデルを呼ばず不合格とするが、候補全文、分解した
  全主張、上限超過エラーは監査行へ保存し、確率的な冗長化を再診断できるようにする。
  JSON・主張ID・引用ページなど出力契約の検証に失敗した場合だけ、元の検査入力、初回応答、
  具体的な検証エラーを同じ検証モデルへ渡して1回だけ訂正させ、訂正版にも同一の厳格検証を行う。
  訂正時も提示本文ページを拡張せず、根拠が提示本文内にない主張は`unsupported`とする。
  正常に構文解析できた`contradicted / unsupported`や重要事実の欠落は内容上の不合格であり、
  判定を変えるための再試行を行わない。
  結果は`summary_grounding_reports`へ監査保存し、不合格時は人物生成と公開一括確定へ進まない。
  訂正を実行した監査ログには初回エラーと初回応答を残す。訂正後も構文・候補外引用で失敗した
  場合は、候補要約の各主張、主張ごとの許可候補ページ、検証プロンプトへ実際に提示したページ、
  初回・訂正の両方の生応答を保存し、検索候補とモデル引用のどちらに原因があるかを再診断できる
  ようにする。
- **品質ゲート**: 空出力、生成マーカーやコードフェンスの混入、同一文・同一段落の反復、人物名を一度も明示しない人物説明を不合格にする。人物は本文一致ページが1件以上必要で、保守的な短縮別名は2ページ以上一致した場合だけ根拠に使う。
- **人物集合の削除回帰ゲート**: 公開版と新候補を上記の規則で正規化してから比較する。
  公開版人物名が現在の`index_eligible=1`本文に完全一致するか、保守的な短縮別名が2ページ以上に
  一致するにもかかわらず新候補から消えた場合はfail closedとし、一括確定へ進まない。
  現在本文に根拠がない公開版人物だけは、除外理由をログへ残して削除を許可する。
- **機械品質ゲートの限界**: 文章形状検査、Step 2e、正規名統合、人物削除回帰ゲートにより、
  10巻パイロットで判明した機械検査の不足を塞ぐ。ただし初回の10巻再パイロットと全冊展開では、
  旧版・新版の全文差分とCodex補助QAを引き続き公開条件とする。
  構造化事実のページ番号が実在しても、1件の事実内で途中状態と最終結果が矛盾する可能性は残る。
  事実表そのものを該当ページ本文へ意味照合する独立ゲートを実装するまでは、双方向要約検証の
  合格だけで全冊自動公開しない。
- **一括確定**: 詳細あらすじ、短縮要約、全人物説明をメモリ上で完成・検査してから、`books.summary`、`books.catalog_summary`、`book_characters`を単一SQLiteトランザクションで置換する。いずれかの生成・校正・検査が失敗した場合はDBを書き換えず、既存公開版を維持する。コミット後に詳細あらすじのLanceDB embeddingを更新し、失敗時は従来どおりSQLite本文を正として次回再実行する。
- **skip 条件**: `books.summary`、`books.catalog_summary`、`book_characters.summary`がすべて存在し、かつ`redo=False`ならStep 2全体をスキップする。旧構築済み書籍で短縮要約だけがない場合は再生成対象となる。
- **本文入力**: `char_count >= NOVEL_DB_MIN_BODY_CHARS`かつ先頭/末尾`NOVEL_DB_BODY_PAGE_MARGIN`ページを除いた`index_eligible=1`本文を、ページ番号付きでページ順に使用する。
- **生成文の品質方針**: 詳細あらすじ、分割要約、人物像には目標文字数や
  1段落固定を設けない。`num_predict`はLLM暴走防止とcontext保護の技術上限であり、
  文章をその長さへ縮める要件ではない。必要情報を過不足なく伝え、主語・因果・
  時系列・人物関係を省略しない自然な日本語を優先する。
- **短縮要約の受入条件**: 書籍一覧の選書判断用に400〜700文字を必須とし、中心人物、
  発端、中心課題、主要な転機または対立、結果、重要な関係変化を自然な文章で伝える。
  詳細版の網羅性は求めないが、書かれた主張はすべて本文根拠を必要とする。
- **書籍サマリの受入条件**: 中心人物、発端、主要な対立と出来事、転機、結果、
  関係性の変化、巻のテーマまたはシリーズ上の意味が、未読の内部事情を知らない
  読者にも流れとして理解できる。場面羅列、名詞句の連結、文字数合わせの圧縮を
  避け、話題の切れ目では段落を分ける。
- **人物像の受入条件**: 「誰で、どの立場にあり、誰とどう関係するか」を最初に
  明示し、この巻での主要な行動・選択、その理由や心情、関係の変化、物語上の役割を
  根拠本文の範囲で説明する。登場量が少ない人物は情報を水増しせず、重要人物は
  必要に応じて複数段落で説明する。曖昧な代名詞、電文調、根拠のない補完を避ける。
- **不完全出力の扱い**: 事実表の書籍事実または人物事実を識別できない、完成文を品質ゲートへ通せない場合はエラーにして再実行する。不完全な生成物の一部だけを保存しない。
- **再生成監査**: 既存公開版を`audit_generated_content.py snapshot`でJSONへ退避してから
  再生成する。再生成後は`diff`で詳細あらすじ・短縮要約・人物集合・人物説明・生成日時・機械品質ゲートの
  差分をJSONとMarkdownへ出力し、変更された全文をCodex補助QAの対象にする。
  人手QAで不採用の場合は、書名の完全一致確認を必須とする`restore`でSQLiteの旧版を
  トランザクション復元する。復元後のサマリembedding更新に失敗した場合もSQLiteを正本とし、
  エラー終了して次回の再index対象とする。

補足: `character_summarizer.summarize_character`は、1キャラ×1冊の個別執筆と全巻範囲入力選択を担い、full buildとCLI `build_character_summaries.py`から共用する。`character_db`は`book_characters`の集計・CRUDを担う。

## 5. ステップ 4: チャンク文脈生成（`full_builder.build_book_contexts` + `contextualizer`）B-9

Anthropic の Contextual Retrieval 手法。各チャンクに「書籍内のどの場面か」の 1 文（80〜120 字）を付け、`(contextual_text + 本文)` を再 embedding して recall を上げる。**B-23 で full_build から分離した独立ジョブ**（`mode=generate_contexts`）。

- **生成（`contextualizer.generate_chunk_context`）**: 書名 + 書籍サマリ + チャンク先頭 1200 字を GEMMA_BACKEND に投げる。プロンプトは**本文の固有名詞と特徴的フレーズを必ず含める**よう明示（`num_predict=256`, `num_ctx=8192`）。失敗時は空文字を返し未処理のまま残す。
- **対象**: `book.summary` がある書籍の、`contextual_text IS NULL` のチャンク（`redo=True` で全チャンク）。サマリ未生成の書籍はスキップ（Step 2 が前提）。
- **skip 判定（`should_skip_context`）**: `char_count < NOVEL_DB_MIN_BODY_CHARS`(300) または先頭/末尾 `NOVEL_DB_BODY_PAGE_MARGIN`(5) ページ以内のチャンクは `contextual_text = NULL` に保つ。
- **再 embedding（`make_embedding_input`）**: `ctx` があれば `ctx + "\n\n" + text`、無ければ `text` のみを bge-m3 で再計算する。文脈生成は LLM の失敗をチャンク単位で隔離し、成功分を最大 16 件ずつ `embed_batch` へ渡す。LanceDB は同一バッチの `chunk_id IN (...)` を一括削除してから行群を 1 回で追加し、SQLite は `executemany` と 1 transaction で `contextual_text` を確定する。Embedding / LanceDB 更新に失敗したバッチは SQLite を未更新に保つため、`redo=False` の次回ジョブで再試行できる。

## 6. 補助ステップ

- **主要登場人物抽出（`character_extractor.extract_main_characters`）**: 各ページ本文（先頭 1500 字）を GEMMA_BACKEND に投げ、最大 3 名をカンマ区切りで取得 → `pages.main_characters`。CLI `extract_characters.py` で任意実行。用途は 3 つ: 検索ヒットのキャラヒント（[検索QA設計](小説RAG_検索QA設計.md)）、`character_db` のキャラ集計（B-15 単独経路）、C-12 の共起カウント。失敗ページは NULL のまま続行。保存済み文字列のカンマ・読点分割、敬称・肩書除去、匿名役職除外、重複排除、上限適用は`character_names`を正本とし、ページ抽出・キャラ集計・full build・関係抽出から共用する。外国人名の中黒`・`は名前の一部として保持し、区切りには使わない。
- **キャラクター関係グラフ（`relation_extractor.generate_book_relations`）C-12**: `pages.main_characters` の同一ページ共起を数えエッジ重みとし、`book_characters.summary` を Qwen に渡して関係タイプ（友人・師弟・敵対 等）を JSON 抽出 → `character_relations` に REPLACE。`mode=generate_relations` ジョブ。読み取りは `graph_query`（series 単位で nodes/edges 組み立て、内部利用のみで専用 API 無し）。

---

## 7. 再構築ジョブ（`job_queue` + `job_worker`）

全処理は `rebuild_jobs` テーブル経由の**全体ロック + 単一 worker 直列実行**。並列化は GPU/CPU 高負荷のため逆効果、書籍単位ロックの実装複雑化は利得薄、という判断。

- **`NovelDbJobQueue`**: `enqueue(job_type, target_id, mode)` / `cancel` / `get_status` とライフサイクル。`start()` で「`running` を `failed` に戻す（サーバ再起動時）」+ 旧 mode 名の migration（`pdf_text→rebuild` / `reocr→ocr`）を実行し worker スレッドを起動。`main.py` の lifespan で start/stop。
- **`NovelDbJobWorker`**: 5 秒 polling + wakeup Event。`_claim_next_job`（`queued` を古い順に 1 件 `running` 化）→ `_execute_job`（mode 分岐）→ `_mark_finished`。progress/step/detail を `rebuild_jobs` に逐次書き込み、UI がポーリング表示する。ただし、`rebuild_from_pages` が同じ `novel.db` の書込みトランザクションを保持している間の `current_detail` 更新は補助的な表示情報として扱う。別接続が `database is locked` になった場合は詳細更新だけを省略し、本文チャンク・embedding の本処理を失敗させない。ジョブ終了時の progress/state 更新は必須とする。
- **シリーズメタ索引**: `series_meta.load_book_series_ids()` が meta2.db の novel メタを `book_name → series_id` の辞書へ変換する正本。`generate_relations` のジョブ開始時に1回だけ読み、全対象書籍で共有する。CLIの `--series` 対象解決も `book_names_for_series()` を使い、PDF拡張子除去や空ID判定を重複実装しない。

**JobMode と対象書籍（`_resolve_targets`, `job_type="all"` 時）**:

| mode | 処理 | `all` 時の対象 |
|---|---|---|
| `ocr` | 画像 → Surya OCR 2（yomitoku限定補助）→ 品質ゲート → `pages.full_text` | `ocr_done_at IS NULL`（未 OCR） |
| `rebuild` | `pages` → chunks/embedding 再構築 | `ocr_done_at IS NOT NULL`（OCR 済み全冊） |
| `full_build` | rebuild + サマリ + キャラ辞典 | `ocr_done_at IS NOT NULL AND indexed_at IS NULL` |
| `generate_contexts` | チャンク文脈 + 再 embedding | `contextual_text IS NULL` のチャンクを持つ書籍 |
| `generate_relations` | キャラ関係グラフ（C-12） | OCR 済み全冊 |

`job_type="book"` は `target_id` の 1 冊、`job_type="series"` は meta2.db から解決したシリーズ内 novel 書籍。旧 `pdf_text`/`reocr` は起動時 migration で正規化済み。

**キャンセル仕様**: `queued` のジョブのみ `DELETE /builds/{id}` で `canceled` にできる。`running` の DELETE は **409 Conflict**（実行途中中断は embedding バッチ整合性を壊すため不可）。

**失敗時**: `_execute_job` 例外は `state='failed'` + `error_message`（traceback 込み）。
SQLiteとLanceDBをまたぐ更新は単一トランザクションではないため、書籍単位
`rebuild_from_pages`が失敗した場合は同じ書籍を再実行して両ストアを収束させる。
ページ単位`rebuild_page_from_pages`は旧ベクトル退避・補償復元と
`indexed_at=NULL`の不完全状態マーカーを備え、復元できない場合は書籍単位再構築へ
フォールバックする。

---

## 8. CLI と処理順序

CLI 一覧は [データ設計 §3.3](小説RAG_データ.md)。UI の各ボタンは同等のジョブを投入する。推奨順序:

```
ocr → full_build（= rebuild + summary + characters）→ generate_contexts →（任意）generate_relations
```

`generate_contexts` は `books.summary` を前提とするため full_build より後。テストは `backend/tests/test_novel_db_*.py`（embedding / LLM はモック）。
