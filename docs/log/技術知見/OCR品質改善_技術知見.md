# OCR品質改善 技術知見

> status: living | last-verified: 2026-08-22

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

## 20. 2026-08-23: Nemotron Parse 2.0のMLX日本語縦書き診断

[NVIDIA公式model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-Parse-2.0)は、903M parameterの
C-RADIO vision encoder + mBART decoderで、20,000 tokenの語彙拡張とCJK・Indicの改善を示す。
MOSCARに日本語を含むが、公開指標は日本語縦書き小説の文字精度を直接保証しない。
調査時の元モデルrevisionは`b6742064f4a8cf22a10383ece5e7fbead355ac04`、利用条件は
OpenMDW License Agreement 1.1であり、同梱tokenizerはCC-BY-4.0である。MLX変換のconfigにsource revisionは記録されておらず、
変換元の厳密なcommitは復元できない。変換cardのApache-2.0 metadataは元licenseを上書きする
根拠としない。

[MLX 8bit変換](https://huggingface.co/mlx-community/Nemotron-Parse-2.0-8bit) revision
`e7e89479657fb3631028ac12b6bc0d5a59ceafe4`は1,658,167,275 byteの重みを持ち、変換cardの
M2 Pro計測はピークRAM 14.50GBである。4bit版は同cardの表文書で生成反復回帰を起こしたため、
8bitだけを評価した。[MLX-VLM移植PR](https://github.com/Blaizzy/mlx-vlm/pull/1866)は同一入力の
Hugging Face CPU経路とbyte-for-byte生成を確認しているが、非Latinの公開精度値はない。

公開cardの「image-to-text onlyでpromptは無視」という説明を通常文`Extract the text`で
実行すると、日本語ページは`<<<<`反復になった。同梱の元実装とgolden試験が使う
`</s><s><predict_bbox><predict_classes><output_markdown><predict_no_text_in_pic>`を
明示すると、合成golden画像ではbbox・class付き構造出力に復帰した。したがって実運用上は
promptが無視されると見なさない。

同task tokenでJSSODa `000006`を実行すると、MLX-VLM 0.6.15および移植merge
`8683ec195f57118e52674a5b97080f63db928b65`の両方で、BPE streaming detokenizerが日本語
token `キ`をbyte mapで引き`KeyError`となった。`NaiveStreamingDetokenizer`へ隔離した
評価経路だけを切り替えるとdecodeは完走したが、実文は少数の誤認断片後に同一文節を
4,096 token上限まで反復した。42.40秒、process最大RSS約2.20GB、peak footprint約41.66GB、
swap 0である。これは64GB unified memory不足ではなく、日本語縦書きの生成品質と
runtime表示層の両方の不適合である。反復停止processorは幻覚を隠すため採用値へ使わず、
固定5枚の残り4枚と79枚は実行しない。

## 21. 2026-08-23: Qianfan-OCR MLXを次候補に固定

[Baidu公式model card](https://huggingface.co/baidu/Qianfan-OCR)は4B-parameterのend-to-end文書VLMと説明し、
配布safetensors metadataは4,741,408,256 parameter（Hugging Face表示は5B）である。
192言語、Apache-2.0、`do_sample=False`の基本経路を示す。CCOCR multilingual等の汎用公開値はあるが、
日本語縦書き小説のCER・列読順・生成反復を分離した値はない。公式推論はBF16 Transformersまたは
vLLMを基準とし、Apple Silicon MLXの正しさまでは保証しない。

[コミュニティMLX 4bit変換](https://huggingface.co/jason1966/Qianfan-OCR-MLX-4bit) revision
`125a392cc25e8750f427c7e09b5a517f07bbf70c`は約2.9GBで、変換cardは約4.7GB peak memoryと
2倍の生成速度、OCR精度維持を報告する。ただし検証例は英語・中国語・複雑layout等で、日本語縦書きの
数値はない。configに`base_model` revisionがなく、元Baidu重みの厳密なcommitは復元できないため、
変換版自体を固定して本プロジェクトのJSSODa gateで判定する。

同梱custom Python 5本はSHA-256を保存し、ネットワーク、subprocess、任意コード評価、ファイル削除・
書込みの呼出しがないことを実行前に静的確認した。初回はMLX-VLM 0.6.15、公式基準prompt
`Parse this document to Markdown.`、temperature 0、最大4,096 token、raw出力無加工とする。
Layout-as-Thoughtや反復抑制を先に追加せず、固定5枚の総合CER 0.5%以下・最大2%未満・列欠落と
反復0を満たした場合だけ79枚へ進む。

実測では`000006`がCER 2.0270%で最大gateを超え、`000142`は列読順を入れ替えた後に同一文節を
反復し、7,321正規化文字・CER 753.8883%となった。2枚目保存後、3枚目の推論途中でfail-fast停止し、
残り3枚と79枚は実行していない。停止まで107.83秒、process最大RSS 3,773,054,976 byte、peak
footprint 7,409,799,056 byte、swap 0であり、64GB unified memory不足ではない。専用CLIはraw出力を
fsync保存し、custom Pythonもmodel fingerprintへ含める。固定revisionは本番候補から外し、
反復penalty・文字列切出し・Layout-as-Thoughtによる同一候補の救済は行わない。

## 22. 2026-08-23: HunyuanOCR 1.5 BF16 llama.cpp診断

[Tencent公式model card](https://huggingface.co/tencent/HunyuanOCR)は1B級HunyuanOCR 1.5、
最大4K画像・128K context、llama.cppによるPC配備、temperature 0・top_p 1・top_k無効・
repetition penalty 1.08の共通生成条件を示す。調査時revisionは
`449e7d471a8a1ef5bd5d652e4881183d7252cbc7`、licenseはTencent Hunyuan Community Licenseである。
日本語縦書き小説のCER・段落重複率は公開していない。

[BF16 GGUF派生](https://huggingface.co/prithivMLmods/HunyuanOCR-1.5-GGUF-Updated) revision
`9ddd3b47beb0de305ecd89a717748bac080d7aee`から、BF16本体1.0GBとprojector 951MBだけを取得した。
SHA-256は本体`489dc42338cac27b1d93b7f503b5df65d8e829dd33b43bad94227d929d8a4541`、
projector`2c9c459f68a9a3c221b1a8088d9c91ac1007ef22aa89045108d14d949f9a3994`である。
派生metadataのApache-2.0表記は元licenseを上書きする根拠とせず、元Tencent revisionも埋め込まれて
いないため、このGGUF pair自体を独立候補として扱った。

llama.cpp build`b10360-48d22e295`、公式中国語文書解析prompt、最大4,096 tokenで固定2枚を実行した。
llama-cli出力fileの固定`User:` / `Assistant:` framingだけをprotocolとして分離し、assistant本文へは
後処理していない。`000006`はCER 0.3378%で通過したが、`000142`は段落の二重出力と順序入替により
CER 13.0340%、2枚総合8.0399%となった。2枚目14.57秒、最大RSS 15,393,259,520 byte、peak
footprint 14,257,417,832 byte、swap 0である。64GB不足ではなく列読順・重複品質の不合格とし、
残り3枚と79枚を実行しない。段落dedupe・順序補正・再promptで採用値を救済しない。

## 23. 2026-08-23: Hayai OCR v2とhonmono-ocrの実行前screening

[Hayai OCR v2公式model card](https://huggingface.co/JustANormalTinkerer/hayai-ocr-v2)の固定revision
`fa1ca12bacba3ac09a9fee09c6086ef84c72d8f4`はApache-2.0、約0.2B parameter、F32重み
622,500,080 byteである。SigLIP2 NaFlexをnative aspect ratioで使い、別text detectorなしで全画像を
256 patchへ変換し、独自12層causal decoderがgreedy生成する。custom codeの生成loopはEOSまたは指定token
上限まで継続し、公式例は128 token、repetition penalty 1.20である。

公式finetuningは約2,000件の漫画cropで、公開dataset viewerのtranscription長は最大81文字、公式平均CERは
8.52%である。したがって小説全ページへの適合を公開値から推定せず、1,024 tokenへ出力budgetだけを広げた
固定`000006`のfail-fast診断に限定した。`trust_remote_code=True`が必要なので固定2ファイルを事前監査し、
ネットワーク送信、subprocess、任意コード評価、ファイル削除・書込みがないことを確認した。

Transformers 5.12.0、PyTorch 2.13.0、MPS、公式repetition penalty 1.20、最大1,024 tokenで、
画像SHA-256 `c7914c0ae3cb15fc2948a1eb78c6061b5bce0ff8af88de377d71902fc8938e10`を評価した。
592正規化文字に対し予測は「「Incle」の」の8文字、Levenshtein距離589、CER 99.4932%だった。
2.30秒、process最大RSS 1,710,555,136 byte、MPS driver allocation最大観測1,552,662,528 byteであり、
64GB unified memory不足ではない。全文coverageと最大CER gateに不合格のため残り4枚・79枚へ進めず、
短文crop化や回転、patch数変更で同一候補を救済しない。

[honmono-ocr test set](https://huggingface.co/datasets/eridgd/honmono-ocr-test)は14,256件の実画像行を公開し、
縦書きcropを90度回転した入力、v6-smallの完全行一致83.5%を報告する。以前の404状態からdataset cardと
benchmarkは公開されたが、2026-08-23時点でもモデルAPIは401、参照GitHubは404で取得不能だった。また
行認識器単体であり、Kindle/JSSODa全ページにはtext detection、縦横判定、crop回転、列読順復元が別途必要である。
そのため再現可能なモデル配布とページpipelineが揃うまでB-35の直接候補へ数えない。

## 24. 2026-08-23: Qwen3.5-OCR-JP-2Bの固定5枚screening

[Qwen3.5-OCR-JP-2B model card](https://huggingface.co/ebinan92/Qwen3.5-ocr-jp-2b)の固定revision
`dc58acc05962cb2ca129c8d3533ab7e5a651cc02`はApache-2.0、BF16 2,782,629,184 parameterで、
追加custom Pythonを持たない標準Qwen3.5 checkpointである。日本語縦書き、手書き、HTML5 rubyを学習重点とし、
VJRODa 92/100件でCER 7.3%、JaWildTextでCER 6.33%を報告する。いずれもJSSODa小説ページの
0.5%・最大2.0% gateを保証しない。

公式契約はprompt `OCR this image as HTML layout blocks with bbox and label.`、greedy生成、最大8,000 token、
HTML layout block出力である。採用値はraw HTMLからDOM順の可視文字を取り出し、rubyの読み`rt`だけを除外する。
tag・attribute・単一code fence除去以外の並べ替え、dedupe、言語補正は行わない。Transformers 5.12.0、
PyTorch 2.13.0、MPS BF16で固定5枚を評価した。任意高速化のFLA・causal-convは未導入で、標準PyTorch実装へ
fallbackした。これは計算経路の低速化であり、生成条件は変更しない。

| page | 正解文字 | 予測文字 | 距離 | CER | 推論秒 |
|---|---:|---:|---:|---:|---:|
| `000006` | 592 | 591 | 1 | 0.1689% | 25.33 |
| `000142` | 913 | 913 | 0 | 0% | 35.94 |
| `000158` | 724 | 724 | 5 | 0.6906% | 26.78 |
| `000609` | 668 | 668 | 1 | 0.1497% | 27.12 |
| `001751` | 756 | 13,190 | 12,566 | 1,662.1693% | 354.29 |

先頭4枚は距離7/2,897文字・CER 0.2416%で、ページ最大も0.6907%だった。`001751`だけは
「過去を受け入れ、現在を慈しみ…」を最大8,000 tokenまで反復し、固定5枚単体総合を
距離12,573/3,653文字・CER 344.1829%へ悪化させた。最初のmodel loadを含むprocess最大RSSは
3,408,150,528 byte、MPS driver allocation最大観測は6,069,567,488 byteで、OS swapは事前値から
増加しなかった。Qwen単体は64GB不足ではなく生成停止品質で不採用とする。

既存production guard `has_suspicious_repetition`は保存した抽出本文に対して正常4枚をfalse、`001751`だけを
trueと判定した。同ページのraw HTMLは最大token到達で末尾tagも未閉鎖だった。rawを修復せず切断flagを保存し、
反復または末尾切断ならdots.mocr、それ以外はQwenへ切り替える。過去のdots固定5枚は
総合CER 0.4654%、ページ最大0.6614%なので、756文字の`001751`の距離は整数で5以下である。Qwen正常4枚の
距離7と合成すると総距離12以下、複合総合CER 0.3285%以下、ページ最大0.6907%以下となる。これは過去集計からの
数学的上界であり、欠落したdots raw予測の再計測ではない。固定79枚では両候補のrevision・fingerprint・raw出力・
選択理由を保存し、正解本文をselectorへ渡さず同じ規則を使う。

## 25. 2026-08-23: Qwen3.5 OCR複合候補を15/79枚でfail-fast

Qwen runnerはモデル重みだけでなく`chat_template.jinja`、processor、tokenizer、generation configを含む
fingerprint `40b08aa62b9673615a8b29c9104b9ea66ef2c25bc482126a3b7a24042957d392`を固定した。
JSSODa metadata SHA-256は`b521ff3f57fc044d4e92faa76cb32ebf8cfc5669ede6059c9187cb73b33cc2b9`、
先頭79縦書きページ順リストは`4b66fbdf1778261a7f7429fcfbea085cf281de411c3ec619373da7ca6058f176`である。
先頭`000006`の再実行は距離1/592文字・CER 0.1689%となり、実行前screeningと一致した。

Transformers 5.12.0、PyTorch 2.13.0、torchvision 0.28.0、MPS BF16、公式prompt、greedy、最大8,000
tokenで15枚まで実行した。反復・HTML切断は0枚だったが、総編集距離53/10,259文字、総合CER 0.5166%、
ページ最大は`000260`の14/451文字・3.1042%だった。次点は`000533`の1.3994%、`000228`の0.9115%である。

`000260`は縦書き中の半角`AI`を5箇所とも「と」と出力したほか、「もたらす」を「もたもらで」とするなど、
生成loopではない通常認識誤りだった。したがって反復・HTML切断だけをcandidate-only signalとする複合selectorは
同ページでQwenを選び、既定の総合0.5%未満・ページ最大2.0%未満を満たせない。参照正解を見た`AI`文字列、
ページID、CERでfallbackを増やすのはoracle化になるため行わず、残り64枚を停止した。

公式model cardはvLLMを推奨しつつTransformers経路も提示するが、Apple SiliconではvLLM CUDA経路をそのまま
比較できない。公開情報上はQwen3.5 visionをMLX-VLMが扱えるものの、このOCR fine-tuneの同一revision変換と
JSSODa精度保証はない。まず同一MPS条件の再現性を確認し、固定誤りならruntime切替だけを採用理由にしない。

追加2回のMPS再実行は本文SHA-256
`6eee7d4b63a560341efc13b8a21b0d272c7e67adc089a71e4bbdb9ad095dcd6d`、raw HTML SHA-256
`a67111f79249d62ee335b9fcc298d097effcb3f686f82c5aae9591da7f87f648`まで初回と一致した。
MLX-VLM 0.6.15で同じsourceをBF16変換した重みSHA-256は
`f50dfa3f0004de672da7c60716fa061876f47abf256259865aa799435b0456b0`で、同ページは距離14・CER 3.1042%、
反復・切断なしだった。最終句には小差があるが`AI`5箇所の誤認は同じで、runtime切替による救済根拠はない。

raw HTMLを比較すると、先頭15枚で`000260`だけが`<i>`を4箇所出力し、いずれも`AI`誤認を含む箇所だった。
正解を見て`<i>`本文を`AI`へ置換せず、本番plain text契約で保持しないinline装飾tagがあるページ全体を
dots.mocrへ送るcandidate-only診断は可能である。ただし公開screeningを見て追加した規則なので、同じ79枚を
最初から再評価する調整版に限り、正式holdoutの実績とは分離する。

dots.mocr固定revision`e539fbb52280393adc081b289ec597430a0f9031`をMLX-VLM 0.6.15でBF16変換した。
変換shard SHA-256は`ee5b6805e6daed399a12e05809fa6f9d6d50e28fc59bdfc365c8c3b68bbb4a11`と
`ea920fcabc7a3777b00854eff0a07126adc0acc4d05aabc51ef754a7fe302201`、runner fingerprintは
`0722d321dfef111c6329633ba8d3f36630bdf36f6915499003f799876d29fc51`である。既存最良の公式layout
prompt、temperature 0.1、top-p 1.0、seed 0、最大2,048 tokenで`000260`を5.65秒で処理した。

dots出力は`AI`5箇所をすべて「は」と誤認し、距離10/451文字・CER 2.2173%だった。v2 selectorは15枚中
この1枚だけをdotsへ切り替え、総合を距離49/10,259文字・CER 0.4776%へ改善したが、ページ最大2.2173%で
2.0%未満gateに不合格である。Qwenの「と」とdotsの「は」の不一致は誤り検出には使えても正解文字を決められず、
参照正解や言語補正を使うとoracle化する。そのため残り64枚を再実行せず、複合v2も不採用とする。

## 26. 2026-08-23: Qwen＋dotsレビュー版の79枚完走と正式候補化

自動公開候補のfail-fast終了後、ADR-0022の全ページレビューlaneを評価する目的で、同じ開封済み
JSSODa先頭79縦書きページをQwenとdotsの両方で完走した。Qwenは4/79枚（`000868`、`000967`、
`001444`、`001751`）が8,000 tokenまで反復してHTML末尾も切断され、単体は総編集距離
57,194/54,504文字、加重CER 104.9354%、最大2,864.1791%だった。反復4枚を除いた75枚でも
距離662/51,373文字・CER 1.2886%、最大33.3333%であり、単体採用はできない。

dots.mocrは同じ79枚で反復0、距離490/54,504文字、加重CER 0.8990%、最大4.0155%だった。
Qwenの反復・HTML切断4枚、非保持`<i>` markup 1枚、隣接する狭い縦列blockの左→右出力1枚、
dotsが30文字・2%以上長い欠落疑い1枚をdotsへ切り替えたレビュー版は、Qwen 72枚・dots 7枚、
距離223/54,504文字、加重CER 0.4091%、最大2.8835%、完全一致20/79枚となった。総合0.5%未満は
満たすが最大2.0%未満には届かないため、機械gate合格・自動公開・レビュー縮小には使わない。

欠落ページ`000653`はQwen 496文字・CER 33.3333%に対しdots 750文字・CER 0.6720%で、文字量差signalが
有効だった。読順崩壊ページ`000724`はQwen CER 25.2513%に対しdots 0.1256%だった。一方、最初のbbox判定は
正常に近い`000228`と`000905`も拾ったため、隣接block、各幅300以下、上下端差25以下へ限定した。これにより
79枚では`000724`だけを検出した。選択はレビュー開始時の初期候補であり、両raw本文を保持して原画像照合する。
各候補内でmodel revision・fingerprint・promptが全ページ同一でない入力もfail closedで拒否する。

[Qwen公式card](https://huggingface.co/ebinan92/Qwen3.5-ocr-jp-2b)の固定prompt、BF16、Transformers
`do_sample=False`、最大8,000 tokenを維持した。公式はvLLMを推奨するがApple Siliconで同じCUDA経路は使えない。
[MLX-VLMの別OCRモデル反復報告](https://github.com/Blaizzy/mlx-vlm/issues/1021)では
`repetition_penalty`でもloopを防げなかったため、penaltyで出力を救済せず反復guardと独立候補へ隔離する。
[dots公式layout prompt](https://github.com/studio-dots-ai/dots.mocr)を使い、MLX-VLM 0.6.15、BF16、
temperature 0.1、top-p 1.0、最大2,048 tokenを固定した。
[コミュニティの文書OCR実測](https://www.reddit.com/r/LocalLLaMA/comments/1s6cmll/testing_qwen_35_for_ocr_and_redaction_tasks/)でも
VLMが行や段落を落とす場合があり、独立OCRとのhybridと人手確認が推奨されている。

Qwen前処理のpixel budgetを根拠に低解像度ページを2〜4倍へ拡大した診断では、`000260`はCER 3.1042%から
2.4390%へ改善したが、`000158`は0.6906%から3.1768%、`000314`は0.7772%から2.4611%へ悪化し、
`000533`は長大生成へ入った。入力の一律拡大は採用せず、固定元画像を既定にする。79枚のモデル生成時間は
Qwen 3,179.58秒（中央値25.29秒、最大347.36秒）、dots 1,016.64秒（中央値12.80秒、最大22.20秒）、
合計4,196.22秒、約53.1秒/ページだった。実書籍の画像条件・文字量・反復率では増減する。

以上から、レビュー前提の正式候補はQwen主候補＋全ページdots副候補とする。残存最大誤り`000713`は
Qwen 2.8835%、dots 3.1142%で両方が2%を超え、自動候補選択では解決できない。全ページQAと
narrative全ページの原画像照合・補正を公開条件にする判断は維持する。この79枚はsignal調整に使った
公開screeningであり、未調整holdoutの性能とは報告しない。

## 27. 2026-08-23: Qwen＋dotsレビュー版の実書籍57画面pilot

rollback用canonicalがある最小の正式小説57画面を隔離DBへ複製し、`qwen35_dots_review_v1`を
Apple Silicon 64GBで実行した。両modelは同時常駐させず、Qwen全画面、process終了、dots全画面、
process終了、selectorの順に処理した。候補生成時間の合計はQwen 3,618.87秒（中央値72.10秒、最大85.23秒）、
dots 2,541.27秒（中央値46.57秒、最大67.03秒）、合計6,160.14秒（約102分40秒、108.07秒/画面）だった。

57画面すべてで両候補・raw・provenanceを揃えた後にDBへ保存し、Qwen 42画面、dots 15画面を初期候補に
選んだ。内訳はQwen clean 41、非保持`h2` 5、画像のみ4、dotsの方が明確に長い3、bbox読順疑い1、
Qwen候補解析失敗1、Qwen反復1、dots候補解析失敗1である。Qwenは挿絵系5画面でHTML本文blockを
抽出できず、dotsは4画面を`Picture`のみと判定した。dotsの画面19は2,048 tokenでlayout JSON文字列が
途中切れしたため、rawと`candidate_error`を保存して非反復のQwen候補を残した。

画面19を原画像と照合すると、原文「王国史上最悪」がQwen候補では「王国史上最 worst」となっていた。
これは候補形式・反復・文字量差の機械signalでは検出できない自然文中の誤認であり、review laneでも
全narrative画面の原画像照合を省略できない実例である。既存canonicalとの差は全体4.0275%だったが、
canonicalはverified ground truthではないため品質値として扱わず、確認順序を決める診断signalに限定する。

run 184は57/57画面を`required`として`awaiting_qa`へ遷移し、canonical本文・FTSは未変更である。
優先確認対象は、候補切替・候補エラー・分類未確定または既存本文との差が大きい
画面1〜8、11、17〜21、26、33〜34、36、41、47、50、52、57の23画面とする。残り34画面も
当初は公開前の原画像照合対象としていた。

プロジェクトオーナーは画面2・5・7・8・12を画面上で承認し、追加で画面1・3・4・6・18〜21・26・34・
47・50・52・57を原画像照合した。dotsへ切り替わった全15画面、候補解析失敗、反復、画像のみ、分類未確定、
clean本文標本を含む計19画面で、重大な欠落・読順崩壊は認めなかった。画面3は挿絵内の台詞で検索本文ではなく、
画面1・4は表紙、画面6は中央配置のヘルマン・ヘッセ引用、画面19は「最 worst」を「最悪」へ補正可能と確認した。
全件目視の負担を踏まえ、残るclean通常本文は非空・非反復・候補完全性・文字量差・provenance・画像SHAを
再監査し、根拠付きで機械支援承認する。これは個人利用のreview laneに限り、自動公開への昇格ではない。

残ページの候補差分を既存canonicalと突き合わせ、差が大きい画面11・13・17・22・33・36・41を追加で
原画像監査した。画面11は「自然とフィーネは…慕うようになった」とキノコの台詞が各2回重複、画面13は
「私がしたかっただけ」が「私がしたっただけ」、画面36は「でも、僕は君に自分のことを優先してほしくて」と
「信じられると思えたのはなぜなのか」の2文がQwen候補から欠落していた。画面17・22・33・41はQwen候補を
維持できると判定した。画面11・13・19・36は原画像で確定した箇所だけを補正文へ反映し、推測補完は行わない。

全57画面の承認内訳は、プロジェクトオーナー確認19画面、追加のCodex原画像監査7画面、clean通常本文の
機械支援監査31画面である。画面11・13・19・36は`selected_engine=codex`の補正文、画面1・4は
image-only、画面6は本文／全幅本文として確定した。selector replay、artifactとDBの候補一致、57画像の
SHA一致、選択本文の反復0件を再検証してから公開した。

隔離DBでrun 184を公開するとcanonicalは57画面・42,903文字となり、全ページで公開本文と選択／補正文、
FTSが一致した。公開前Online Backup
`20260823T105530.007192Z-publish-run-184-b4ab82ec2dc7`は389,599,232 bytesで、manifestと復元DBの
`integrity_check=ok`を確認した。続けて旧run 76へrollbackし、canonical本文・文字数・page分類・索引可否と
FTS digest `1862ed0db66d072315b7af52d5421a69b007ccd7951d2160da26f4462539bcce`が公開前と一致した。
rollback前backup `20260823T105642.543933Z-rollback-run-76-4773195e9bcb`は390,479,872 bytesで、
同じ完全性検査に合格した。

最初の監査ではcanonical行全体のdigest一致を成功条件にしたため不一致となったが、差分は57画面すべての
`image_path`だけだった。旧runはWindows絶対パスを持ち、rollback処理は検証済みの現在Mac入力パスへ
再基準化していた。現在画像は57/57件で存在し、run 76の入力SHAと一致する。`ocr_done_at`もrollback時刻へ
更新される。したがってこれはrollback失敗ではなく、監査条件が本文・分類・索引復元と環境依存pathを
混同していた問題である。本番DB SHA-256
`2cd38925f6e9eebb36d90a5bdc3d0b1f27ef846dae22ac0e6e0786053c03ec66`は一連の試験前後で不変だった。

## 28. 2026-08-23: Codex-reviewed packageの隔離往復

人手QAを通常運用から外す決定に伴い、run 184のレビュー済み成果をMac隔離DBからLinux本番へ安全に渡す
`codex-reviewed-ocr-package-v1`を実装した。packageは57画面の画像SHA、Qwen／dots双方のrawと固定
model revision・engine version・prompt ID・prompt SHA、選択理由、分類、補正文、レビュー方法を保持する。
package digestは転送事故の検出用checksumであり署名ではないため、信頼済みSSH/SCP経路を前提とする。

実測packageは1,276,317 bytes、digest
`cc63d0e21ac7aed4d24772c4cdfcbb3d09744e5ec01851a760698b906ae0d25e`だった。レビュー方法は所有者原画像確認19、
機械監査31、Codex原画像確認7、補正は画面11・13・19・36である。SQLite Online Backupで作った一時DBへ
初回57件をstagingし、同じpackageの再importは同一runの57件すべてを冪等判定した。import前後のcanonical
digestは`76e65d4b9cf648edc6680a34f6ef212bd3041faebdaf0ce3e3563251e433c67d`で変化しなかった。

既存公開処理を別操作で実行すると、57画面すべての本文・分類がpackageと一致し、FTS不一致は0件だった。
旧active run 76へrollbackするとcanonical digestも完全復元した。publish／rollback前に各1世代作成したbackupは
manifest SHA一致・復元DB `integrity_check=ok`、最終DBも`integrity_check=ok`だった。これにより、重いMac
runtimeを本番へ配備せず、stagingと公開を分離したままCodexが1冊単位で反映できる。本番DBは変更していない。
