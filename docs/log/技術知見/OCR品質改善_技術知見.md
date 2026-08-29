# OCR品質改善 技術知見

> status: living | last-verified: 2026-08-29

OCR品質改善で得た実測結果、失敗事例、採否判断を時系列に保存する。
現在の公開契約は [OCR設計書](../../design/詳細設計/機能別/OCR設計書.md)、
未完了作業は [小説OCR品質改善 実装計画](../計画/小説OCR品質改善_実装計画.md)、
機械判定値は `scripts/maintenance/ocr_quality_policy.json` を正本とする。

## 1. 2026-07-19〜26: 初期基準と再現性問題

- 縦書きリフロー小説では紙面ページ番号とキャプチャ画面番号が一致しない。実測では
  紙面1〜265ページと表紙が97画面へ配置されたため、DBと引用導線はPNG由来の
  キャプチャ画面番号を正本にした。
- 『茉莉花官吏伝 十八』91画面と『十三歳の誕生日、皇后になりました。10』92画面を
  Surya OCR 2で処理した初期基準では、合格106・失敗77、再試行98画面だった。
- 同一画像でも単独実行と全冊実行で本文が変化した。合格判定済みの候補にも人物名誤読と
  短い縦列の欠落が残り、構造・coverage合格と文字単位の正しさを分離する必要が確定した。
- yomitokuは最低confidenceだけでは棄却できなかった。既知画面では最低0.184でも中央値0.907、
  文字数加重平均0.78で、Suryaが落とした短い列を回収した。

## 2. 2026-07-26: 固定20画面と無料OCR予備比較

ページ種別を `narrative` / `toc` / `illustration` / `colophon_or_ad` に分け、
20画面の人手正解を画像SHA付きで固定した。基準内訳は通常散文9、目次4、挿絵4、奥付3、
正規化文字数9,429字だった。

予備比較では次を確認した。

| 候補 | 実測上の結論 |
|---|---|
| NDLOCR-Lite | CPUで高速。列の存在確認には有効だが誤字・混入・重複が多く主系には不採用 |
| manga-ocr | ページ全体では原文にない自然文を生成し、不採用 |
| PaddleOCR PP-OCRv5 | 列を検出したが欠字が多く、Windows CPUで遅いため主系には不採用 |
| Tesseract `jpn_vert` | 軽量だが固有名詞誤読が多く、補助診断に限定 |

## 3. 2026-07-27〜28: QA公開とシリーズ再処理

- 茉莉花官吏伝8〜17巻を直列処理し、全ページ処理後も `awaiting_qa` で止める運用を確立した。
- 1〜7巻の再処理では、別作品試し読みが `narrative` 候補になる、本系と補助系が同じ固有名詞を
  誤る、同一文を反復する、という公開前リスクを確認した。
- 反復監査では実反復6ページを画像照合後に補正し、公開中の未解決反復を0件にした。
- ページ種別、補正文、採用候補、承認状態を別々に保持し、原画像を監査正本として残した。

## 4. 2026-07-29〜31: 列欠落と補正文採用元の不整合

『ふつつかな悪女ではございますが』1巻120画面では、機械上116画面が合格した一方、
通常本文8画面で主系本文から縦列が丸ごと欠落していた。不採用の補助候補は35〜123文字長く、
欠落列を保持していた。候補の文字量差はQA優先度には使えるが、長い候補の自動採用はできない。

4シリーズ46冊・5,585画面の全画面QAでは、本文4,625画面と非本文960画面を分離し、
1,354画面へ画像照合済み補正文を保存した。薬屋11〜16巻の308画面で、補正文が非空でも
`selected_engine=primary / external`のままの不整合を検出した。SQLite Online Backup後に
公開本文・FTSを再同期し、補正文あり・採用元非codexと公開本文不一致を各0件にした。

この事故から、`corrected_text`が非空なら同じQA更新で`selected_engine=codex`を保存し、
APIで不整合な組み合わせを拒否する契約を導入した。

## 5. 2026-08-01: 入力完全性と公開後監査

- グリムコネクト1〜3巻の旧入力は20・18・14画面で途中終了していた。OCR runの承認は
  入力範囲内の品質だけを表し、書籍全体の完全性を保証しないと判明した。
- 再撮影後は168・168・141画面となった。OCR前にKindle終端、連番、復号、寸法、重複・白紙候補、
  先頭・中間・末尾を確認する運用へ変更した。
- 通知UIが3画面へ重なった事例から、強い製品名または複数UI固有語をQA必須flagへ送るようにした。
- 46冊の公開後再監査では、DB整合性、ページ件数、公開本文、種別・索引、採用元、UI混入、
  隣接完全重複の既知不整合を0件にした。これは文字単位の完全正解を意味しない。

## 6. B-35複合ゲートの実測

初回の固定20画面では、通常散文加重CER 1.82%、ページ最大CER 2.07%、上限超過4/4画面、
列欠落疑い2画面で `FAIL` だった。固有名詞は10表記・121/121出現で合格したため、
固有名詞だけでも平均CERだけでも公開可否を決められないことが確認できた。

第三OCRとoracle評価では次の結論を得た。

- NDLOCR-Lite、YomiToku 0.14.0、Tesseract、PP-OCRv5はいずれも単独の公開条件を満たさない。
- 候補集合の参照位置oracleが改善しても、実際の選択器出力の合格を意味しない。
- 約物正規化と固定標本向けgap consensusは固定通常散文でCER 0.342%まで改善したが、
  4シリーズ20画面の開封済みholdoutでは汎化しなかった。
- 候補多数決は共通系統誤りを残す。候補間の合意や距離の小ささは正しさの証拠にならない。

監査成果物は
`backend/data/kindle_capture/audits/2026-07-28-four-novel-series/b35-*.json`
に保存している。

## 7. PARSeq追加学習pilot

NDLOCR-Lite配布ONNXから175 tensor・8,831,654 parameterの互換state dictを復元し、
32実画像・3,333 token位置でONNX Runtimeとのtop-1不一致0件を確認した。
49,741行（train 45,861、validation 3,880）の追加学習で、validation完全一致率は
67.2680%から89.4072%、NEDは97.9581%から99.4649%へ改善した。

しかし未調整holdoutでは配布ONNX CER 3.2843%に対し追加学習版2.6682%で、
B-35の0.5%に届かなかった。列gap cropの診断は2.2758%まで改善したが、同じholdoutを見て
閾値を定めたため採用根拠にはしなかった。追加学習ONNXは本番へ差し替えていない。

教訓は、行認識器のvalidation改善やONNX同値性は、列検出、順序、ページ結合、約物、
固有名詞を含むページ品質の代替指標にならないことである。

## 8. 新規3シリーズholdoutとCodex補助境界

候補品質を見ずに『悪役令嬢レベル99』『後宮一番の悪女』各10画面を固定し、
原画像QAで27,629字のverified ground truthを作成した。候補結果はprimary 3.18%、
external 2.24%、配布NDLOCR 1.38%、追加学習NDLOCR 0.81%、文字位置合議0.44%だった。
集計CERは達成したが、ページ最大1.946%と固有名詞266/278により総合 `FAIL` だった。

候補支持付きの同長1文字固有名詞補正でCER 0.398%、固有名詞277/278まで改善したが、
ページ最大1.647%のため機械単独は不合格だった。昇格7画面へ画像照合済み本文を適用した
Codex補助込み候補はCER 0.23%、ページ最大0.714%、固有名詞278/278で合格した。

第三シリーズ『虚構推理短編集 岩永琴子の密室』10画面を加えた30画面・48,296字では、
4候補合議＋固有名詞補正がCER 0.474%でも、ページ最大3.470%、固有名詞529/536で
機械総合ゲートは不合格だった。全30画面の画像照合済み結果0%は正解化実績であり、
未知ページへの機械性能やCodex省略可否の根拠には数えない。

## 9. モデル委任の実測

代表通常散文1画面でLunaを予備評価した。現行候補CER 1.96%に対し、本文領域切り出しは
1.63%、機械候補併用は1.20%まで改善したが、0.5%未達だった。低推論は本文列を欠落し、
高推論は4分で完成本文を返さなかった。括弧変更などの誤提案も確認した。

したがってLunaは差分要約、QA優先順位、修正案作成に限定し、本文確定・ページ分類・承認・
公開を行わない。Solまたは人の省略は、別の未調整holdoutと反復・出力契約試験を通過するまで
解禁しない。

## 10. 現在も残る検証上の穴

- `ocr_quality_policy.json` は汎用品質ゲートを強制するが、B-35固有の3シリーズ以上、
  通常散文20画面以上、再開封拒否、全QAパッケージdigestを強制しない。
- `seed` / `benchmark` は開封済みholdoutの再利用を拒否しない。
- `--verify-queue` は優先集合を検査するが、パッケージ全体を保証しない経路がある。
- これらを実装するまではB-35を完了扱いにせず、自動公開とCodex最終確認省略を禁止する。

## 11. 2026-08-17: 未調整正式holdoutの一度限り評価

候補品質を参照せず3シリーズ30画面を選定し、原画像QAで29通常散文・1章扉、29,001字、
固有名詞25語・430出現を封印した。正式評価の直前に、汎用corpus用固有名詞注釈とページ種別件数が
formal manifestへ誤って二重適用される問題を検出したため、manifest注釈・構成を正本とする既定契約へ
修正し、26件の回帰テスト後に同一manifestを一度だけ開封した。

現行primaryの結果は通常散文CER 27.4038%、ページ最大496.7509%、列欠落疑い3画面、
固有名詞324/430（75.3488%）で総合 `FAIL` だった。1画面の反復出力が6,880編集を占めたが、
この外れ値を除いても1,066/27,611字、CER 3.8608%で基準0.5%に届かない。シリーズ別CERも
7.0603%、67.4748%、1.7162%で、最良シリーズでも基準未達だった。

したがって、単一外れ値だけの抑制ではB-35を完了できない。反復停止、縦列欠落回収、人物名の
長音・小書き文字を含む固有名詞保持を固定候補側で改善し、開封済みholdoutは調整用へ降格する。
次の正式判定には新しい品質非参照holdoutを用意する。

## 12. 2026-08-17: 開封後の候補選択診断

開封済みholdoutを調整用へ降格した後、保存済み選択結果、primary、externalを同じformal
scopeで再集計した。保存済み選択結果は通常散文CER 4.1626%、external単体は4.2420%だった。
既存QAリスク検出に以前からあった「primary 256文字以上、externalが30文字・2%以上長い」
条件を候補選択と共有し、externalに反復がない場合だけ必須QA候補へ切り替えると、4画面が
切り替わり、CER 2.1141%、ページ最大10.1805%、列欠落疑い1画面、固有名詞再現率82.5581%
となった。閾値は今回の正解本文から探索せず、候補本文だけで判定する。

YomiToku検出＋MangaOCR認識を第三候補として30画面へ実行したところ、単体CER 70.6753%、
列欠落疑い28画面、固有名詞再現率7.4419%で不採用だった。primary・externalとの文字位置合議も
CER 2.4693%で上記固定版を下回った。正解参照のページoracleではMangaOCR採用は1画面だけで、
3候補oracleもCER 1.4761%、ページ最大10.1805%だった。したがって現候補集合の選択改善だけでは
B-35のCER 0.5%・ページ最大2.0%を同時達成できず、難例を改善する独立候補または部分再OCRが必要である。

この結果は開封済みholdoutの調整値であり、正式性能には数えない。長さがほぼ同じページで
externalが良かった事例もあるが、正解本文を見て追加の採用閾値を作ると過学習になるため導入しない。
固定した全文性判定を次の品質非参照holdoutで一度だけ評価する。

## 13. 2026-08-18: 公開知見とNDLOCR-Lite v1.2.3再評価

公開実装を再確認したところ、国立国会図書館の
[NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite) は、レイアウト認識、文字列認識、
読み順整序を独立モジュールとして組み合わせている。旧評価のcommit `7fd36cd` より新しい
[v1.2.1](https://github.com/ndl-lab/ndlocr-lite/releases/tag/1.2.1) では、学習データ追加後の
認識モデル、DEIM検出境界、カスケード、縦中横が更新された。v1.2.2・v1.2.3は主に入出力と
GUIの修正であるため、最新固定版v1.2.3（`c3cc767`）を開封済みholdoutの調整用候補として評価した。

v1.2.3単体は通常散文CER 3.1832%、ページ最大8.6643%、列欠落疑い0画面、固有名詞再現率
83.7209%だった。primary・external・v1.2.3の正解非参照文字合議はCER 1.1174%、ページ最大
5.3345%、列欠落疑い0画面、固有名詞再現率91.8605%まで改善したが、B-35基準には届かなかった。
正解参照のページoracleもCER 1.3140%であり、単純なページ単位選択だけでは不足する。

一方、生成系OCRの反復は候補選択で遮断できる。primaryの異常反復、external 256文字以上、
external反復なし、という正解非参照条件でexternalへ切り替えると、正式評価最大外れ値だった
run 74 / page 53だけが切り替わり、primary基準のCERは27.4038%から4.1626%、ページ最大は
496.7509%から28.1128%へ低下した。採用結果は必須QAとし、自動公開へ昇格させない。

文書VLMでは視覚token圧縮が強いほど言語事前分布への依存とhallucination riskが増えるという
[実証研究](https://arxiv.org/abs/2601.03714)もあり、同じ全画面生成モデルへの無制限再試行だけで
反復を直す方針は採らない。レイアウト・行bboxを持つ独立候補でcoverageを確認し、反復・列欠落を
別々のflagとして必須QAへ送る。ここでの数値は開封後の調整値であり、正式性能には数えない。

NDLOCRの行bboxからSuryaへ部分再OCRする追加診断では、最大外れ値ページを4列ずつ処理すると
CER 3.1769%まで改善した。しかし同じ4列条件でもseed未指定時は3.5379%へ揺れ、別の難例では
38.6997%まで悪化した。1列ずつは29.6029%、2列ずつは3.6823%で、cropを細かくすれば単調に
改善する関係ではなかった。このため部分再OCRを自動採用せず、候補本文とbboxをQAへ提示する用途に限る。

llama.cppの[server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
はRNG `seed`を受け取り、既定seedはランダム値である。Surya transportへ`seed=0`を固定後、
最大外れ値ページの4列部分再OCRを3回実行し、候補本文SHA-256
`5d546635074fa221469f39782df44a19d934b4187954dab3886c7006c4419945`とCER 3.1769%が
全回一致した。正式候補は固定seedを使うが、GPU・server・model revisionも引き続き監査対象とする。

## 14. 2026-08-18: 候補支持型固有名詞補正とPP-OCRv6追加評価

開封済み30画面に対し、シリーズ単位の公式固有名詞台帳と、同じ整列位置で語を完全一致させた
独立OCR候補を二重の根拠とする補正を評価した。台帳は出版社の
[『おこぼれ姫と円卓の騎士』公式ページ](https://bslogbunko.com/special-contents/okobore/)、
[『後宮の烏』公式特集](https://orangebunko.shueisha.co.jp/feature/shirakawakouko-campaign202004)、
[『蜘蛛ですが、なにか？』公式特設](https://kadokawabooks.jp/special/s12/kumo.html?browser=1)
を根拠とし、巻・ページ・正解本文を含めなかった。

調整用正解の2画面に、公式表記・原画像では「烏妃」である箇所を「鳥妃」とした転記誤りが
計5出現見つかった。封印済み正式コーパスと結果は改変せず、画像SHA、置換前後、出現数、
公式URLを固定した調整用errataを別記録とした。errata適用後の正解で比較すると、3候補合議の
通常散文CER 1.1346%に対し、候補支持型補正は1.0622%、ページ最大5.3345%、列欠落疑い0画面、
固有名詞再現率96.0465%だった。21補正・10画面は全10画面で編集距離を改善し、悪化0、
正味21編集を削減した。ただしページ最大値は変わらず、B-35総合ゲートは `FAIL` のままである。

別認識器として、2026年6月公開の
[PP-OCRv6 medium](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.md)
を最大CER画面で先行評価した。公式の全文検出・認識はCER 33.6462%、NDLOCR行bboxを再利用した
認識器単独でも11.6968%で、現行3候補合議の同画面5.3345%を下回った。縦書きの小書き文字・
句読点脱落が多いため、30画面への拡大評価と正式候補への追加は行わない。

以上から、候補支持型補正は固有名詞保持の固定候補として有望だが、それだけでページ最大値は
解消しない。次は開封済み画面へ閾値を追加せず、小書き文字・約物を保持できる独立候補を作ってから、
新しい品質非参照holdoutを封印する。

## 15. 2026-08-22: Google Document AI Enterprise OCR予備評価

Sol campaignで開封済みの調整用標本から、19冊30画面を固定manifest
（SHA-256 `2b85c32495997536f749a51e1ff8ce0f993306e9e8c30a06e1c683e0d55fb992`）へ束ね、
Google Document AI Enterprise OCR `pretrained-ocr-v2.1.1-2025-01-31`を最大3並列で実行した。
30/30画面で応答・保存に成功し、manifestのsample集合、画像SHA、raw response、抽出textの対応も
全件一致した。疎通確認1画面を別途処理したが、評価集合は30画面から増やしていない。

既存本文が空の非公開9画面を除く21画面では、空白除去後の既存OCRに対する編集距離率が
Google 15.2420%、初回Sol 6.7566%で、既存本文へ近かった画面はGoogle 6、Sol 15だった。
この比較は既存本文を正解と仮定しない相対差であり、CER・正解率ではない。

独立画像checkerが採用可能としたSol候補を参照にできる8画面では、参照に対する編集距離率が
既存OCR 1.5180%、初回Sol 7.7799%、Google 19.8699%となり、8/8画面で既存OCRが最も近かった。
ただしこの参照も人手作成ground truthではなく、開封済みtuning標本なので正式性能値には数えない。
`pilot-059`ではGoogleの列読順が大きく崩れて95.18%差となった。これを除く7画面でもGoogle 8.30%、
初回Sol 8.68%、既存OCR 1.69%で、Googleを既存OCRの置換候補とする根拠は得られなかった。

主要な失敗は、ルビ読みの本文混入、右から左への縦列順序の崩れ、見開き相当の横長画像での
文章断片の先頭移動、鉤括弧・ダッシュ・疑問符の変形だった。したがって同versionのraw textは
正規本文へ自動昇格せず、必要な場合も比較・診断用の外部候補に限定する。再評価する場合は、
別の未開封holdoutを消費する前に、開封済み画面でstable v1と`legacy_layout`を少数比較し、
ルビ除去と列coverage検査を固定してから新しい合格条件を封印する。

## 16. 2026-08-22: 次候補の公開情報screening

[PaddleOCR-VL-1.6](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL-1.6.en.md)
は0.9Bの文書VLMで、公式資料ではOmniDocBench v1.6の総合96.33%、text・reading orderの改善、
screen photographyを含むReal5-OmniDocBenchでの頑健性を報告している。既に不採用とした
PP-OCRv6 mediumとは認識器・pipelineが異なるため、次の独立候補として最初に診断する価値がある。
一方、公開値は汎用文書benchmarkであり、Kindle縦書き日本語の小書き文字・約物を保証しない。

[dots.mocr](https://github.com/studio-dots-ai/dots.mocr)は3Bの多言語文書VLMで、公式repositoryの
汎用document parsing指標では旧dots.ocrとPaddleOCR-VL-1.5を上回るが、日本語縦書き小説に限定した
値は示されていない。したがって次点候補とし、汎用leaderboardだけで導入・正式評価へ進めない。

2026-08-23時点の公式配布はHugging Faceの`dots-studio/dots.mocr`へ移っており、固定revision
`e539fbb52280393adc081b289ec597430a0f9031`のBF16重みは約6.1 GBだった。
[MLX-VLMのdots.mocr実装](https://github.com/Blaizzy/mlx-vlm/tree/main/mlx_vlm/models/dots_ocr)を使うと、
M1 Max 64GBでprocess最大RSS約6.87GiB、MLX peak memory約9.15GBに収まり、5ページをモデル再読込なしで
68.36秒で処理できた。JSSODa縦書き1〜4段4枚とPaddleOCR-VL最大外れ値1枚では、総合CER 0.4654%、
ページ最大0.6614%、列欠落・反復0だった。したがってApple Siliconのメモリ適合性と初期の縦書き精度は通過した。

一方、公式repositoryも解析失敗が残ることを明記し、非公式の
[scene textでの反復・幻覚報告](https://github.com/studio-dots-ai/dots.mocr/issues/1)もある。
5枚だけで安定性を断定せず、生成結果を後処理削除しないJSSODa全件評価と同一画面反復試験を必須にする。
custom Transformers codeは固定snapshotの`configuration_dots.py`、`modeling_dots_ocr.py`、
`modeling_dots_vision.py`を監査済みだが、通常のアプリ実行へ`trust_remote_code`を広げず、隔離した評価CLIでのみ許可する。

同じ79枚を単純OCR promptで評価すると総合CER 1.6402%、最大26.9289%で、罫線分割ページの段落省略と
読順入れ替えが生じた。公式の`prompt_layout_all_en`で領域JSONを取得し、返却順にtextを結合すると、
総合0.8990%、最大4.0155%まで改善し、大規模欠落・反復は解消した。document VLMでは「textだけ」の
promptより、領域検出と読順を同時に要求する公式layout promptが縦書き複数領域にも有効だった。

それでも1〜4段の各group最大は2.4390〜4.0155%で、2.0% gateには届かなかった。temperature 0は
上位5枚を改善せず、layout bbox crop後の再OCRも最大難例を4.0155%から5.6995%へ悪化させた。
64GB unified memoryの不足ではなく文字認識品質の上限であり、今回のrevisionをKindle正式評価へ進めない。
評価CLIは固定snapshot fingerprint、prompt digest、入力SHA、ページ単位fsync、JSON fail closedを保持し、
将来のmodelまたはMLX更新時に同じ公開標本で差分を再現できるようにした。

縦書き日本語の事前screeningには、LREC 2026論文の公式実装
[llm-jp/eval_vertical_ja](https://github.com/llm-jp/eval_vertical_ja)が公開する、合成の
JSSODa-testと実文書由来のVJRODaを用いる。同研究は既存MLLMが横書きより縦書きで悪化することを
報告しているため、多言語OCR対応という表記だけを採用根拠にしない。公開screeningは方向・列順・
出力契約のfail-fast用途に限定し、B-35正式値は同一画像SHAの人手verified ground truthだけでCERを
計算する。screening通過後も、開封済み30画面でページ最大CER、列欠落、固有名詞、小書き文字・約物を
確認し、固定候補が全項目へ届くまで新holdoutを消費しない。

## 17. 2026-08-22: 公開前Online Backupの設計差分

公開・rollbackはSQLite transactionで本文、FTS、active publicationを一体更新するが、設計で必須とした
transaction前のSQLite Online Backup呼び出しが実装経路に存在しなかった。transaction rollbackは
論理的な途中失敗を防ぐ一方、filesystem障害やDBファイル単位の復旧点を代替しない。

公開操作ごとに`novel.db`をOnline Backupし、復元先で`integrity_check=ok`を確認してから世代を原子的に
公開する実装へ変更した。backup失敗時はOCR公開transactionへ入らず、公開前世代を実際に開いて
runとpublicationの状態を照合するtestも追加した。実ディスク不足とprocess hang、本番filesystem上の
世代公開は、通常の一時ディレクトリtestだけで実運用合格とせず、隔離serverで別に確認する。

各公開・rollbackの完全DB世代を監査用に保持し、自動削除は行わない。公開頻度は低い前提だが、
本番昇格前に1世代の実サイズ、保存先空き容量、日次server backupへ退避後の保持規則を確認する。

## 18. 2026-08-22: 縦書き公開screeningの再現契約

PaddleOCR-VL公式資料では、VLM componentだけの直接実行は完全pipelineと同等ではなく、
過剰生成や公称精度を再現できない場合はlayout analysisを含むpipeline使用を最初に確認するよう
明記されている。Apple SiliconではPaddlePaddleによる完全pipelineをclient側で動かし、
MLX-VLM serviceをVLM推論backendとして接続する公式経路がある。このためMac検証でも
MLX-VLMへ画像を直接投げず、`PaddleOCRVL(..., vl_rec_backend="mlx-vlm-server")`を使う。

llm-jpの公式評価実装は、JSSODa-testを`is_vertical`と`num_columns`で分け、VJRODaを実文書の
縦書き標本として評価する。元実装には生成反復を除去するoptionがあるが、今回のscreeningでは
反復自体を失敗として観測するため適用しない。`ocr_benchmark_vertical_screen.py`は公式JSONLの
`id` / `pred`契約を受け、NFKC・空白除去・dash統一を既存B-35比較器と共有する。入力digest、
完全なID対応、model revision、prompt、seedを固定し、公開screening値とKindle正式値を混同しない。

JSSODa-testは2,256件・約456 MB・CC BY 4.0であり、方向と1〜4列の切り分けに使える。
ただし合成画像なので、Kindleのルビ、画面撮影、長文縦列、小書き文字・約物の正式な代替にはしない。
VJRODaも実文書由来だがKindle小説そのものではない。両方を通過した候補だけを開封済み30画面へ
進め、そこでページ最大CER 2.0%未満などの既定条件を満たすまで新holdoutは消費しない。

実公開metadata 2,256件を使ったcontract smokeでは、縦書き1,125件（1列284、2列274、
3列285、4列282）・正規化784,988文字を欠落なく集計し、完全一致入力で全groupのCER 0を確認した。
VJRODaの公式GitLabは同日のMac環境から20秒で接続timeoutしたため、実metadata全件の読込確認は
未実施である。`id` / `text` / `pred`とタグ除去は公式評価実装およびfixtureで固定済みだが、
model推論前に公式hostの再疎通と実metadata digest固定を行う。

## 19. 2026-08-23: Sarashina2.2-OCRを次の独立候補に選定

[公式model card](https://huggingface.co/sbintuitions/sarashina2.2-ocr)は、日本語・英語文書向けの
end-to-end 3B OCRとして縦書き日本語と自然な読順を明示し、VJRODaでCER 22.6、BLEU 79.9を報告する。
同表の旧dots.ocrはCER 40.1であり、縦書き日本語に特化した次候補として診断価値がある。ただし
dots.mocrではなく旧dots.ocrとの比較であり、本プロジェクトのCER契約やKindle画像を代替しない。

公式revision`eafb8d48cb2f2a3a6dce571d26b26586ff048fda`はMIT license、BF16重み約7.8GB、
Transformers 4.57.1とcustom codeを使う。`configuration_sarashina2_vision.py`、
`modeling_sarashina2_vision.py`、`processing_sarashina2_vision.py`のimportとSHA-256を監査し、
ネットワーク、subprocess、任意ファイル操作を持たないことを確認した。通常アプリへremote code許可を
広げず、固定snapshotを照合する隔離CLIだけで評価する。

公式推論はCUDAを例示し、Apple Silicon MPSを保証しない。非公式の日本語手書き比較では推奨
`repetition_penalty=1.2`で数値列の生成loopが発生し、1.3で収束した報告がある。このため公式値を
最初に固定5枚で評価し、loopは後処理削除せず不合格へ残す。1.3は別の診断runとし、採用値へ混ぜない。

固定5枚3,653文字のMPS BF16実測は総合CER 0.2190%、ページ最大0.9259%、完全一致3/5で、
総合0.5%以下・最大2%未満の事前gateを通過した。旧候補で反復した`001751`もCER 0.9259%で収束し、
後処理による反復削除は使用していない。5枚は312.14秒、process最大RSS約9.58GiB、peak memory
footprint約23.73GiBで、64GB unified memory内に収まった。79枚screeningは同一checkpointで継続する。

継続runは71/79枚で総合CER 0.8385%、最大100%となり停止した。`001626`では文字起こし317文字は
完全一致した後、モデルが同内容の要約箇条書きを付加した。明示的に要約・Markdownを禁止しても
image-onlyと完全に同じ649 raw文字を返した。先頭blockだけなら正解になるが、一般文書の正当な段落と
区別できない後処理なので採用しない。71枚3,266.33秒、最大RSS約16.42GiB、peak footprint約54.28GiB、
swap 0であり、品質失敗はmemory不足ではなく出力契約の不安定性である。

H5の実運用確認では、30秒sleepする実workerを0.2秒無通信期限で回収して子PID消滅を確認した。
また本番ext4配置先で388,210,688 bytesのOnline Backupを原子的に公開し、manifest・復元DBとも
`integrity_check=ok`、canonical SHA不変を確認した。監査世代は削除済み。production active releaseには
backup moduleが未配置だったため、deploy後のservice経路確認とroot権限を要する実ENOSPCが残る。
その後、Linux user namespace内の8MiB tmpfsで実ENOSPCを再現し、空き135,168 bytesで
SQLite `OperationalError`、canonical SHA不変、`integrity_check=ok`、公開世代0件を確認した。
host filesystemとproduction DBは変更していないため、残るのはactive releaseへ実装を配置した後の再確認である。

deploy後のactive release`/opt/pic2pdf-viewer/backend-20260823102845-20977`でbackup moduleの配置を確認し、
そのrelease自身から本番ext4へ388,210,688 bytesの監査世代を作成した。manifestと復元DBはともに
`integrity_check=ok`、canonical DBの前後SHAは一致した。対象が監査用run IDで期待したbackup root直下に
あることを検証してから、その監査世代だけを削除した。これによりH5の残件は解消した。

次候補の再調査では、`honmono-ocr`が14,256実画像行の公開benchmarkで縦書きを含む一方、参照先GitHubは
404、モデルは認証なしで取得できず、固定実装を再現できなかったため候補から外した。
`yuta1984/ndlocrlite-web`の入力高24px PARSeqも確認したが、公式NDLOCR-Lite v1.2.3の30・50・100文字版と
3 SHAが完全一致し、既に開封済み30画面で単体CER 3.1832%と判明した候補の再配布だった。さらにWeb側は
24pxモデルへ16px入力を指定しており、そのままの推論経路はshape不一致になる。独立候補として再評価しない。

代わりに、2026年6月公開のBaidu `Unlimited-OCR` 3Bを次候補とする。公式MLX-VLMはsingle-pageに
`document parsing.`を基準promptとして示し、モデル実装がApple Siliconへ追加済みである。MITのBF16変換
revision`6d9f675e3fa73dd49cd03f630868b1941c72803f`を取得し、生成反復を隠す固有後処理を加えず、
JSSODa固定5枚から同じfail-fast gateで評価する。汎用文書benchmarkと日本語縦書き品質は同一視しない。

取得したsnapshotは復元後6.68GBで、MLX-VLM 0.6.15、prompt `document parsing.`、temperature 0、
cropping有効、base 1024px、crop 640px、最大4,096 tokenを固定した。固定5枚はすべて本文途中から
同じ断片を生成上限まで反復し、3,653正解文字に対する総合CER 690.7200%、ページ最大1,069.3122%、
完全一致0%だった。5枚は144.00秒、process最大RSS約7.42GB、peak footprint約13.44GB、swap 0である。
したがって失敗原因は64GB unified memory不足ではなく、この固定MLX生成経路の日本語縦書き品質である。
反復除去を品質値の救済へ使わず、79枚screeningへ進めない。予測CLIはmodel・prompt・入力SHAを固定し、
raw textをページ単位でfsyncするため、将来runtime差分を診断する場合も今回の不採用値と混在させない。
## 20. 2026-08-29: 『りゅうおうのおしごと！』YomiToku速度・環境差監査

1巻のWindows run 185とMacから取り込んだrun 186について、138画面すべての画像SHA-256が
一致することをサーバーDBと再取得画像の双方で確認した。run 186は
`codex_reviewed_qwen35_dots_v1`であり、Qwen・Dots候補をCodexが原画像確認した合成版である。
Mac版YomiToku/MPSの結果ではないため、本比較値をOS差・CUDA対MPS差または正式CERとは呼ばない。
生OCR本文、環境manifest、ページ別指標、実行ログはGit管理外の
`backend/data/novel_db/audits/yomitoku-cross-platform-20260829-ryuuou-v1/`へ固定した。
原画像は監査packageへ複製せず、138画面のSHA manifestだけを保存した。

Windows環境はYomiToku 0.12.0、PyTorch 2.11.0+cu128、Python 3.12.10、RTX 5070、
driver 591.86だった。同一138画面をYomiToku単独で2回処理すると、初期化込み97.89秒と
95.63秒、失敗0、2回の正規化本文は138/138画面で一致した。通常散文93画面の中央値は
約0.80秒/画面だった。run 185の保存済み外部候補とは正規化後125/138画面が一致し、
2日後の固定版再実行と異なる13画面が残った。現在の連続2回は一致するため、直ちに確率的揺らぎと
断定せず、run 185の`model=unversioned`、pipeline・共通OCRの版、実行設定を再現不能にした
provenance欠落として扱う。

同じ30画面を同一Windows上でCPUとCUDAへ通すと、正規化本文は30/30画面で一致した。
ページ処理時間はCPU 367.88秒、CUDA 26.76秒で、CUDAは13.75倍速かった。この固定版・標本では
CUDAは品質差ではなく速度差として観測された。ただしMac MPSは未測定であり、同じ結論を移植しない。

run 186の原画像確認済み合成本文を運用上の比較参照とした場合、現行YomiToku再実行の
通常散文編集距離率は6.600%、ページ最大20.038%、5%超56/93画面だった。この参照は人手転記の
formal ground truthではないためCERではない。一方、run 185ではSurya失敗を契機にYomiToku判定へ
送った画面が17、低confidenceが17、外部候補反復が6、固有名詞候補不一致が17あった。
YomiTokuは空振り回避と重大なSurya欠落・反復の救済に強いが、全ページを無条件採用できる精度には
達していない。通常散文と特殊レイアウトを分け、候補保存とQAを維持する。

速度面ではWindowsのSurya＋YomiToku全pipelineが開始から最終page保存まで49分58秒、
YomiToku単独が1分37.89秒で、OCR段階は約30.6倍短かった。run 186は128画面を
19:49:01〜22:36:39の2時間47分38秒で確認しており、15分以上の空白を別sessionとした4 sessionの
観測span合計は1時間6分1秒だった。採用元はCodex補正110、primary 22、external 6である。
review時刻はbatch/packageの証跡で人のdwell timeではなく、Mac側OCR開始時刻もないため、
「OCR＋QA＋修正」の厳密な総時間は未確定である。それでも現状はOCRより確認・補正が支配的で、
速度優位を運用成果へ変えるには重大誤りの検出recallを落とさずQA対象を縮小する必要がある。

追加で、run 185の外部候補採用ページでは保存済み`primary_text`が`external_text`と同値になり、
元のSurya候補を後から独立比較できない画面があった。次の品質調整前に、候補を上書きせず保存し、
YomiToku・PyTorch・device・model/pipeline SHAとOCR/QA/補正時間をrunへ版付き記録する。
