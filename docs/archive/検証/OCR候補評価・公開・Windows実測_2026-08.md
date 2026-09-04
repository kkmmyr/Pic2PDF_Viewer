# OCR候補評価・公開・Windows実測（2026年8月）

> status: archived | archived-at: 2026-09-05 | source-revision: 4598d76

OCR設計書から分離した当時の検証記録。以下の本文は採否・保留・失敗・公開前後の区別を含めて保持した。
記録中の現在形や「受入基準」は当時の記述であり、現在の実装・DB状態・承認を保証しない。
現行契約は[OCR設計書](../../design/詳細設計/機能別/OCR設計書.md)、
時系列の補足は[OCR品質改善 技術知見](../../log/技術知見/OCR品質改善_技術知見.md)を参照する。

<a id="run184"></a>
## 1. run 184の隔離pilot・公開・rollback・本番反映

- 2026-08-23の1冊pilotでは、隔離DBのrun 184で57/57画面を完走し、Qwen 42・dots 15を初期候補として
  全57画面を初期`required`、runを`awaiting_qa`にした。Qwen候補解析失敗5、dots候補解析失敗1、
  dots画像のみ4を監査artifactへ保持した。プロジェクトオーナーが候補切替全15画面、候補異常・分類未確定、
  clean標本を含む計19画面を確認し、重大な欠落・読順崩壊なしと判定した。追加の候補差分・原画像監査で、
  画面11の2文重複、13の「したかった」誤認、19の「最悪」意味誤認、36の2文欠落を確定し、補正文へ反映した。
  画面1・4は画像のみ、画面6は本文／全幅本文に分類した。追加7画面をCodex原画像監査、残るclean通常本文
  31画面をADR-0023の機械支援監査として承認し、全57画面を承認済みにした。
- run 184は隔離DBで一度公開し、57画面・42,903文字の選択／補正済み本文とFTSが一致することを確認した。
  公開前backupは`20260823T105530.007192Z-publish-run-184-b4ab82ec2dc7`（389,599,232 bytes）で、
  manifestと復元DBの`integrity_check=ok`を確認した。その後、旧run 76へrollbackし、57画面・41,707文字の
  本文、文字数、page分類、索引可否、FTSが公開前世代と一致することを確認した。rollback前backupは
  `20260823T105642.543933Z-rollback-run-76-4773195e9bcb`（390,479,872 bytes）で同じ検証に合格した。
  隔離DBはrun 76のrollback publicationをactive、run 184を`completed / approved`のまま保持する。
  本番DBは変更していない。
- 同じrun 184を`codex-reviewed-ocr-package-v1`へexportした隔離往復では、packageは1,276,317 bytes、
  digestは`cc63d0e21ac7aed4d24772c4cdfcbb3d09744e5ec01851a760698b906ae0d25e`だった。レビュー根拠は
  owner原画像確認19、機械監査31、Codex原画像確認7、補正pageは11・13・19・36として保持した。一時DBへの
  初回importは57件、再importは同一runの57件すべてを冪等判定し、import前後のcanonical digestは不変だった。
  明示公開後はpackageと57件一致・FTS不一致0、旧run 76へのrollback後はcanonical完全復元、publish／rollback
  backup各1世代のSHA・integrityと最終DB integrityに合格した。本番DBは変更していない。
- その後の本番反映では、review noteを含むpackage digest
  `d78907dfedf71deadde157104e7b7b5e7b30026f9da88ba39bf40b165e04ec98`をproduction run 184へ
  57件stagingし、再import 57件の冪等一致を確認した。事前backupとの直接比較でcanonical pages、
  publication history、FTS5、page-level ICU stateがstaging前後で完全一致した後、publication ID 82として
  明示公開した。公開本文は57画面・42,903文字、`index_eligible=1`は49画面、FTS5本文不一致0件である。
  page-level ICUはrevision 1・8,568行・source SHA-256
  `55c8f39783ffdd30e3f4305362e79383da8ae16195f33edb003ec86945367d89`へactive化し、対象書籍の
  bge-m3 chunk 83件はSQLite／LanceDBでID・画面番号・本文が一致した。公開前全体backup、公開処理内backup、
  公開後・embedding前backup、全処理後の`2026-08-23_ocr-run184-complete`を保持し、各SQLiteと
  LanceDB復元検査に合格している。

<a id="windows-runtime"></a>
## 2. Windows run 189・190の監査保存

2026-08-29のWindows受入では、138画面のrun 190がWindows 11、RTX 5070、CUDA 12.8、
YomiToku 0.12.0、PyTorch 2.11.0+cu128、Git commit、pipeline/model/mmproj SHAをmanifestへ固定し、
全画面で両候補・候補manifest・工程時間を保存した。空のprimary候補18件も空のまま監査保存され、
同一入力のrun 185に対して`failed`から`passed`へ3件改善、逆方向の遷移は0件だった。

この受入でページの`passed` 117件、`failed` 21件は品質リスク分類であり、runの実行成否とは分ける。
全138画面を`required`、runを`awaiting_qa / pending`として隔離し、公開版・canonical本文・検索索引は
変更しなかった。先行run 189は原候補本文とmanifestのSHA不一致で19画面時点にfail closedとなり、
checkpointを保持したまま公開へ進まなかった。この挙動を監査保存の受入基準とする。


<a id="candidate-screening"></a>
## 3. 固定候補のscreeningと採否

- Google Document AI Enterprise OCR `pretrained-ocr-v2.1.1-2025-01-31`は、2026-08-22の
  開封済み30画面pilotでルビ混入と縦列読順崩壊を確認したため、正規本文の生成元にしない。
  利用する場合は外部候補としてstagingに隔離し、列coverage・約物・ルビを原画像で独立確認する。
  pilot差分率はverified ground truthに対するCERではなく、自動公開条件へ転用しない。
- Unlimited-OCR BF16は、MLX-VLM 0.6.15の固定5枚で全ページが生成反復し、総合CER
  690.7200%、ページ最大1,069.3122%だったため本番候補にしない。最大RSS約7.42GB、swap 0なので
  64GB unified memory不足による不合格とは扱わない。反復除去後の本文を採用値へ転用しない。
- Nemotron Parse 2.0 MLX 8bitは、元実装の専用task token列と日本語decode回避を
  適用してもJSSODa固定先頭1枚で誤認文節が4,096 token上限まで反復した。
  swap 0であり64GB unified memory不足ではない。標準MLX-VLMの逐次decodeでは
  日本語tokenによる`KeyError`も起きるため、runtime修正だけで品質合格と見なさず、
  固定revisionは本番候補にしない。元モデルの利用条件はOpenMDW-1.1、tokenizerはCC-BY-4.0とする。
- Qianfan-OCR MLX 4bitは、公式基準prompt・temperature 0でも固定`000006`がCER 2.0270%、
  `000142`がCER 753.8883%・同一文節反復となった。停止までのpeak footprintは約6.90GiB、
  swap 0であり64GB unified memory不足ではない。変換元revisionもconfigから復元できないため、
  固定変換版を本番候補にせず、反復penaltyや文字列切出しで採用値を救済しない。
- HunyuanOCR 1.5 BF16 GGUFは、公式llama.cpp生成条件で固定`000006`をCER 0.3378%で通過したが、
  `000142`は段落重複・順序入替によりCER 13.0340%だった。最大RSS約14.34GiB、swap 0であり
  64GB unified memory不足ではない。固定GGUF pairを本番候補にせず、段落dedupe・順序補正で
  採用値を救済しない。
- Hayai OCR v2は固定revision、固定custom code、公式greedy生成とrepetition penalty 1.20で
  JSSODa固定1枚目を診断したが、592文字に対して8文字出力・CER 99.4932%だった。
  最大RSS約1.59GiBで64GB不足ではなく、短い漫画crop向けモデルの全文coverage不適合とする。
  残りへ進めず本番候補にせず、短文crop化や回転、patch数変更で救済しない。
- fail-fast不採用候補の一回限りrunnerは恒久保守資産にしない。runtime差分を再診断する期限付きrunnerだけを
  `maintenance_assets.json`へ登録し、実測・revision・hash・失敗原因は設計書と技術知見を正本とする。
- Qwen3.5-OCR-JP-2Bは公式固定prompt、greedy生成、最大8,000 token、固定revisionでJSSODaを評価する。
  HTML layout blockはDOM順の可視文字へ復号し、rubyの`rt`だけを除外する。blockの並べ替え、本文dedupe、
  言語補正は行わず、raw HTMLも保存する。固定5枚中4枚は総合CER 0.2416%だったが、`001751`が
  8,000 tokenまで反復したため単体候補は不採用とする。
- Qwen3.5 OCR + dots.mocr複合候補は、抽出本文へ既存`has_suspicious_repetition`を適用し、反復または
  8,000 token到達によるHTML末尾切断ならdots.mocr、それ以外はQwenを採用する。selectorは正解本文、CER、
  ページIDを参照しない。固定5枚では`001751`だけが
  fallback対象となり、保存済みdots固定5枚集計から導く合成上界は総合CER 0.3285%以下、最大0.6907%以下である。
  次の固定79枚でも未修復raw出力、HTML末尾切断flag、両候補のprovenanceを保存し、選択後の総合0.5%未満・
  最大2.0%未満を判定する。実測は15枚時点で総合CER 0.5166%、最大3.1042%となり、最大ページに
  反復・切断signalがないためfail-fast不採用とする。正解を見たLatin文字やページID条件をselectorへ追加しない。
- 公開screening調整用v2では、plain textへ保持しない`div` / `ruby` / `rt` / `p` / `br`以外のinline HTML markupも
  fallback候補信号として記録できる。tag内本文を推測補正せずページ全体をdots.mocrへ送り、同じ公開79枚を
  最初から再評価する。これは開封済みscreeningで発見した規則なので正式holdoutの合格実績には数えない。
  実測は`000260`だけをfallbackし、15枚総合CER 0.4776%へ改善したが、同ページのdots出力が2.2173%で
  最大gateを超えた。残りへ進めずv2も不採用とする。
- ADR-0022のレビュー前提v3は、Qwenとdotsを全ページで実行し、反復・HTML切断・非保持markup・
  隣接する狭いvertical blockの左→右bbox順に加えて`is_external_materially_more_complete`をレビュー初期候補の
  切替信号へ使う。bbox幅300超、上下端差25超、非隣接blockは比較せず、広い段落領域の誤検知を避ける。
  固定79枚の再開後、`000653`でQwenが
  中央2段落を欠落してCER 33.3333%となったが既存異常signalがなく、文字量差なら検出できることを確認した。
  selectorは両候補のID・画像SHAを完全一致で検証し、各候補内でmodel revision・fingerprint・promptが
  全ページ同一であることも検査する。選択後も両本文をQAへ保存する。
  79枚中Qwen 72枚、dots 7枚を初期候補に選び、総編集距離223/54,504文字、加重CER 0.4091%、
  ページ最大2.8835%となった。総合gateは通るが最大gateに未達である。この規則は開封済みscreening由来なので
  未調整holdout合格値には数えず、自動公開へは昇格しない。人手照合範囲はADR-0023を正本とする。
