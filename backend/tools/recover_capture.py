"""撮影復旧記録の表示。writer停止後、--resumeで残る補償だけを実行。"""

import argparse

from services.kindle_catalog.capture_recovery import resume_rollback
from services.kindle_catalog.capture_recovery_record import read_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--resume", action="store_true", help="writer停止・記録確認後に補償を再開する")
    args = parser.parse_args(argv)
    if args.resume:
        resume_rollback(args.job_id)
        print(f"補償完了: {args.job_id}（job状態は変更していません）")
    else:
        print(read_record(args.job_id).model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
