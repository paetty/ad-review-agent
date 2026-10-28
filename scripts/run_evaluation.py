"""The same four datasets and engine used by the evaluation-center UI."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.service import init_db
from app.evaluation_center import Selection,RunRequest,preview,reserve_run,execute_run,get_run

async def main(args):
    init_db()
    selection=Selection(dataset=args.dataset,mode=args.mode)
    plan=preview(selection)
    print(json.dumps(plan,ensure_ascii=False,indent=2))
    if args.preview:return
    if args.mode=="provider" and not args.allow_provider:
        raise SystemExit("真实模型需要显式--allow-provider；请先--preview确认调用数量。")
    request=RunRequest(**selection.model_dump(),dataset_sha256=plan["dataset"]["sha256"],confirm_provider=args.allow_provider)
    run_id,rows,snapshot,prompt=reserve_run(request)
    await execute_run(run_id,rows,snapshot,prompt)
    result=get_run(run_id)
    folder=ROOT/"output/evaluation"
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f"run-{run_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"run_id":run_id,"status":result["status"],"metrics":result.get("metrics"),"report":str(target)},ensure_ascii=False,indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",choices=["development","validation","supplement","legacy"],default="development")
    parser.add_argument("--mode",choices=["rules","provider"],default="rules")
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--allow-provider",action="store_true")
    asyncio.run(main(parser.parse_args()))
