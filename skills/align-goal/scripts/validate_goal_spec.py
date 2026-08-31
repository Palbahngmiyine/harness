#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime
from pathlib import Path

SCHEMA="align-goal/v1"
ACTIONS=("research_facts","map_choices","ask_choices","compile_spec","run_ambiguity_audit","run_cold_consumer","resolve_findings","request_final_confirmation","complete","pause")
FM={"schema","title","target","session_status","alignment_status","handoff_status","revision","created","updated"}
TOP={"contract_version","revision","target","goal","repository_context","facts","choices","question_rounds","decision_surfaces","specifications","acceptance_checks","implementation_units","open_items","reviews","confirmations"}
ENUM={"target":{"decision","implementation"},"session_status":{"active","waiting","paused","complete"},"alignment_status":{"exploring","aligned","rejected"},"handoff_status":{"not_requested","draft","ready"}}
KIND={"behavior","error","name","format","contract","data","state","structure","dependency","compatibility","security","performance","operation","verification"}
SURFACES=("goal_success_failure_non_goal","user_behavior_defaults_order_atomicity_idempotency","errors_partial_failure_recovery_rollback","commands_flags_routes_events_config_types_fields_paths_formats","data_state_ownership_lifecycle_persistence","api_event_file_internal_contract_versioning","architecture_modules_components_dependencies_stack","concurrency_timing_resource_policy","compatibility_migration_rollout","security_privacy_authorization_destructive_side_effect","performance_observability_operation","verification_acceptance")
SOURCE_KIND={"path","url","command","runtime"}
REPO_KIND={"git_head","file","command","runtime"}
VAGUE=re.compile(r"(?:^|[^\w])(?:looks\s+good|you\s+choose|best\s+judgment|follow\s+(?:the\s+)?repo(?:sitory)?|알아서\s*해(?:줘|주세요)?)(?:$|[^\w])",re.I)
RFC=re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$")
SHA=re.compile(r"^sha256:[0-9a-f]{64}$")
PH=re.compile(r"(?:<[^>]+>|\[\s*(?:todo|tbd|placeholder|fill|결정)\s*\]|\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b)",re.I)
ASSUMPTION=re.compile(r"\b(?:assumption|assumptions|assume|assumes|assuming)\b|가정",re.I)
FENCE="\x60"*3

def dup(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError("duplicate JSON key: "+k)
        out[k]=v
    return out
def constant(x):raise ValueError("non-standard JSON constant: "+x)
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def dg(x):return "sha256:"+hashlib.sha256(canon(x)).hexdigest()
def text(x,label,e,nullable=False):
    if x is None and nullable:return
    if not isinstance(x,str) or not x.strip():e.append(label+" must be nonempty string")
def stamp(x,label,e,nullable=False):
    if x is None and nullable:return
    if not isinstance(x,str) or not RFC.fullmatch(x):e.append(label+" must be RFC3339")
def instant(x):
    try:return datetime.fromisoformat(x.replace("Z","+00:00"))
    except (TypeError,ValueError):return None
def sha(x,label,e,nullable=False):
    if x is None and nullable:return
    if not isinstance(x,str) or not SHA.fullmatch(x):e.append(label+" must be sha256:64 lowercase hex")
def strings(x,label,e,empty=True,required=False):
    if not isinstance(x,list):e.append(label+" must be array");return
    if required and not x:e.append(label+" must be nonempty array")
    for i,v in enumerate(x):
        if not isinstance(v,str) or (not empty and not v.strip()):e.append(f"{label}[{i}] must be nonempty string")
def list_value(x):return x if isinstance(x,list) else []
def dict_value(x):return x if isinstance(x,dict) else {}
def string_values(x):return [v for v in list_value(x) if isinstance(v,str)]
def exact(x,keys,label,e):
    if not isinstance(x,dict):e.append(label+" must be object");return False
    if set(x)-set(keys):e.append(label+" unexpected keys: "+", ".join(sorted(set(x)-set(keys))))
    if set(keys)-set(x):e.append(label+" missing keys: "+", ".join(sorted(set(keys)-set(x))))
    return set(x)==set(keys)
def arr(x,label,e):
    if not isinstance(x,list):e.append(label+" must be array");return []
    return x
def table(rows,prefix,label,e):
    out={}
    for i,r in enumerate(arr(rows,label,e)):
        if not isinstance(r,dict):e.append(f"{label}[{i}] must be object");continue
        ident=r.get("id")
        if not isinstance(ident,str) or not re.fullmatch(prefix+r"[0-9]+",ident):e.append(f"{label}[{i}].id must match {prefix}N")
        elif ident in out:e.append("duplicate or reused ID: "+ident)
        else:out[ident]=r
    return out
def refs(r,key,t,label,e):
    if not isinstance(r,dict):e.append(label+" must be object");return []
    v=r.get(key)
    if not isinstance(v,list):e.append(label+"."+key+" must be array");return []
    for x in v:
        if not isinstance(x,str) or x not in t:e.append(f"{label}.{key} references unknown ID {x}")
    return [x for x in v if isinstance(x,str) and x in t]

def front(text0):
    if not text0.startswith("---\n"):return {},text0,["frontmatter must start at first line"]
    end=text0.find("\n---",4)
    if end<0:return {},text0,["frontmatter closing delimiter missing"]
    out={};e=[]
    for line in text0[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):continue
        if ":" not in line:e.append("invalid frontmatter line: "+line);continue
        k,v=line.split(":",1);k=k.strip();v=v.strip().strip("'\"")
        if k in out:e.append("duplicate frontmatter key: "+k)
        out[k]=v
    return out,text0[end+4:],e
def contract(body):
    hit=list(re.finditer(r"^"+FENCE+r"json align-goal-contract\s*\n(.*?)^"+FENCE+r"\s*$",body,re.M|re.S))
    if len(hit)!=1:return None,[f"expected exactly one json align-goal-contract fence, found {len(hit)}"]
    try:x=json.loads(hit[0].group(1),object_pairs_hook=dup,parse_constant=constant)
    except (ValueError,json.JSONDecodeError) as ex:return None,["contract JSON is invalid: "+str(ex)]
    return (x,[]) if isinstance(x,dict) else (None,["contract root must be object"])

class V:
    def __init__(self,raw,f,c):
        self.raw,self.f,self.c=raw,f,c;self.e=[];self.unresolved=[];self.uncovered=[];self.untraced=[];self.unverified=[];self.orphans=[];self.cycles=[];self.stale=[]
        self.fact_invalid=False;self.context_invalid=False;self.surface_invalid=False;self.choice_invalid=False;self.compile_invalid=False;self.planner_blockers=[]
        self.F=self.C=self.S=self.A=self.U=self.O={}
    def fail(self,x):self.e.append(x)
    def front(self):
        if set(self.f)!=FM:self.fail("frontmatter keys must be exactly "+", ".join(sorted(FM)))
        if self.f.get("schema")!=SCHEMA:self.fail("frontmatter schema must be align-goal/v1")
        text(self.f.get("title"),"frontmatter.title",self.e)
        for k,vals in ENUM.items():
            if self.f.get(k) not in vals:self.fail("frontmatter."+k+" has invalid value")
        if not re.fullmatch(r"[1-9][0-9]*",str(self.f.get("revision",""))):self.fail("frontmatter.revision must be positive integer")
        stamp(self.f.get("created"),"frontmatter.created",self.e);stamp(self.f.get("updated"),"frontmatter.updated",self.e)
    def top(self):
        if set(self.c)!=TOP:
            if set(self.c)-TOP:self.fail("unexpected top-level keys: "+", ".join(sorted(set(self.c)-TOP)))
            if TOP-set(self.c):self.fail("missing top-level keys: "+", ".join(sorted(TOP-set(self.c))))
        if self.c.get("contract_version")!=SCHEMA:self.fail("contract_version must be align-goal/v1")
        if self.c.get("target")!=self.f.get("target"):self.fail("frontmatter/contract target mismatch")
        if type(self.c.get("revision")) is not int:self.fail("contract revision must be integer")
        elif re.fullmatch(r"[1-9][0-9]*",str(self.f.get("revision",""))) and self.c.get("revision")!=int(self.f.get("revision")):self.fail("frontmatter/contract revision mismatch")
        if self.f.get("target")=="decision" and self.f.get("handoff_status") in {"draft","ready"}:self.fail("decision target cannot claim handoff draft/ready")
        g=self.c.get("goal")
        if exact(g,{"statement","success","failure","non_goals"},"goal",self.e):
            text(g.get("statement"),"goal.statement",self.e)
            for k in ("success","failure","non_goals"):strings(g.get(k),"goal."+k,self.e,False,True)
    def context(self):
        start=len(self.e)
        x=self.c.get("repository_context")
        if not exact(x,{"root","captured_at","entries"},"repository_context",self.e):self.context_invalid=True;return
        text(x.get("root"),"repository_context.root",self.e);stamp(x.get("captured_at"),"repository_context.captured_at",self.e)
        entries=arr(x.get("entries"),"repository_context.entries",self.e)
        if not entries:self.context_invalid=True
        for i,r in enumerate(entries):
            l=f"repository_context.entries[{i}]"
            if exact(r,{"kind","locator","digest"},l,self.e):
                if not isinstance(r.get("kind"),str) or r.get("kind") not in REPO_KIND:self.fail(l+".kind invalid");self.context_invalid=True
                text(r.get("locator"),l+".locator",self.e);sha(r.get("digest"),l+".digest",self.e,True)
                if r.get("digest") is None:self.context_invalid=True
        if len(self.e)>start:self.context_invalid=True
    def facts(self):
        start=len(self.e);self.F=table(self.c.get("facts"),"F","facts",self.e);keys={"id","observation","sources","observed_at","stability","stability_basis","limits"}
        for i,r in self.F.items():
            l="facts."+i
            if not exact(r,keys,l,self.e):continue
            text(r.get("observation"),l+".observation",self.e);stamp(r.get("observed_at"),l+".observed_at",self.e)
            if r.get("stability") not in {"snapshot","immutable_for_scope"}:self.fail(l+".stability invalid")
            if r.get("stability")=="immutable_for_scope":text(r.get("stability_basis"),l+".stability_basis",self.e)
            elif r.get("stability_basis") is not None:self.fail(l+".stability_basis must be null for snapshot")
            text(r.get("limits"),l+".limits",self.e)
            ss=arr(r.get("sources"),l+".sources",self.e)
            if not ss:self.fail(l+".sources must be nonempty")
            for j,s in enumerate(ss):
                sl=f"{l}.sources[{j}]"
                if exact(s,{"kind","value","digest"},sl,self.e):
                    if not isinstance(s.get("kind"),str) or s.get("kind") not in SOURCE_KIND:self.fail(sl+".kind invalid")
                    text(s.get("value"),sl+".value",self.e);sha(s.get("digest"),sl+".digest",self.e,True)
                    if r.get("stability")=="immutable_for_scope" and s.get("digest") is None and not r.get("limits"):self.fail(l+" immutable basis needs nonempty limits when source digest is null")
        if len(self.e)>start:self.fact_invalid=True
    def choices(self):
        start=len(self.e);self.C=table(self.c.get("choices"),"C","choices",self.e);keys={"id","question","alternatives","recommendation","depends_on_choice_ids","choice_kind","policy_targets","user_response","confirmed_alternative_id","confirmed_value","scope","consequences","affected_spec_ids","affected_acceptance_ids","affected_unit_ids","status","supersession"}
        ak={"id","value","outcome_delta"};rk={"alternative_id","rationale","evidence_fact_ids"};sk={"exact_user_response","turn_id","confirmed_at","basis_choice_ids","basis_fact_ids","derivation"}
        for i,r in self.C.items():
            l="choices."+i
            if not exact(r,keys,l,self.e):continue
            text(r.get("question"),l+".question",self.e);als=arr(r.get("alternatives"),l+".alternatives",self.e)
            if len(als)<2:self.fail(l+".alternatives needs 2+")
            alts=set()
            for j,a in enumerate(als):
                al=f"{l}.alternatives[{j}]"
                if exact(a,ak,al,self.e):
                    aid=a.get("id")
                    text(aid,al+".id",self.e)
                    if isinstance(aid,str):
                        if aid in alts:self.fail(al+".id duplicated")
                        alts.add(aid)
                    text(a.get("value"),al+".value",self.e);text(a.get("outcome_delta"),al+".outcome_delta",self.e)
            rec=r.get("recommendation")
            if not exact(rec,rk,l+".recommendation",self.e):continue
            if not isinstance(rec.get("alternative_id"),str) or rec.get("alternative_id") not in alts:self.fail(l+".recommendation alternative unknown")
            text(rec.get("rationale"),l+".recommendation.rationale",self.e)
            if not refs(rec,"evidence_fact_ids",self.F,l+".recommendation",self.e):self.fail(l+".recommendation.evidence_fact_ids must be nonempty")
            refs(r,"depends_on_choice_ids",self.C,l,self.e);strings(r.get("policy_targets"),l+".policy_targets",self.e,False)
            if not isinstance(r.get("choice_kind"),str) or r.get("choice_kind") not in {"discrete","policy"}:self.fail(l+".choice_kind invalid")
            if r.get("choice_kind")=="policy" and not r.get("policy_targets"):self.fail(l+".policy_targets required for policy")
            pts=list_value(r.get("policy_targets"))
            if all(isinstance(x,str) for x in pts) and len(pts)!=len(set(pts)):self.fail(l+".policy_targets must be unique")
            if r.get("choice_kind")=="discrete" and r.get("policy_targets"):self.fail(l+".policy_targets must be empty for discrete")
            strings(r.get("scope"),l+".scope",self.e,False,True);strings(r.get("consequences"),l+".consequences",self.e,False,True)
            for key in ("scope","consequences","policy_targets"):
                value=r.get(key)
                if isinstance(value,list) and all(isinstance(x,str) for x in value) and len(value)!=len(set(value)):self.fail(l+"."+key+" must be unique")
            refs(r,"affected_spec_ids",self.S,l,self.e);refs(r,"affected_acceptance_ids",self.A,l,self.e);refs(r,"affected_unit_ids",self.U,l,self.e)
            st=r.get("status")
            if not isinstance(st,str) or st not in {"candidate","asked","confirmed","superseded"}:self.fail(l+".status invalid")
            if st in {"candidate","asked"}:
                if any(r.get(k) is not None for k in ("user_response","confirmed_alternative_id","confirmed_value","supersession")):self.fail(l+" candidate/asked confirmation fields must be null")
                self.unresolved.append(i)
            if st=="confirmed":
                if r.get("supersession") is not None:self.fail(l+".supersession must be null for confirmed")
                u=r.get("user_response")
                if not exact(u,{"exact","turn_id","confirmed_at"},l+".user_response",self.e):self.fail(l+".user_response required")
                else:
                    text(u.get("exact"),l+".user_response.exact",self.e);text(u.get("turn_id"),l+".user_response.turn_id",self.e,True);stamp(u.get("confirmed_at"),l+".user_response.confirmed_at",self.e,True)
                    if u.get("turn_id") is None and u.get("confirmed_at") is None:self.fail(l+".user_response needs turn_id or confirmed_at")
                selected=next((a for a in als if isinstance(a,dict) and a.get("id")==r.get("confirmed_alternative_id")),None)
                if not isinstance(r.get("confirmed_alternative_id"),str) or r.get("confirmed_alternative_id") not in alts:self.fail(l+".confirmed_alternative_id unknown")
                if r.get("confirmed_value")!=(selected or {}).get("value"):self.fail(l+".confirmed_value must equal selected alternative.value")
            if st=="superseded":
                u=r.get("user_response")
                if not exact(u,{"exact","turn_id","confirmed_at"},l+".user_response",self.e):self.fail(l+" superseded choice must preserve original user_response")
                elif not isinstance(u.get("exact"),str) or not u.get("exact").strip():self.fail(l+" superseded original exact response must be nonempty")
                else:
                    text(u.get("turn_id"),l+".user_response.turn_id",self.e,True);stamp(u.get("confirmed_at"),l+".user_response.confirmed_at",self.e,True)
                    if u.get("turn_id") is None and u.get("confirmed_at") is None:self.fail(l+" superseded original response needs turn_id or confirmed_at")
                selected=next((a for a in als if isinstance(a,dict) and a.get("id")==r.get("confirmed_alternative_id")),None)
                if not isinstance(r.get("confirmed_alternative_id"),str) or r.get("confirmed_alternative_id") not in alts:self.fail(l+" superseded confirmed_alternative_id unknown")
                if r.get("confirmed_value")!=(selected or {}).get("value"):self.fail(l+" superseded confirmed_value must equal selected alternative.value")
                s=r.get("supersession")
                if not exact(s,sk,l+".supersession",self.e):continue
                text(s.get("exact_user_response"),l+".supersession.exact_user_response",self.e);text(s.get("derivation"),l+".supersession.derivation",self.e);text(s.get("turn_id"),l+".supersession.turn_id",self.e,True);stamp(s.get("confirmed_at"),l+".supersession.confirmed_at",self.e,True)
                if s.get("turn_id") is None and s.get("confirmed_at") is None:self.fail(l+".supersession needs turn_id or confirmed_at")
                bc=refs(s,"basis_choice_ids",self.C,l+".supersession",self.e);bf=refs(s,"basis_fact_ids",self.F,l+".supersession",self.e)
                if not bc and not bf:self.fail(l+".supersession needs basis")
                if any(self.C.get(x,{}).get("status")!="confirmed" for x in bc):self.fail(l+".supersession choice basis must be confirmed")
                if any(self.F.get(x,{}).get("stability")!="immutable_for_scope" for x in bf):self.fail(l+".supersession fact basis must be immutable")
                if VAGUE.search(str(s.get("exact_user_response"))):self.fail(l+" contains vague supersession response")
            if st in {"confirmed","superseded"} and (VAGUE.search(json.dumps(r.get("user_response"),ensure_ascii=False)) or VAGUE.search(str(r.get("confirmed_value")))):self.fail(l+" contains vague response/value")
        if len(self.e)>start:self.choice_invalid=True
    def rounds(self):
        rows=arr(self.c.get("question_rounds"),"question_rounds",self.e);rounds={}
        for j,r in enumerate(rows):
            l=f"question_rounds[{j}]"
            if not exact(r,{"number","choice_ids","asked_at","checkpoint"},l,self.e):continue
            n=r.get("number");cs=refs(r,"choice_ids",self.C,l,self.e)
            if type(n) is not int or n<1:self.fail(l+".number invalid")
            if not 1<=len(cs)<=8 or len(set(cs))!=len(cs):self.fail(l+".choice_ids must be unique 1..8")
            stamp(r.get("asked_at"),l+".asked_at",self.e)
            if type(n) is int:
                if n in rounds:self.fail("duplicate round number")
                rounds[n]=r
                if n%4==0:
                    cp=r.get("checkpoint")
                    if not exact(cp,{"confirmed_choice_ids","unresolved_choice_ids","affected_spec_ids","next_question_choice_ids","recorded_at"},l+".checkpoint",self.e):self.fail(l+".checkpoint required every 4th round")
                    else:
                        for k,t in (("confirmed_choice_ids",self.C),("unresolved_choice_ids",self.C),("next_question_choice_ids",self.C),("affected_spec_ids",self.S)):refs(cp,k,t,l+".checkpoint",self.e)
                        stamp(cp.get("recorded_at"),l+".checkpoint.recorded_at",self.e)
                elif r.get("checkpoint") is not None:self.fail(l+".checkpoint must be null")
            for x in cs:
                if self.C.get(x,{}).get("status")=="candidate":self.fail(x+" candidate choice cannot be in a round")
        if rounds and set(rounds)!=set(range(1,max(rounds)+1)):self.fail("question rounds must be contiguous from 1 to N")
        for x,r in self.C.items():
            if r.get("status") in {"asked","confirmed","superseded"} and sum(x in list_value(q.get("choice_ids")) for q in rounds.values())!=1:self.fail(x+" must occur in exactly one round")
        for n,r in rounds.items():
            for x in string_values(r.get("choice_ids")):
                for d in string_values(self.C.get(x,{}).get("depends_on_choice_ids")):
                    dn=next((z for z,q in rounds.items() if d in list_value(q.get("choice_ids"))),None)
                    if dn is None or dn>=n or self.C.get(d,{}).get("status")!="confirmed":self.fail(x+" dependency must be earlier confirmed choice")
    def surfaces(self):
        start=len(self.e);rows=arr(self.c.get("decision_surfaces"),"decision_surfaces",self.e);found={}
        if len(rows)!=12:self.fail("decision_surfaces must contain exactly 12 entries")
        for j,r in enumerate(rows):
            l=f"decision_surfaces[{j}]"
            if not exact(r,{"id","name","classification","resolution","reason"},l,self.e):continue
            if not isinstance(r.get("id"),str) or not re.fullmatch(r"DS[0-9]+",r["id"]):self.fail(l+".id must match DSN")
            elif r.get("name") in SURFACES and r["id"]!="DS"+str(SURFACES.index(r["name"])+1):self.fail(l+" id/name must be exact DS1..DS12 pair")
            name=r.get("name")
            if not isinstance(name,str) or name not in SURFACES:self.fail(l+".name invalid exact surface")
            elif name in found:self.fail("duplicate decision surface name")
            else:found[name]=r
            if not isinstance(r.get("classification"),str) or r.get("classification") not in {"applicable","not_applicable"}:self.fail(l+".classification invalid")
            q=r.get("resolution")
            if exact(q,{"mode","choice_ids","fact_ids","derivation"},l+".resolution",self.e):
                cs=refs(q,"choice_ids",self.C,l+".resolution",self.e);fs=refs(q,"fact_ids",self.F,l+".resolution",self.e)
                if q.get("mode")=="choice":
                    if not cs or fs or q.get("derivation") is not None:self.fail(l+" choice resolution requires C only and null derivation")
                    if any(self.C.get(x,{}).get("status") not in {"candidate","asked","confirmed","superseded"} for x in cs):self.fail(l+" governing choice invalid")
                    if any(self.C.get(x,{}).get("status") in {"candidate","asked"} for x in cs) and isinstance(name,str):self.uncovered.append(name)
                    if any(self.C.get(x,{}).get("status")=="superseded" for x in cs):
                        self.fail(l+" superseded choice cannot govern current surface")
                        if isinstance(name,str):self.uncovered.append(name)
                elif q.get("mode")=="forced":
                    if not cs and not fs:self.fail(l+" forced resolution needs basis")
                    if any(self.C.get(x,{}).get("status")!="confirmed" for x in cs):self.fail(l+" forced choice basis must be confirmed")
                    if any(self.F.get(x,{}).get("stability")!="immutable_for_scope" for x in fs):self.fail(l+" forced fact basis must be immutable")
                    text(q.get("derivation"),l+".resolution.derivation",self.e)
                else:self.fail(l+".resolution.mode invalid")
            text(r.get("reason"),l+".reason",self.e)
        for n in SURFACES:
            if n not in found:self.uncovered.append(n);self.fail("missing decision surface "+n)
        for n in SURFACES:
            if n in found and self.f.get("alignment_status")=="aligned":
                resolution=found[n].get("resolution")
                if isinstance(resolution,dict) and any(self.C.get(x,{}).get("status")!="confirmed" for x in string_values(resolution.get("choice_ids"))):self.fail(n+" must use current confirmed C")
        if len(self.e)>start:self.surface_invalid=True
    def current_surfaces_closed(self):
        rows=self.c.get("decision_surfaces",[])
        if not isinstance(rows,list) or len(rows)!=12:return False
        for row in rows:
            if not isinstance(row,dict) or row.get("name") not in SURFACES:return False
            res=row.get("resolution")
            if not isinstance(res,dict):return False
            if res.get("mode")=="choice" and (not string_values(res.get("choice_ids")) or any(self.C.get(x,{}).get("status")!="confirmed" for x in string_values(res.get("choice_ids")))):return False
            if res.get("mode")=="forced" and ((not string_values(res.get("choice_ids")) and not string_values(res.get("fact_ids"))) or any(self.C.get(x,{}).get("status")!="confirmed" for x in string_values(res.get("choice_ids"))) or any(self.F.get(x,{}).get("stability")!="immutable_for_scope" for x in string_values(res.get("fact_ids")))):return False
            if res.get("mode") not in {"choice","forced"}:return False
        return True
    def specs(self):
        start=len(self.e);self.S=table(self.c.get("specifications"),"S","specifications",self.e)
        for i,r in self.S.items():
            l="specifications."+i
            if not exact(r,{"id","kind","statement","provenance"},l,self.e):continue
            if not isinstance(r.get("kind"),str) or r.get("kind") not in KIND:self.fail(l+".kind invalid")
            text(r.get("statement"),l+".statement",self.e);p=r.get("provenance")
            if not exact(p,{"mode","choice_ids","fact_ids","derivation"},l+".provenance",self.e):continue
            cs=refs(p,"choice_ids",self.C,l+".provenance",self.e);fs=refs(p,"fact_ids",self.F,l+".provenance",self.e)
            if p.get("mode")=="choice":
                if not cs or fs or p.get("derivation") is not None:self.fail(l+" choice provenance requires C only")
                if any(self.C.get(x,{}).get("status")!="confirmed" for x in cs):self.untraced.append(i);self.fail(l+" provenance choice must be confirmed")
            elif p.get("mode")=="forced":
                if not cs and not fs:self.fail(l+" forced provenance needs basis")
                if any(self.C.get(x,{}).get("status")!="confirmed" for x in cs):self.fail(l+" forced choice basis must be confirmed")
                if any(self.F.get(x,{}).get("stability")!="immutable_for_scope" for x in fs):self.fail(l+" forced fact basis invalid")
                text(p.get("derivation"),l+".provenance.derivation",self.e)
            else:self.fail(l+".provenance.mode invalid")
            if PH.search(json.dumps(r,ensure_ascii=False)):self.fail(l+" contains placeholder")
        if len(self.e)>start:self.compile_invalid=True
    def au(self):
        start=len(self.e);self.A=table(self.c.get("acceptance_checks"),"A","acceptance_checks",self.e);ak={"id","spec_ids","setup","input","action","observable_or_inspection","pass_condition","evidence","acceptance_type","measurement"}
        for i,r in self.A.items():
            l="acceptance_checks."+i
            if not exact(r,ak,l,self.e):continue
            if not refs(r,"spec_ids",self.S,l,self.e):self.fail(l+".spec_ids must be nonempty")
            for k in ("setup","input","action","observable_or_inspection","pass_condition","evidence"):text(r.get(k),l+"."+k,self.e)
            if not isinstance(r.get("acceptance_type"),str) or r.get("acceptance_type") not in {"functional","non_functional"}:self.fail(l+".acceptance_type invalid")
            if r.get("acceptance_type")=="functional" and r.get("measurement") is not None:self.fail(l+".measurement must be null for functional")
            if r.get("acceptance_type")=="non_functional":
                m=r.get("measurement")
                if exact(m,{"metric","threshold","conditions","method"},l+".measurement",self.e):
                    for k in ("metric","threshold","conditions","method"):text(m.get(k),l+".measurement."+k,self.e)
        self.U=table(self.c.get("implementation_units"),"U","implementation_units",self.e);uk={"id","title","spec_ids","acceptance_ids","inputs","outputs","change_boundary","forbidden_changes","dependency_unit_ids","execution_order","completion_evidence"};ms=set();ma=set()
        for i,r in self.U.items():
            l="implementation_units."+i
            if not exact(r,uk,l,self.e):continue
            ms.update(refs(r,"spec_ids",self.S,l,self.e));ma.update(refs(r,"acceptance_ids",self.A,l,self.e));text(r.get("title"),l+".title",self.e)
            for k in ("inputs","outputs","change_boundary","forbidden_changes","completion_evidence"):
                strings(r.get(k),l+"."+k,self.e,False)
                if not isinstance(r.get(k),list) or not r.get(k):self.fail(l+"."+k+" must be nonempty")
                elif all(isinstance(x,str) for x in r[k]) and len(r[k])!=len(set(r[k])):self.fail(l+"."+k+" must be unique")
            ds=refs(r,"dependency_unit_ids",self.U,l,self.e)
            if len(ds)!=len(set(ds)):self.fail(l+" duplicate dependency edge")
            if i in ds:self.fail(l+" self dependency")
            if type(r.get("execution_order")) is not int or r["execution_order"]<1:self.fail(l+".execution_order invalid")
            for d in ds:
                if d in self.U and type(self.U[d].get("execution_order")) is int and self.U[d]["execution_order"]>=r["execution_order"]:self.fail(l+" dependency order inversion")
            for aid in list_value(r.get("acceptance_ids")):
                acceptance=self.A.get(aid,{})
                if not set(string_values(acceptance.get("spec_ids"))).issubset(set(string_values(r.get("spec_ids")))):self.fail(l+" must own every specification referenced by its acceptance")
            if not r.get("spec_ids") or not r.get("acceptance_ids"):self.orphans.append(i)
        if self.f.get("target")=="decision" and self.U:self.fail("decision target implementation_units must be empty")
        for sid,spec in self.S.items():
            matching=[a for a in self.A.values() if sid in list_value(a.get("spec_ids"))]
            if not matching:self.unverified.append(sid);self.fail("specification "+sid+" requires an acceptance check")
            if spec.get("kind")=="performance":
                for acceptance in matching:
                    measurement=acceptance.get("measurement")
                    if acceptance.get("acceptance_type")!="non_functional" or not isinstance(measurement,dict) or any(not isinstance(measurement.get(k),str) or not measurement.get(k).strip() for k in ("metric","threshold","conditions","method")):
                        self.fail("performance specification "+sid+" requires nonfunctional measured acceptance")
                        self.unverified.append(sid)
        if self.f.get("target")=="implementation":
            self.orphans.extend(x for x in self.S if x not in ms);self.orphans.extend(x for x in self.A if x not in ma)
        graph={i:string_values(r.get("dependency_unit_ids")) for i,r in self.U.items()};active=[];done=set()
        def visit(x):
            if x in active:self.cycles.append(active[active.index(x):]+[x]);return
            if x in done:return
            active.append(x)
            for y in graph.get(x,[]):
                if y in graph:visit(y)
            active.pop();done.add(x)
        for x in graph:visit(x)
        if self.cycles:self.fail("implementation unit dependency cycle")
        if len(self.e)>start:self.compile_invalid=True
    def reverse_affected(self):
        for cid,c in self.C.items():
            expected_s={sid for sid,s in self.S.items() if cid in list_value(dict_value(s.get("provenance")).get("choice_ids"))}
            expected_a={aid for aid,a in self.A.items() if set(string_values(a.get("spec_ids"))) & expected_s}
            expected_u={uid for uid,u in self.U.items() if set(string_values(u.get("spec_ids"))) & expected_s or set(string_values(u.get("acceptance_ids"))) & expected_a}
            for key,expected in (("affected_spec_ids",expected_s),("affected_acceptance_ids",expected_a),("affected_unit_ids",expected_u)):
                actual=c.get(key,[])
                if actual!=sorted(expected):self.fail("choices."+cid+"."+key+" must equal computed reverse affected IDs")
    def final(self):
        self.O=table(self.c.get("open_items"),"O","open_items",self.e);ok={"id","kind","description","blocking_ids","status","resolution"}
        for i,r in self.O.items():
            l="open_items."+i
            if not exact(r,ok,l,self.e):continue
            if not isinstance(r.get("kind"),str) or r.get("kind") not in {"choice","conflict","research","external_dependency"}:self.fail(l+".kind invalid")
            text(r.get("description"),l+".description",self.e);refs(r,"blocking_ids",self.S,l,self.e)
            if not isinstance(r.get("status"),str) or r.get("status") not in {"open","resolved"}:self.fail(l+".status invalid")
            if r.get("status")=="open" and r.get("resolution") is not None:self.fail(l+".resolution must be null while open")
            if r.get("status")=="resolved":
                z=r.get("resolution")
                if exact(z,{"fact_ids","choice_ids","note"},l+".resolution",self.e):
                    fs=refs(z,"fact_ids",self.F,l+".resolution",self.e);cs=refs(z,"choice_ids",self.C,l+".resolution",self.e)
                    if not fs and not cs:self.fail(l+".resolution needs at least one fact or choice")
                    text(z.get("note"),l+".resolution.note",self.e)
        self.receipts()
        if self.f.get("alignment_status")=="aligned" and any(x.get("status")=="open" for x in self.O.values()):self.fail("aligned cannot contain open O")
        if self.f.get("handoff_status")=="ready" and self.f.get("target")!="implementation":self.fail("ready requires implementation target")
    def planner_text_check(self):
        values=[]
        def add(label,value):values.append((label,value))
        g=dict_value(self.c.get("goal"))
        for key in ("statement","success","failure","non_goals"):add("goal."+key,g.get(key))
        for i,row in enumerate(list_value(self.c.get("facts"))):
            if isinstance(row,dict):
                add(f"facts[{i}].stability_basis",row.get("stability_basis"));add(f"facts[{i}].limits",row.get("limits"))
        for i,row in enumerate(list_value(self.c.get("choices"))):
            if not isinstance(row,dict):continue
            base=f"choices[{i}]"
            for key in ("question","policy_targets","scope","consequences","confirmed_value"):add(base+"."+key,row.get(key))
            rec=dict_value(row.get("recommendation"));add(base+".recommendation.rationale",rec.get("rationale"))
            for j,alt in enumerate(list_value(row.get("alternatives"))):
                if isinstance(alt,dict):
                    add(f"{base}.alternatives[{j}].value",alt.get("value"));add(f"{base}.alternatives[{j}].outcome_delta",alt.get("outcome_delta"))
            supersession=dict_value(row.get("supersession"));add(base+".supersession.derivation",supersession.get("derivation"))
        for i,row in enumerate(list_value(self.c.get("decision_surfaces"))):
            if isinstance(row,dict):
                add(f"decision_surfaces[{i}].reason",row.get("reason"));add(f"decision_surfaces[{i}].resolution.derivation",dict_value(row.get("resolution")).get("derivation"))
        for i,row in enumerate(list_value(self.c.get("specifications"))):
            if isinstance(row,dict):
                add(f"specifications[{i}].statement",row.get("statement"));add(f"specifications[{i}].provenance.derivation",dict_value(row.get("provenance")).get("derivation"))
        for i,row in enumerate(list_value(self.c.get("acceptance_checks"))):
            if not isinstance(row,dict):continue
            for key in ("setup","input","action","observable_or_inspection","pass_condition","evidence"):add(f"acceptance_checks[{i}].{key}",row.get(key))
            measurement=dict_value(row.get("measurement"))
            for key in ("metric","threshold","conditions","method"):add(f"acceptance_checks[{i}].measurement.{key}",measurement.get(key))
        for i,row in enumerate(list_value(self.c.get("implementation_units"))):
            if not isinstance(row,dict):continue
            add(f"implementation_units[{i}].title",row.get("title"))
            for key in ("inputs","outputs","change_boundary","forbidden_changes","completion_evidence"):add(f"implementation_units[{i}].{key}",row.get(key))
        for i,row in enumerate(list_value(self.c.get("open_items"))):
            if isinstance(row,dict):
                add(f"open_items[{i}].description",row.get("description"));add(f"open_items[{i}].resolution.note",dict_value(row.get("resolution")).get("note"))
        def walk(label,x):
            if isinstance(x,str):
                if PH.search(x) or ASSUMPTION.search(x):self.planner_blockers.append(label)
            elif isinstance(x,list):
                for y in x:walk(label,y)
        for label,value in values:walk(label,value)
        for label in sorted(set(self.planner_blockers)):self.fail("planner-authored placeholder or assumption: "+label)
    def receipts(self):
        rv=self.c.get("reviews");
        if not exact(rv,{"ambiguity_auditor","cold_consumer"},"reviews",self.e):return
        rk={"review_id","reviewer","status","spec_digest","repository_context_digest","generated_at","output"}
        review_ids=set()
        for kind in ("ambiguity_auditor","cold_consumer"):
            r=rv.get(kind)
            if r is None:continue
            l="reviews."+kind
            if not exact(r,rk,l,self.e):continue
            rid=r.get("review_id")
            if not isinstance(rid,str) or not re.fullmatch(r"R[1-9][0-9]*",rid):self.fail(l+".review_id must match RN")
            elif rid in review_ids:self.fail("duplicate review ID: "+rid)
            else:review_ids.add(rid)
            text(r.get("reviewer"),l+".reviewer",self.e);sha(r.get("spec_digest"),l+".spec_digest",self.e);sha(r.get("repository_context_digest"),l+".repository_context_digest",self.e);stamp(r.get("generated_at"),l+".generated_at",self.e)
            if r.get("reviewer")!=kind:self.fail(l+".reviewer mismatch")
            if r.get("spec_digest")!=self.spec_digest():self.stale.append(kind+":spec_digest")
            if r.get("repository_context_digest")!=dg(self.c.get("repository_context")):self.stale.append(kind+":repository_context_digest")
            out=r.get("output");keys={"new_material_choices","counterexamples","contradictions","invalid_forced_consequences","invalid_local_coding","unexamined_surfaces"} if kind=="ambiguity_auditor" else {"steps","required_user_choices","implicit_assumptions","contradictions","underspecified_clauses","unmapped_spec_ids","local_choices"}
            if not exact(out,keys,l+".output",self.e):continue
            for k in keys:
                if not isinstance(out.get(k),list):self.fail(l+".output."+k+" must be array")
            if not isinstance(r.get("status"),str) or r.get("status") not in {"pass","findings"}:self.fail(l+".status invalid")
            if r.get("status")=="pass" and any(out.get(k) for k in keys if k not in {"steps","local_choices"}):self.fail(l+" pass contradicts findings")
            if r.get("status")=="findings" and not any(out.get(k) for k in keys if k not in {"steps","local_choices"}):self.fail(l+" findings status requires an actual finding")
            if kind=="cold_consumer":self.cold(out,l)
        cf=self.c.get("confirmations")
        if not exact(cf,{"alignment_summary","handoff_document"},"confirmations",self.e):return
        confirmation_ids=set();valid_confirmations={}
        for kind in ("alignment_summary","handoff_document"):
            r=cf.get(kind)
            if r is None:continue
            keys={"confirmation_id","exact_response","turn_id","confirmed_at","spec_digest","repository_context_digest","ambiguity_review_id","ambiguity_receipt_digest"}
            if kind=="handoff_document":keys|={"cold_review_id","cold_receipt_digest"}
            l="confirmations."+kind
            if not exact(r,keys,l,self.e):continue
            valid_confirmations[kind]=r;cid=r.get("confirmation_id")
            if not isinstance(cid,str) or not re.fullmatch(r"UC[1-9][0-9]*",cid):self.fail(l+".confirmation_id must match UCN")
            elif cid in confirmation_ids:self.fail("duplicate confirmation ID: "+cid)
            else:confirmation_ids.add(cid)
            text(r.get("exact_response"),l+".exact_response",self.e);text(r.get("turn_id"),l+".turn_id",self.e,True);stamp(r.get("confirmed_at"),l+".confirmed_at",self.e,True);sha(r.get("spec_digest"),l+".spec_digest",self.e);sha(r.get("repository_context_digest"),l+".repository_context_digest",self.e);text(r.get("ambiguity_review_id"),l+".ambiguity_review_id",self.e);sha(r.get("ambiguity_receipt_digest"),l+".ambiguity_receipt_digest",self.e)
            if r.get("turn_id") is None and r.get("confirmed_at") is None:self.fail(l+" needs turn_id or confirmed_at")
            if r.get("spec_digest")!=self.spec_digest() or r.get("repository_context_digest")!=dg(self.c.get("repository_context")):self.stale.append(kind+":digest")
            a=self.c.get("reviews",{}).get("ambiguity_auditor") if isinstance(self.c.get("reviews"),dict) else None
            if not isinstance(a,dict) or r.get("ambiguity_review_id")!=a.get("review_id"):self.fail(l+" ambiguity review mismatch")
            if isinstance(a,dict) and r.get("ambiguity_receipt_digest")!=dg(a):self.stale.append(kind+":ambiguity_receipt_digest")
            confirmation_time=instant(r.get("confirmed_at"));ambiguity_time=instant(a.get("generated_at")) if isinstance(a,dict) else None
            if confirmation_time is not None and ambiguity_time is not None and confirmation_time<=ambiguity_time:self.fail(l+" must be confirmed after ambiguity_auditor receipt")
            if kind=="handoff_document":
                c=self.c.get("reviews",{}).get("cold_consumer") if isinstance(self.c.get("reviews"),dict) else None
                if not isinstance(c,dict) or r.get("cold_review_id")!=c.get("review_id"):self.fail(l+" cold review mismatch")
                if isinstance(c,dict) and r.get("cold_receipt_digest")!=dg(c):self.stale.append(kind+":cold_receipt_digest")
        if "alignment_summary" in valid_confirmations and "handoff_document" in valid_confirmations:
            alignment=valid_confirmations["alignment_summary"];handoff=valid_confirmations["handoff_document"]
            a_time=alignment.get("confirmed_at");h_time=handoff.get("confirmed_at");cold=self.c.get("reviews",{}).get("cold_consumer") if isinstance(self.c.get("reviews"),dict) else None
            if not a_time or not h_time:self.fail("handoff_document requires timestamps for ordering")
            elif instant(h_time) is None or instant(a_time) is None:self.fail("handoff_document ordering timestamps must be valid instants")
            elif instant(h_time)<=instant(a_time):self.fail("handoff_document must be confirmed after alignment_summary")
            elif isinstance(cold,dict) and (instant(cold.get("generated_at")) is None or instant(h_time)<=instant(cold.get("generated_at"))):self.fail("handoff_document must follow cold_consumer receipt")
    def cold(self,out,l):
        ss=set();aa=set();uu=set()
        for i,s in enumerate(list_value(out.get("steps"))):
            z=f"{l}.steps[{i}]"
            if not exact(s,{"step","spec_ids","acceptance_ids","unit_ids"},z,self.e):continue
            text(s.get("step"),z+".step",self.e);step_s=refs(s,"spec_ids",self.S,z,self.e);step_a=refs(s,"acceptance_ids",self.A,z,self.e);step_u=refs(s,"unit_ids",self.U,z,self.e)
            ss.update(step_s);aa.update(step_a);uu.update(step_u)
            if self.f.get("target")=="implementation" and (not step_s or not step_a or not step_u):self.fail(z+" must map nonempty S/A/U")
            for aid in step_a:
                if not set(list_value(self.A.get(aid,{}).get("spec_ids"))).issubset(set(step_s)):self.fail(z+" acceptance/spec mapping is inconsistent")
            owned_s=set().union(*(set(list_value(self.U.get(uid,{}).get("spec_ids"))) for uid in step_u)) if step_u else set()
            owned_a=set().union(*(set(list_value(self.U.get(uid,{}).get("acceptance_ids"))) for uid in step_u)) if step_u else set()
            if not set(step_s).issubset(owned_s) or not set(step_a).issubset(owned_a):self.fail(z+" unit ownership is inconsistent")
        if ss!=set(self.S) or aa!=set(self.A) or (self.f.get("target")=="implementation" and uu!=set(self.U)):self.fail(l+" steps must cover all S/A/U")
        pk={"same_observable_behavior","unchanged_named_surfaces","no_system_impact","private_unit_only","reversible_without_spec_change"}
        local_ids=set()
        for i,z in enumerate(list_value(out.get("local_choices"))):
            lz=f"{l}.local_choices[{i}]"
            if not exact(z,{"id","description","unit_id",*pk},lz,self.e):continue
            local_id=z.get("id")
            if isinstance(local_id,str):
                if local_id in local_ids:self.fail(lz+" duplicate local choice ID")
                local_ids.add(local_id)
            if not isinstance(local_id,str) or not re.fullmatch(r"LC[1-9][0-9]*",local_id):self.fail(lz+".id must match LCN")
            text(z.get("description"),lz+".description",self.e);refs({"unit_id":[z.get("unit_id")]},"unit_id",self.U,lz,self.e)
            for k in pk:
                p=z.get(k)
                if not exact(p,{"satisfied","evidence"},lz+"."+k,self.e):continue
                if type(p.get("satisfied")) is not bool or p.get("satisfied") is not True:self.fail(lz+"."+k+" satisfied must be boolean true")
                text(p.get("evidence"),lz+"."+k+".evidence",self.e)
    def spec_projection(self):return {k:self.c.get(k) for k in ("contract_version","revision","target","goal","facts","choices","question_rounds","decision_surfaces","specifications","acceptance_checks","implementation_units","open_items")}
    def spec_digest(self):return dg(self.spec_projection())
    def run(self):
        self.front();self.top();self.context();self.facts()
        # Build lookup tables before checking cross-register affected lists.
        self.C=table(self.c.get("choices"),"C","choices",self.e)
        self.S=table(self.c.get("specifications"),"S","specifications",self.e)
        self.A=table(self.c.get("acceptance_checks"),"A","acceptance_checks",self.e)
        self.U=table(self.c.get("implementation_units"),"U","implementation_units",self.e)
        self.choices();self.rounds();self.surfaces();self.specs();self.au();self.reverse_affected();self.final();self.planner_text_check()
        if re.search(r"\b(?:assumption|assumes|가정)\b",json.dumps(self.c.get("goal",{}),ensure_ascii=False),re.I):self.fail("canonical goal contains assumption")
    def gate(self,require):
        out=list(self.e);aligned=self.f.get("alignment_status")=="aligned" or require in {"aligned","handoff-ready"} or self.f.get("handoff_status")=="ready";ready=self.f.get("handoff_status")=="ready" or require=="handoff-ready"
        if require=="aligned" and self.f.get("alignment_status")!="aligned":out.append("--require aligned requires front alignment_status aligned")
        if aligned:
            if self.f.get("alignment_status")!="aligned":out.append("aligned gate requires front alignment_status aligned")
            if self.context_invalid or self.fact_invalid or not self.F:out.append("aligned requires usable repository context and observed facts")
            if not self.current_surfaces_closed():out.append("all decision surfaces must have current confirmed closure")
            if self.unresolved:out.append("unresolved choices remain")
            if any(x.get("status")=="open" for x in self.O.values()):out.append("open items remain")
            if self.planner_blockers:out.append("planner-authored placeholder or assumption remains")
            a=self.c.get("reviews",{}).get("ambiguity_auditor") if isinstance(self.c.get("reviews"),dict) else None
            if not isinstance(a,dict) or a.get("status")!="pass" or any(x.startswith("ambiguity_auditor") for x in self.stale):out.append("fresh ambiguity auditor PASS required")
            x=self.c.get("confirmations",{}).get("alignment_summary") if isinstance(self.c.get("confirmations"),dict) else None
            if not isinstance(x,dict) or any(y.startswith("alignment_summary") for y in self.stale):out.append("fresh alignment summary confirmation required")
        if ready:
            if self.f.get("alignment_status")!="aligned":out.append("handoff-ready requires front alignment_status aligned")
            if self.f.get("handoff_status")!="ready":out.append("handoff-ready requires front handoff_status ready")
            if self.f.get("target")!="implementation":out.append("handoff-ready requires implementation target")
            if self.f.get("session_status")!="complete":out.append("handoff-ready requires complete session")
            if not self.S or not self.A or not self.U:out.append("handoff-ready requires nonempty S/A/U registers")
            if self.planner_blockers:out.append("planner-authored placeholder or assumption remains")
            c=self.c.get("reviews",{}).get("cold_consumer") if isinstance(self.c.get("reviews"),dict) else None
            if not isinstance(c,dict) or c.get("status")!="pass" or any(x.startswith("cold_consumer") for x in self.stale):out.append("fresh cold consumer PASS required")
            if isinstance(c,dict):
                for k in ("required_user_choices","implicit_assumptions","contradictions","underspecified_clauses","unmapped_spec_ids"):
                    if dict_value(c.get("output")).get(k):out.append("cold consumer blocker: "+k)
            if self.orphans:out.append("graph orphan remains")
            if self.cycles:out.append("dependency cycle remains")
            if self.untraced or self.unverified:out.append("untraced/unverified specification remains")
            h=self.c.get("confirmations",{}).get("handoff_document") if isinstance(self.c.get("confirmations"),dict) else None
            if not isinstance(h,dict) or any(x.startswith("handoff_document") for x in self.stale):out.append("fresh handoff confirmation required")
        return list(dict.fromkeys(out))
    def action(self):
        if self.f.get("session_status")=="paused":return "pause"
        if self.context_invalid or self.fact_invalid or not self.F or any(x.get("status")=="open" and x.get("kind")=="research" for x in self.O.values()):return "research_facts"
        if any(x.get("status")=="open" and x.get("kind")=="external_dependency" for x in self.O.values()):return "pause"
        if self.surface_invalid or self.uncovered:return "map_choices"
        if self.choice_invalid or self.unresolved or any(x.get("status")=="open" and x.get("kind")=="choice" for x in self.O.values()):return "ask_choices"
        if self.compile_invalid or self.untraced or self.unverified or self.orphans or self.cycles:return "compile_spec"
        if self.planner_blockers:return "resolve_findings"
        a=self.c.get("reviews",{}).get("ambiguity_auditor") if isinstance(self.c.get("reviews"),dict) else None
        if not isinstance(a,dict) or any(x.startswith("ambiguity_auditor") for x in self.stale):return "run_ambiguity_audit"
        if isinstance(a,dict) and (a.get("status")=="findings" or any(x.get("kind")=="conflict" and x.get("status")=="open" for x in self.O.values())):return "resolve_findings"
        x=self.c.get("confirmations",{}).get("alignment_summary") if isinstance(self.c.get("confirmations"),dict) else None
        if not isinstance(x,dict) or any(y.startswith("alignment_summary") for y in self.stale):return "request_final_confirmation"
        if self.f.get("target")=="decision":return "complete" if self.gate_passes("aligned") else "resolve_findings"
        c=self.c.get("reviews",{}).get("cold_consumer") if isinstance(self.c.get("reviews"),dict) else None
        if not isinstance(c,dict) or any(x.startswith("cold_consumer") for x in self.stale):return "run_cold_consumer"
        if isinstance(c,dict) and any(dict_value(c.get("output")).get(k) for k in ("required_user_choices","implicit_assumptions","contradictions","underspecified_clauses","unmapped_spec_ids")):return "resolve_findings"
        h=self.c.get("confirmations",{}).get("handoff_document") if isinstance(self.c.get("confirmations"),dict) else None
        if not isinstance(h,dict) or any(x.startswith("handoff_document") for x in self.stale):return "request_final_confirmation"
        return "complete" if self.gate_passes("handoff-ready") else "resolve_findings"
    def gate_passes(self,require):
        """Return whether the target gate is fully satisfied."""
        return not self.gate(require)
    def output(self,require):
        f=self.gate(require)
        next_action=self.action()
        relevant="handoff-ready" if self.f.get("target")=="implementation" else "aligned"
        # Completion is an assertion about the target gate, even for a
        # structural invocation whose requested gate is weaker.
        if next_action=="complete" and not self.gate_passes(relevant):next_action="resolve_findings"
        return {"valid":not f,"require":require,"next_action":next_action,"errors":f,"unresolved_choice_ids":sorted(set(self.unresolved)),"uncovered_surfaces":sorted(set(self.uncovered)),"untraced_spec_ids":sorted(set(self.untraced)),"unverified_spec_ids":sorted(set(self.unverified)),"graph_cycles":self.cycles,"graph_orphans":sorted(set(x for x in self.orphans if isinstance(x,str) and x)),"stale_receipts":sorted(set(self.stale)),"spec_digest":self.spec_digest(),"repository_context_digest":dg(self.c.get("repository_context"))}

def diagnostic(require,next_action,errors,*,spec_digest=None,repository_context_digest=None):
    return {"valid":False,"require":require,"next_action":next_action,"errors":list(errors),"unresolved_choice_ids":[],"uncovered_surfaces":[],"untraced_spec_ids":[],"unverified_spec_ids":[],"graph_cycles":[],"graph_orphans":[],"stale_receipts":[],"spec_digest":spec_digest,"repository_context_digest":repository_context_digest}

def validate(path,require):
    try:raw=Path(path).read_text(encoding="utf-8")
    except (OSError,UnicodeError) as ex:return 2,diagnostic(require,"research_facts",[str(ex)])
    f,b,e=front(raw);c,x=contract(b);e+=x
    if c is None:return 1,diagnostic(require,"research_facts",e)
    v=V(raw,f,c);v.e+=e
    try:
        v.run();o=v.output(require)
    except Exception as ex:
        # Any parseable JSON shape must fail validation without leaking a traceback.
        return 1,diagnostic(require,"resolve_findings",["malformed contract structure: "+type(ex).__name__+": "+str(ex)])
    return (0 if o["valid"] else 1),o

class UsageError(Exception):pass
class Parser(argparse.ArgumentParser):
    def error(self,message):raise UsageError(message)

def main(argv=None):
    args=list(argv) if argv is not None else None;want_json="--json" in (args if args is not None else __import__("sys").argv[1:])
    p=Parser(prog="validate_goal_spec.py");p.add_argument("path",nargs="?");p.add_argument("--require",choices=("structural","aligned","handoff-ready"),default="structural");p.add_argument("--json",action="store_true")
    try:
        a=p.parse_args(args)
        if not a.path:raise UsageError("PATH is required")
    except UsageError as ex:
        o=diagnostic("structural","research_facts",["usage error: "+str(ex)])
        print(json.dumps(o,ensure_ascii=False,indent=2,sort_keys=True) if want_json else "FAIL\nnext_action: research_facts\nusage error: "+str(ex));return 2
    code,o=validate(a.path,a.require)
    if a.json:print(json.dumps(o,ensure_ascii=False,indent=2,sort_keys=True))
    else:
        print("PASS" if code==0 else "FAIL");print("next_action: "+o["next_action"])
        for error in o["errors"]:print("- "+error)
    return code
if __name__=="__main__":raise SystemExit(main())
