"""Opt-in importer for external research candidates; no images or participant profiles."""
import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.pii import detect_pii_text

BASE="https://raw.githubusercontent.com/eric-zeng/chi-bad-ads-data/master/"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fetch",action="store_true",help="下载公开研究元数据，不下载截图或参与者画像")
    args=parser.parse_args()
    if not args.fetch:
        print("来源：https://github.com/eric-zeng/chi-bad-ads-data；需要显式--fetch。许可证/素材再分发权尚未核实，导入仅保存在已忽略的output目录。")
        return
    metadata_raw=urllib.request.urlopen(BASE+"data/ads_all_labels.json",timeout=30).read()
    ratings_raw=urllib.request.urlopen(BASE+"data/overall_ad_ratings.csv",timeout=30).read()
    ads=json.loads(metadata_raw)
    ratings=list(csv.DictReader(io.StringIO(ratings_raw.decode("utf-8-sig"))))
    prepared=[]; filtered=0
    for idx,row in enumerate(ratings):
        feedback=(row.get("free_response") or "").strip()
        if not feedback: continue
        if detect_pii_text(feedback): filtered+=1; continue
        prepared.append({"record_id":f"CHI21-{idx:05d}","ad_id":row["ad_id"],
            "source_type":"external_research","language":"en","annotation_status":"unmapped_not_gold",
            "input":{"title":"研究广告 "+row["ad_id"],"ad_copy":"","feedback":feedback,"industry":"其他","media_scene":"其他","landing_type":"其他","material_format":"图片"},
            "gold_labels":None,"gold_risk":None,"evaluation_ready":False,
            "material_status":"截图仍在原仓库，本次未下载或分析"})
    output=ROOT/"output/public-data"
    output.mkdir(parents=True,exist_ok=True)
    (output/"feedback-candidates.jsonl").write_text("\n".join(json.dumps(row,ensure_ascii=False) for row in prepared)+"\n",encoding="utf-8")
    manifest={"source":"https://github.com/eric-zeng/chi-bad-ads-data","paper_doi":"10.1145/3411764.3445459",
        "ads":len(ads),"rating_records":len(ratings),"text_candidates":len(prepared),"pii_pattern_filtered":filtered,
        "metadata_sha256":hashlib.sha256(metadata_raw).hexdigest(),"ratings_sha256":hashlib.sha256(ratings_raw).hexdigest(),
        "license_status":"not_verified_do_not_redistribute","participant_profiles_downloaded":False,"screenshots_downloaded":False,
        "scope":"英文广告观感与可选评论，不包含本项目12标签金标、中文移动端曝光或跳转行为。缺失数据不得补写为真实值。"}
    (output/"import-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
