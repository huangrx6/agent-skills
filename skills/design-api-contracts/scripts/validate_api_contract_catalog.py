#!/usr/bin/env python3
from pathlib import Path
import argparse,csv,re,sys
AUT={"true","false","partly"}; RS={"MUST","SHOULD","MAY"}; VS={"BLOCKER","MAJOR","MINOR"}; CC={"COMPATIBLE","CONDITIONAL","BREAKING"}; METHODS={"GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"}

# 变更提案模板必备章节（缺失则报错，防止评审流程关键步骤被删）
CHANGE_PROPOSAL_SECTIONS=("基本信息","兼容性评估","迁移计划","验证证据","决策")

def read(p):
    with p.open("r",encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f)
        fn=r.fieldnames
        if fn is None: fn=[]
        return fn,list(r)
def g(x,k):
    """安全读取 CSV 单元格：缺列返回空串而非 KeyError。"""
    v=x.get(k); return "" if v is None else v
def hdr(p,h,label):
    a,r=read(p); e=[] if a==h else [f"{label}表头错误: {a}"]; e+=[] if r else [f"{label}为空"]; return r,e
def rules(p):
    r,e=hdr(p,["ruleId","category","requirement","severity","automatable","evidence"],"规则目录"); seen=set()
    for i,x in enumerate(r,2):
        rid=g(x,"ruleId")
        if not rid or rid in seen: e.append(f"规则目录第{i}行 ruleId 无效")
        seen.add(rid)
        if g(x,"severity").upper() not in RS: e.append(f"规则目录第{i}行 severity 无效")
        if g(x,"automatable").lower() not in AUT: e.append(f"规则目录第{i}行 automatable 无效")
    return e
def compat(p):
    r,e=hdr(p,["changeType","location","example","defaultClassification","conditions","requiredAction"],"兼容矩阵")
    for i,x in enumerate(r,2):
        if g(x,"defaultClassification").upper() not in CC:e.append(f"兼容矩阵第{i}行分类无效")
    return e
def status(p):
    r,e=hdr(p,["operation","method","successStatus","conditionalStatus","commonClientErrors","notes"],"状态映射")
    for i,x in enumerate(r,2):
        for m in g(x,"method").split("|"):
            if m and m.upper() not in METHODS:e.append(f"状态映射第{i}行未知方法 {m}")
        for fld in ("successStatus","conditionalStatus","commonClientErrors"):
            val=g(x,fld)
            for c in val.split("|") if val else []:
                if not c.isdigit() or not 100<=int(c)<=599:e.append(f"状态映射第{i}行状态码无效 {c}")
    return e
def review(p):
    r,e=hdr(p,["checkId","category","requirement","severity","automatable","evidence"],"评审清单"); seen=set()
    for i,x in enumerate(r,2):
        cid=g(x,"checkId")
        if not cid or cid in seen: e.append(f"评审清单第{i}行 checkId 无效")
        seen.add(cid)
        if g(x,"severity").upper() not in VS: e.append(f"评审清单第{i}行 severity 无效")
        if g(x,"automatable").lower() not in AUT: e.append(f"评审清单第{i}行 automatable 无效")
    return e
def styles(p):
    r,e=hdr(p,["style","primaryUse","direction","contract","strengths","mainRisks","defaultFor"],"风格矩阵"); req={"REST_STYLE_HTTP","GRPC","GRAPHQL","SSE","WEBSOCKET","HTTP_STREAMING","EVENT_PUBSUB","WEBHOOK","JSON_RPC"}; act={g(x,"style") for x in r};
    if req-act:e.append(f"风格矩阵缺少 {sorted(req-act)}")
    return e
def openapi(p):
    t=p.read_text(encoding="utf-8"); e=[]
    for n,pat in {"OpenAPI版本":r"(?m)^openapi:\s*\d+\.\d+\.\d+\s*$","operationId":r"operationId:","Problem Details":r"application/problem\+json","幂等键":r"Idempotency-Key","并发控制":r"If-Match"}.items():
        if not re.search(pat,t):e.append(f"OpenAPI模板缺少 {n}")
    return e
def gql(p):
    t=p.read_text(encoding="utf-8"); return [f"GraphQL模板缺少 {x}" for x in ("type Query","type Mutation","ID!","OrderConnection","PageInfo") if x not in t]
def change_proposal(p):
    t=p.read_text(encoding="utf-8"); return [f"变更提案模板缺少章节 {s}" for s in CHANGE_PROPOSAL_SECTIONS if f"## {s}" not in t]
def main():
    p=argparse.ArgumentParser(); p.add_argument("rules",type=Path); p.add_argument("--compatibility",type=Path,required=True); p.add_argument("--status-map",type=Path,required=True); p.add_argument("--review",type=Path,required=True); p.add_argument("--styles",type=Path,required=True); p.add_argument("--openapi",type=Path,required=True); p.add_argument("--graphql",type=Path,required=True); p.add_argument("--change-proposal",type=Path,help="变更提案模板"); a=p.parse_args(); e=[]
    for fn,arg in ((rules,a.rules),(compat,a.compatibility),(status,a.status_map),(review,a.review),(styles,a.styles),(openapi,a.openapi),(gql,a.graphql)):e+=fn(arg)
    if a.change_proposal:e+=change_proposal(a.change_proposal)
    if e:
        [print("错误："+x,file=sys.stderr) for x in e]; return 1
    print("API 契约 Skill 校验通过。"); return 0
if __name__=="__main__": raise SystemExit(main())
