#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,time
from collections import Counter
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin,urlparse,urldefrag
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'ai-knowledge'
KNOWLEDGE=DATA/'knowledge.json'; MANIFEST=DATA/'manifest.json'
OFFICIAL_INDEX=DATA/'official'/'index.json'; FORUM_INDEX=DATA/'forum'/'index.json'
OFFICIAL='https://web.wuwuji.tw/index'; OFFICIAL_HOST='web.wuwuji.tw'
FORUM='https://www.wuwuji.tw/forum/'; FORUM_HOST='www.wuwuji.tw'
UA='Wuwuji-AI-KnowledgeBot/1.0 (+https://annynn1990.github.io/wuwujitest/)'
TIMEOUT=25; DELAY=.7; MAX_OFFICIAL=120; MAX_FORUM_INDEX=10; MAX_THREADS=150
KNOWN=['/index','/about','/cosmos','/practice','/book_adventure','/history','/seminar']
BLOCK=('home.php','member.php','mod=space','login','logout','admin','plugin.php')

def now(): return datetime.now(timezone.utc).isoformat()
def sha(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def sent(s): return [x.strip() for x in re.split(r'(?<=[。！？!?；;])\s*|(?<=[.!?])\s+(?=[A-Z0-9\u4e00-\u9fff])',clean(s)) if len(x.strip())>=12]
def summary(text,limit=900):
    ss=sent(text)
    if not ss:return ''
    if len(ss)<=3:return clean(' '.join(ss))[:limit]
    toks=re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,20}|\d{2,4}',text.lower()); f=Counter(toks)
    scored=[]
    for i,s in enumerate(ss):
        ts=re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,20}|\d{2,4}',s.lower())
        score=sum(f[t] for t in ts if f[t]>=2)+max(0,5-i)*.8+min(len(s)/100,2)
        scored.append((score,i,s))
    out=''
    for _,_,s in sorted(sorted(scored,reverse=True)[:5],key=lambda x:x[1]):
        if len(out)+len(s)+1>limit:break
        out=(out+' '+s).strip()
    return out

def keywords(text,n=12):
    stop={'中天','中天法門','一世成就','法門','網站','就是','可以','我們','你們','這個','那個','以及','如果','因為','所以','the','and','for','with','from','that','this'}
    ts=re.findall(r'[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,20}',text.lower())
    return [k for k,v in Counter(x for x in ts if x not in stop).most_common(n)]

class P(HTMLParser):
    DROP={'script','style','noscript','svg','canvas','template'}
    def __init__(self,base):
        super().__init__(); self.base=base; self.title=''; self.meta={}; self.head=[]; self.par=[]; self.links=[]; self.a=None; self.buf=[]; self.active=None; self.abuf=[]
    def handle_starttag(self,t,attrs):
        t=t.lower(); a=dict(attrs)
        if t in self.DROP:self.active=t;return
        if t=='title' or t in {'h1','h2','h3','h4'} or t=='p':self.active=t;self.buf=[]
        elif t=='a':self.a=a.get('href');self.abuf=[]
        elif t=='meta':
            k=(a.get('name') or a.get('property') or '').lower(); v=clean(a.get('content') or '')
            if k and v:self.meta[k]=v
    def handle_data(self,d):
        if self.active in {'title','h1','h2','h3','h4','p'}:self.buf.append(d)
        if self.a is not None:self.abuf.append(d)
    def handle_endtag(self,t):
        t=t.lower()
        if self.active==t and t in {'title','h1','h2','h3','h4','p'}:
            x=clean(' '.join(self.buf))
            if x:
                if t=='title':self.title=x
                elif t.startswith('h'):self.head.append({'level':int(t[1]),'text':x})
                else:self.par.append(x)
            self.active=None;self.buf=[]
        elif t=='a' and self.a is not None:
            h=self.a.strip();txt=clean(' '.join(self.abuf))
            if h and not h.startswith(('javascript:','mailto:','#')):self.links.append({'url':urldefrag(urljoin(self.base,h))[0],'text':txt[:300]})
            self.a=None;self.abuf=[]

def fetch(url):
    req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8'})
    with urlopen(req,timeout=TIMEOUT) as r:
        b=r.read(); enc=r.headers.get_content_charset() or 'utf-8'; return b.decode(enc,errors='replace')
def robots_ok(url):
    p=urlparse(url); rp=robotparser.RobotFileParser(); ru=f'{p.scheme}://{p.netloc}/robots.txt'
    try:
        txt=fetch(ru); rp.parse(txt.splitlines()); return rp.can_fetch(UA,url)
    except Exception:return True
def blocked(u):
    x=u.lower(); return any(v in x for v in BLOCK)
def parse(url,html,kind):
    p=P(url);p.feed(html); body=clean('\n'.join(p.par));
    body=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email removed]',body)
    return {'url':url,'source_type':kind,'title':p.title,'description':p.meta.get('description',''),'headings':p.head[:120],'text':body[:50000],'summary':summary(body),'keywords':keywords(body),'links':p.links[:400],'content_sha256':sha(body)}

def crawl_official():
    q=[urljoin('https://web.wuwuji.tw',x) for x in KNOWN]+[OFFICIAL]; seen=set(); docs=[]
    while q and len(docs)<MAX_OFFICIAL:
        u=urldefrag(q.pop(0))[0]
        if u in seen or urlparse(u).netloc!=OFFICIAL_HOST or blocked(u):continue
        seen.add(u)
        if not robots_ok(u):continue
        try:
            d=parse(u,fetch(u),'official');docs.append(d)
            for l in d['links']:
                v=l['url']
                if urlparse(v).netloc==OFFICIAL_HOST and v not in seen and not blocked(v) and not re.search(r'\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|mp4|mp3|css|js|ico|woff2?)$',urlparse(v).path.lower()):q.append(v)
        except Exception:pass
        time.sleep(DELAY)
    return docs

def crawl_forum():
    q=[FORUM];seen=set();idx=[];cand={}
    while q and len(idx)<MAX_FORUM_INDEX:
        u=urldefrag(q.pop(0))[0]
        if u in seen or urlparse(u).netloc!=FORUM_HOST or blocked(u):continue
        seen.add(u)
        if not robots_ok(u):continue
        try:
            d=parse(u,fetch(u),'forum_index');idx.append(d)
            for l in d['links']:
                v=l['url'];low=v.lower()
                if urlparse(v).netloc!=FORUM_HOST or blocked(v):continue
                if 'mod=viewthread' in low or ('forum.php' in low and 'tid=' in low):cand[v]=l['text']
                if 'mod=forumdisplay' in low or 'gid=' in low:
                    if v not in seen and v not in q:q.append(v)
        except Exception:pass
        time.sleep(DELAY)
    threads=[]
    for u,anchor in list(cand.items())[:MAX_THREADS]:
        if not robots_ok(u):continue
        try:
            d=parse(u,fetch(u),'forum_thread');d['anchor_text']=anchor;d['text']=d['text'][:15000];d['summary']=summary(d['text'],700);threads.append(d)
        except Exception:pass
        time.sleep(DELAY)
    return idx,threads

def load(p,default):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except Exception:return default

def merge(old,new):
    oldmap={x.get('url'):x for x in old.get('documents',[]) if x.get('url')};out=[]
    for d in new:
        o=oldmap.get(d['url']); d['first_seen_at']=o.get('first_seen_at',now()) if o else now(); d['last_changed_at']=now() if not o or o.get('content_sha256')!=d.get('content_sha256') else o.get('last_changed_at',d['first_seen_at']); d['retrieved_at']=now();out.append(d)
    return out

def main():
    DATA.mkdir(exist_ok=True);old=load(KNOWLEDGE,{})
    official=crawl_official();fi,ft=crawl_forum();docs=merge(old,official+fi+ft)
    claims=[{'subject':'中天法門','statement':d['summary'],'source_url':d['url'],'source_type':d['source_type'],'interpretation':'source_attributed'} for d in docs if d.get('summary')]
    generated=now();data={'schema_version':'2.0','dataset':'中天法門 AI / GEO 公開知識庫','entity':'中天法門','generated_at':generated,'description':'公開網站與公開論壇內容的機器可讀索引。保留來源 URL，並區分官方與論壇來源。','source_policy':{'official':'web.wuwuji.tw 公開頁面','forum':'www.wuwuji.tw/forum/ 公開頁面；論壇內容不自動等同官方立場','privacy':'不抓登入頁、後台及不必要會員個資','summary':'extractive_v1；自動抽取摘要，不是事實查核'},'stats':{'official_pages':len(official),'forum_index_pages':len(fi),'forum_threads':len(ft),'documents':len(docs),'claims':len(claims)},'sources':[{'type':'official','url':'https://web.wuwuji.tw/'},{'type':'forum','url':'https://www.wuwuji.tw/forum/'},{'type':'seminar','url':'https://annynn1990.github.io/wuwujitest/seminar-data.json'}],'documents':docs,'claims':claims,'seminars':{'url':'https://annynn1990.github.io/wuwujitest/seminar-data.json','note':'由既有說明會同步流程維護；本程式不改寫該 JSON。'}}
    KNOWLEDGE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    OFFICIAL_INDEX.write_text(json.dumps({'type':'official_index','updated_at':generated,'documents':[d for d in docs if d['source_type']=='official']},ensure_ascii=False,indent=2),encoding='utf-8')
    FORUM_INDEX.write_text(json.dumps({'type':'forum_index','updated_at':generated,'documents':[d for d in docs if d['source_type'].startswith('forum')]},ensure_ascii=False,indent=2),encoding='utf-8')
    m=load(MANIFEST,{'schema_version':'1.0','runs':[]});run={'completed_at':generated,'official_pages':len(official),'forum_index_pages':len(fi),'forum_threads':len(ft),'documents':len(docs)};m['last_run']=run;m['runs']=(m.get('runs',[])+[run])[-30:];MANIFEST.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(run,ensure_ascii=False))
if __name__=='__main__':main()
