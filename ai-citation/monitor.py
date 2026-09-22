import json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "ai-citation/prompts.json").read_text(encoding="utf-8"))
TARGET = CFG["target_site_prefix"].rstrip("/") + "/"
REPEATS = int(os.getenv("CITATION_REPEATS", CFG.get("repeats_per_prompt", 3)))
TIMEOUT = 60

def post_json(url, headers, body):
    req = Request(url, data=json.dumps(body).encode(), headers={**headers, "Content-Type":"application/json"}, method="POST")
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))

def collect_strings(x, out):
    if isinstance(x, dict):
        for v in x.values(): collect_strings(v, out)
    elif isinstance(x, list):
        for v in x: collect_strings(v, out)
    elif isinstance(x, str):
        out.append(x)

def urls_from_response(data):
    strings=[]; collect_strings(data, strings)
    urls=[]
    for s in strings:
        for u in re.findall(r'https?://[^\\s<>"\\']+', s):
            u=u.rstrip(').,;]}>')
            if u not in urls: urls.append(u)
    return urls

def target_citations(urls):
    return [u for u in urls if u.startswith(TARGET)]

def run_openai(question):
    key=os.getenv("OPENAI_API_KEY")
    if not key: return {"status":"not_configured","citations":[],"urls":[]}
    body={
      "model":os.getenv("OPENAI_MODEL","gpt-5.6-luna"),
      "tools":[{"type":"web_search"}],
      "input":question
    }
    try:
        data=post_json("https://api.openai.com/v1/responses", {"Authorization":"Bearer "+key}, body)
        urls=urls_from_response(data)
        return {"status":"ok","citations":target_citations(urls),"urls":urls}
    except Exception as e:
        return {"status":"error","error":str(e),"citations":[],"urls":[]}

def run_perplexity(question):
    key=os.getenv("PERPLEXITY_API_KEY")
    if not key: return {"status":"not_configured","citations":[],"urls":[]}
    body={
      "model":os.getenv("PERPLEXITY_MODEL","sonar"),
      "messages":[{"role":"user","content":question}]
    }
    try:
        data=post_json("https://api.perplexity.ai/chat/completions", {"Authorization":"Bearer "+key}, body)
        urls=urls_from_response(data)
        return {"status":"ok","citations":target_citations(urls),"urls":urls}
    except Exception as e:
        return {"status":"error","error":str(e),"citations":[],"urls":[]}

def main():
    providers={"openai_web_search":run_openai,"perplexity":run_perplexity}
    runs=[]; now=datetime.now(timezone.utc).isoformat()
    for p, fn in providers.items():
        for prompt in CFG["prompts"]:
            for repeat in range(1, REPEATS+1):
                result=fn(prompt["question"])
                runs.append({
                  "timestamp":now,"provider":p,"prompt_id":prompt["id"],
                  "question":prompt["question"],"repeat":repeat,
                  **result
                })
    configured=[p for p in providers if any(r["provider"]==p and r["status"]=="ok" for r in runs)]
    summary={}
    for p in providers:
        rr=[r for r in runs if r["provider"]==p]
        ok=[r for r in rr if r["status"]=="ok"]
        cited=[r for r in ok if r["citations"]]
        prompt_cited=len({r["prompt_id"] for r in cited})
        unique_urls=sorted({u for r in cited for u in r["citations"]})
        summary[p]={
          "status":"ok" if ok else ("not_configured" if all(r["status"]=="not_configured" for r in rr) else "error"),
          "runs":len(rr),"successful_runs":len(ok),
          "cited_runs":len(cited),
          "citation_rate_pct":round(len(cited)/len(ok)*100,2) if ok else None,
          "citation_probability_estimate_pct":round(len(cited)/len(ok)*100,2) if ok else None,
          "prompt_coverage_pct":round(prompt_cited/len(CFG["prompts"])*100,2) if CFG["prompts"] else 0,
          "unique_target_urls":unique_urls,
          "official_source_rate_pct":round(sum(1 for r in cited if r["citations"])/len(cited)*100,2) if cited else None
        }
    latest={"generated_at":now,"target":TARGET,"repeats_per_prompt":REPEATS,"summary":summary,"runs":runs}
    hist_dir=ROOT/"ai-citation/history"; hist_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    (ROOT/"ai-citation/latest.json").write_text(json.dumps(latest,ensure_ascii=False,indent=2),encoding="utf-8")
    (hist_dir/f"{stamp}.json").write_text(json.dumps(latest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if not configured:
        print("No AI citation provider is configured; baseline remains unmeasured.")
if __name__=="__main__": main()
