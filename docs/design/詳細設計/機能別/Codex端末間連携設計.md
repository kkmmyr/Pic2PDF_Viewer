# Codex端末間連携設計

> status: living | last-verified: 2026-08-29

MacとWindowsで動くCodexが、コピー＆ペーストを介さずに作業依頼・回答・OCR比較文脈を
共有するためのMCPサービスを定義する。本サービスはmedaroserverを中継点とする
非同期メールボックスであり、Codex同士を直接接続しない。

<!-- contract-owner: codex-coordination -->

## 1. 目的と境界

```text
Mac Codex ─────┐
               ├─ Streamable HTTP MCP ─ medaroserver ─ coordination.db
Windows Codex ─┘
```

- MacとWindowsは同じMCP URLへ接続し、送信・一覧・返信・確認をツールとして実行する。
- メッセージの正本は専用SQLiteとし、`novel.db`、OCR staging、公開本文へ直接書き込まない。
- MCPサービスは停止中のCodexを起動しない。受信側は起動時または定期タスクで未読を取得する。
- OCRジョブのclaim、run作成、QA承認、公開は既存OCR契約の責務であり、本サービスは代行しない。
- メッセージには本文そのものを大量複写せず、run ID、page番号、SHA-256、成果物path等の参照を渡す。

## 2. 公開ツール

| ツール | 種別 | 契約 |
|---|---|---|
| `send_message` | write | 宛先へ新規メッセージを送り、topicを新規作成または再利用する。`idempotency_key`指定時は同一送信者内で再送を重複登録しない |
| `list_messages` | read | 指定recipient宛てのメッセージを、状態・topicで絞り込み、新しい順に返す |
| `get_message` | read | message IDで単一メッセージを返す |
| `ack_message` | write | recipient本人のagent IDが未読メッセージを確認済みにする。同じagentによる再実行は成功扱い |
| `reply_message` | write | 元メッセージと同じtopicで送信元へ返信する。返信者は元メッセージのrecipientと一致させる |
| `close_topic` | write | topic参加者が解決内容を記録してcloseする。同一内容の再実行は成功扱い |
| `get_comparison_context` | read | 比較コーディネーターが登録した`comparison_group_id`の固定文脈を返す。未登録時は`found=false` |

MCPのserver instructionsには、agent IDとして`mac-codex` / `windows-codex`を使うこと、
受領時に`ack_message`、回答時に`reply_message`を使うこと、公開操作を行わないことを記載する。

## 3. SQLiteスキーマ

物理ファイルは`CODEX_COORDINATION_DB_PATH`で指定し、既定は
`backend/data/codex_coordination.db`とする。起動時に存在しなければ以下を作成する。

### `topics`

| 列 | 内容 |
|---|---|
| `id` | UUID文字列、primary key |
| `subject` | topic表示名 |
| `state` | `open` / `closed` |
| `created_at` / `closed_at` | UTC ISO 8601 |
| `closed_by` / `resolution` | closeしたagentと解決内容 |

### `messages`

| 列 | 内容 |
|---|---|
| `id` | UUID文字列、primary key |
| `topic_id` | `topics.id`への外部キー |
| `sender` / `recipient` | agent ID |
| `body` | メッセージ本文 |
| `refs_json` | 小さいJSON object。run ID、page番号、SHA等の参照 |
| `reply_to_id` | 返信元message ID、nullable |
| `status` | `unread` / `acknowledged` |
| `created_at` / `acknowledged_at` | UTC ISO 8601 |
| `acknowledged_by` | 確認したagent ID |
| `idempotency_key` | sender内で一意な任意キー |

### `comparison_contexts`

| 列 | 内容 |
|---|---|
| `comparison_group_id` | 比較グループ識別子、primary key |
| `context_json` | campaign種別、member run、画像manifest SHA、差分要約等 |
| `context_sha256` | canonical JSONのSHA-256 |
| `updated_at` | UTC ISO 8601 |

`comparison_contexts`への書き込みはMCPツールとして公開しない。将来のOCR比較コーディネーターが
同一process内のstore APIまたは専用import経路から登録し、Codex側は読み取りだけを行う。

## 4. 検証と失敗時契約

- agent、topic、comparison IDは英数字、`.`、`_`、`-`、`:`に限定する。
- 本文、subject、resolution、idempotency key、refs JSONには上限を設け、巨大なOCR本文を拒否する。
- `refs`はJSON objectだけを受け付け、canonical JSONで保存する。
- SQLiteはforeign key、WAL、busy timeoutを有効にし、各tool callで短いtransactionを使う。
- topicがclosedの場合、新規送信・返信を拒否する。
- message不存在、宛先不一致、返信者不一致はfail closedとし、他messageを変更しない。
- `idempotency_key`再送では最初のmessageを返し、本文や宛先が異なる場合は競合として拒否する。
- 比較文脈のSHAが保存値と一致しない場合は破損として返さない。

## 5. 配置・接続

MCP processは`backend/codex_coordination_mcp.py`を
`streamable-http` transportで起動する。既定は`127.0.0.1:8790/mcp`で、Linuxではnginxの
`/mcp`からのみproxyする。Mac/WindowsのCodexはTailscale内の
`http://medaroserver:8090/mcp`を登録する。

設定:

| 環境変数 | 既定 | 用途 |
|---|---|---|
| `CODEX_COORDINATION_DB_PATH` | `backend/data/codex_coordination.db` | 専用SQLite |
| `CODEX_COORDINATION_HOST` | `127.0.0.1` | MCP listen address |
| `CODEX_COORDINATION_PORT` | `8790` | MCP listen port |
| `CODEX_COORDINATION_LOG_LEVEL` | `INFO` | MCP runtime log level |

初期段階はTailscale到達範囲とlocalhost proxyを信頼境界とする。agent IDは監査用であり、
強い本人認証ではない。共有bearer tokenまたは端末別認証を導入する場合も、本文schemaや
message IDを変更せずtransport境界だけを強化する。

## 6. 受入条件

1. Macから送信し、Windows recipientの未読一覧だけに現れる。
2. ackとreplyを再実行しても重複や不正な状態遷移が起きない。
3. sender内の同一idempotency keyは1件だけを保存する。
4. 別agentによるack・replyとclosed topicへの送信を拒否する。
5. comparison contextのcanonical SHAを検証して返す。
6. process再起動後も未読・topic・返信関係を保持する。
7. MCP clientから7ツールを列挙でき、read/write tool annotationを識別できる。
