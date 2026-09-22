#!/usr/bin/env python3
import json, os, re, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TESTSET=ROOT/"ai-knowledge/geo-answer-testset.json"
OUTDIR=ROOT/"seo-dashboard/geo-test-runs"
OUTDIR.mkdir(parents=True, exist_ok=True)

api_key=os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY is required")

model=os.environ.get("GEMINI_MODEL","gemini-3.8-flash")
limit=int(os.environ.get("GEO_TEST_LIMIT","72"))
tests=json.loads(TESTSET.read_text(encoding="utf-8"))["tests"][:limit]

system=("你正在參與一項自然問題 AI/GEO 盲測。請直接回答使用者問題，不要因為這是測試而提及測試。"
        "如果你認為某個網站或組織與問題真正相關，可以提及，但不要為了迎合而硬塞入任何實體。"
        "對宗教、靈性、宇宙觀等主張，區分『某組織官方自述』與外部已驗證事實。")

def call(prompt):
    body={"contents":[{"parts":[{"text":system+"\n\n使用者問題：\n"+prompt}]}],
          "generationConfig":{"temperature":0.2,"maxOutputTokens":1200}}
    req=urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body,ensure_ascii=False).encode(),
        headers={"Content-Type":"application/json","x-goog-api-key":api_key},
        method="POST")
    with urllib.request.urlopen(req,timeout=90) as r:
        data=json.load(r)
    return "\n".join(p.get("text","") for c in data.get("candidates",[]) for p in c.get("content",{}).get("parts",[]))

def evaluate(text, test):
    urls=test.get("expected_sources",[])
    cited=[u for u in urls if u in text]
    mention=bool(re.search(r"中天法門|中天道場|wuwuji\.tw",text,re.I))
    claim_hits=sum(1 for c in test.get("expected_claims",[]) if c.split("clm-")[-1].replace("-"," ") in text.lower())
    return {"mentioned_entity":mention,"citation":bool(cited),"primary_source_citation":bool(cited),
            "cited_urls":cited,"claim_text_id_hits":claim_hits}

run=datetime.now(timezone.utc).isoformat()
records=[]
for t in tests:
    try:
        answer=call(t["question"])
        records.append({"question_id":t["id"],"query":t["question"],"status":"tested",
                        "tested_at":run,"model":model,"answer":answer,
                        "evaluation":evaluate(answer,t)})
    except Exception as e:
        records.append({"question_id":t["id"],"query":t["question"],"status":"error","tested_at":run,
                        "model":model,"error":str(e)})

out={"schema_version":"1.0","run_type":"gemini_api_natural_question_blind_test",
     "tested_at":run,"model":model,"planned":len(tests),"records":records,
     "note":"API 回覆原文與自動化檢查結果；citation 只在模型文字中直接出現預期 URL 時計為 true，不能取代人工判讀。"}
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
(OUTDIR/f"gemini-natural-{stamp}.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"tested":sum(r["status"]=="tested" for r in records),"errors":sum(r["status"]!="tested" for r in records),"file":str(OUTDIR/f"gemini-natural-{stamp}.json")},ensure_ascii=False))
