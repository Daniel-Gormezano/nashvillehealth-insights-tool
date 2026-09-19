from __future__ import annotations
import json,re
from typing import Any
from rapidfuzz import fuzz
from .data_service import HealthDataRepository
from .llm_client import LLMClient
from .models import QueryPlan
from .text_utils import normalize_text
INTENT_HINTS={"trend":["over time","trend","changed","change","improved","worsened","getting better","getting worse","increasing","decreasing","since","from ","between "],"extremes":["best","worst","highest","lowest","most","least","strongest","weakest"],"comparison":["compare","compared","peer","peers","similar cities","than other cities","rank","stack up","unusually","relative to","versus"," vs ","better than","worse than"],"why":["why","matter","matters","important","care about","so what"],"related":["related","connected","go along with","other factors","other measures","linked"],"overview":["how healthy is nashville","biggest health challenges","main health problems","health at a glance","overall health","where should nashville focus","what matters most","health priorities","top health issues"]}
CONCEPT_ALIASES={"not moving enough":"Physical Inactivity","people not moving enough":"Physical Inactivity","not active enough":"Physical Inactivity","living shorter lives":"Life Expectancy","living longer":"Life Expectancy","how long people live":"Life Expectancy","housing affordability":"Severe Housing Cost Burden","rent too high":"Severe Housing Cost Burden","housing too expensive":"Severe Housing Cost Burden","access to therapy":"Mental Health Providers","access to mental health care":"Mental Health Providers","mental health care":"Mental Health Providers","bad mental health days":"Poor Mental Health Days","mental distress":"Poor Mental Health Days","not enough sleep":"Insufficient Sleep","getting enough sleep":"Insufficient Sleep","places to exercise":"Access to Exercise Opportunities","places to be active":"Access to Exercise Opportunities","people without insurance":"Uninsured","doctor access":"Primary Care Physicians","internet access":"Broadband Access","food access":"Food Insecurity"}
class QueryParser:
    def __init__(self,repository:HealthDataRepository,llm:LLMClient):self.repository=repository;self.llm=llm
    def parse(self,question,previous_indicator=""):
        question=str(question or "").strip()
        if not question:return QueryPlan(needs_clarification=True,clarification="Please enter a question.")
        if self.llm.available:
            parsed=self._parse_with_llm(question,previous_indicator)
            if parsed is not None:return parsed
        return self._parse_fallback(question,previous_indicator)
    def _parse_with_llm(self,question,previous_indicator):
        catalog="\n".join(f"- {r['indicator']}: {r['plain_language_definition']}" for r in self.repository.indicator_catalog()); cities=", ".join(self.repository.city_names)
        system='''You classify questions for a Nashville public-health data tool. Return JSON only. Never invent an indicator or city. Allowed intents: current, comparison, trend, extremes, why, related, overview. Use overview for broad Nashville health priorities. Use trend for change over time or since/between years. Use comparison for peers, similar cities, ranking, unusually high/low, better/worse, versus, or compare. Use Poor Mental Health Days for general mental-health burden; use Mental Health Providers only for access to care. Use Physical Inactivity for "not moving enough" and Life Expectancy for "living shorter lives". Nashville is always included. Schema: {"indicators":["exact allowed indicator"],"intent":"allowed intent","requested_year":2020 or null,"start_year":2015 or null,"end_year":2024 or null,"comparison_cities":["exact allowed city"],"needs_clarification":false,"clarification":""}.'''
        raw=self.llm.chat(system=system,user=f"Allowed indicators:\n{catalog}\nAllowed cities: {cities}\nPrevious indicator: {previous_indicator or 'none'}\nQuestion: {question}",json_mode=True,temperature=0)
        if not raw:return None
        payload=self._extract_json(raw)
        if not isinstance(payload,dict):return None
        inds=[x for x in payload.get("indicators",[]) if x in self.repository.indicator_names]; cs=[x for x in payload.get("comparison_cities",[]) if x in self.repository.city_names and x!="Nashville"]; intent=str(payload.get("intent") or "current")
        if intent!="overview" and not inds and previous_indicator in self.repository.indicator_names:inds=[previous_indicator]
        if intent!="overview" and not inds:return None
        return QueryPlan(indicators=inds,intent=intent,requested_year=payload.get("requested_year"),start_year=payload.get("start_year"),end_year=payload.get("end_year"),comparison_cities=cs,needs_clarification=bool(payload.get("needs_clarification",False)),clarification=str(payload.get("clarification") or ""),matched_by="llm")
    @staticmethod
    def _extract_json(raw):
        text=raw.strip(); text=re.sub(r"^```(?:json)?|```$","",text,flags=re.I).strip()
        try:return json.loads(text)
        except json.JSONDecodeError:
            m=re.search(r"\{.*\}",text,re.S)
            if not m:return None
            try:return json.loads(m.group(0))
            except json.JSONDecodeError:return None
    def _parse_fallback(self,question,previous_indicator):
        n=normalize_text(question); intent="current"
        for candidate in ("overview","trend","extremes","comparison","why","related"):
            if any(normalize_text(t) in n for t in INTENT_HINTS[candidate]):intent=candidate;break
        years=[int(x) for x in re.findall(r"\b(?:19|20)\d{2}\b",question)]; requested=start=end=None
        if len(years)>=2:start,end=min(years),max(years);intent="trend"
        elif len(years)==1:
            if intent=="trend" or any(x in n for x in ("since","from","over time")):start=years[0];intent="trend"
            else:requested=years[0]
        cities=[c for c in self.repository.city_names if c!="Nashville" and normalize_text(c) in n]
        if intent=="overview":return QueryPlan(intent="overview",requested_year=requested,start_year=start,end_year=end,comparison_cities=cities,matched_by="fallback")
        for phrase,indicator in CONCEPT_ALIASES.items():
            if normalize_text(phrase) in n:return QueryPlan(indicators=[indicator],intent=intent,requested_year=requested,start_year=start,end_year=end,comparison_cities=cities,matched_by="fallback")
        scored=[];qt=set(n.split())
        for r in self.repository.indicator_catalog():
            terms=[x.strip() for x in str(r.get("search_terms") or "").split(",") if x.strip()]; score=0
            for text in [r["indicator"],r.get("plain_language_name",""),r.get("plain_language_definition",""),*terms]:
                c=normalize_text(text)
                if not c:continue
                if c in n:score=max(score,95+min(len(c.split()),5))
                score=max(score,fuzz.partial_ratio(n,c)*.84);over=len(qt&set(c.split()))
                if over:score=max(score,45+over*12)
            scored.append((score,r["indicator"]))
        scored.sort(reverse=True);best_score,best=scored[0]
        if best_score<58 and previous_indicator in self.repository.indicator_names:best=previous_indicator;best_score=60
        if best_score<58:return QueryPlan(needs_clarification=True,clarification="I could not tell which health topic you meant. Try naming an issue such as sleep, smoking, housing, mental health, or access to care.")
        return QueryPlan(indicators=[best],intent=intent,requested_year=requested,start_year=start,end_year=end,comparison_cities=cities,matched_by="fallback")
