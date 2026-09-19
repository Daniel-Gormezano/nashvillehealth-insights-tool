from __future__ import annotations
from dataclasses import dataclass,field
from pathlib import Path
from typing import Any
import pandas as pd
from .text_utils import extract_years,period_contains_year,period_end_year
@dataclass(slots=True)
class HealthDataRepository:
    data_path:Path; metadata_path:Path; data:pd.DataFrame=field(init=False,repr=False); metadata:pd.DataFrame=field(init=False,repr=False); indicator_names:list[str]=field(init=False); city_names:list[str]=field(init=False); meta_lookup:dict[str,dict[str,Any]]=field(init=False,repr=False)
    def __post_init__(self):
        self.data=pd.read_csv(self.data_path); self.metadata=pd.read_csv(self.metadata_path).fillna("")
        self.data["CHR&R release year"]=pd.to_numeric(self.data["CHR&R release year"],errors="coerce").astype("Int64"); self.data["Value"]=pd.to_numeric(self.data["Value"],errors="coerce")
        self.data["Underlying data year / period"]=self.data["Underlying data year / period"].fillna("").astype(str)
        for c in ("City","County","Indicator","Category","Better direction","Unit"):self.data[c]=self.data[c].fillna("").astype(str)
        self.indicator_names=self.metadata["indicator"].astype(str).tolist(); self.city_names=self.data["City"].drop_duplicates().tolist(); self.meta_lookup=self.metadata.set_index("indicator").to_dict(orient="index")
    def metadata_for(self,indicator):return dict(self.meta_lookup.get(indicator,{}))
    @staticmethod
    def format_value(value,unit):
        if value is None or pd.isna(value):return "Not available"
        u=str(unit or "").strip(); low=u.lower()
        if u=="%":return f"{value:.1f}%"
        if u=="USD" or "dollar" in low:return f"${value:,.0f}"
        if low=="years":return f"{value:.1f} years"
        if "ratio" in low:return f"{value:.2f}"
        if "residents per" in low:return f"{value:,.0f} residents per provider"
        n=f"{value:,.0f}" if abs(value)>=1000 else (f"{value:,.1f}" if abs(value)>=100 else f"{value:.1f}")
        return f"{n} {u}".strip()
    def _scope_cities(self,cities):
        selected=[c for c in (cities or []) if c in self.city_names]
        return ["Nashville",*[c for c in selected if c!="Nashville"]] if selected else list(self.city_names)
    def _release_for_indicator(self,indicator,requested_year=None,comparison_cities=None):
        subset=self.data[(self.data["Indicator"]==indicator)&self.data["Value"].notna()].copy(); required=set(self._scope_cities(comparison_cities)); nash=subset[subset["City"]=="Nashville"].copy()
        if subset.empty or nash.empty:return None,""
        def has_scope(y):return required.issubset(set(subset[subset["CHR&R release year"]==y]["City"]))
        note=""
        if requested_year:
            matches=nash[nash["Underlying data year / period"].apply(lambda v:period_contains_year(v,requested_year))]
            for y in sorted(matches["CHR&R release year"].dropna().astype(int).unique(),reverse=True):
                if has_scope(int(y)):return int(y),""
            if not nash[nash["CHR&R release year"]==requested_year].empty and has_scope(requested_year):return requested_year,""
            for y in sorted(nash[nash["CHR&R release year"]<=requested_year]["CHR&R release year"].dropna().astype(int).unique(),reverse=True):
                if has_scope(int(y)):return int(y),f"No exact value was available for {requested_year}, so the closest earlier usable release was used."
        for y in sorted(nash["CHR&R release year"].dropna().astype(int).unique(),reverse=True):
            if has_scope(int(y)):return int(y),note
        return int(nash["CHR&R release year"].max()),note
    def current_facts(self,indicator,requested_year=None,comparison_cities=None):
        meta=self.metadata_for(indicator); release,note=self._release_for_indicator(indicator,requested_year,comparison_cities)
        if release is None:return {"available":False,"indicator":indicator,"metadata":meta}
        scope=self._scope_cities(comparison_cities); group=self.data[(self.data["Indicator"]==indicator)&(self.data["CHR&R release year"]==release)&self.data["Value"].notna()&self.data["City"].isin(scope)].copy(); nr=group[group["City"]=="Nashville"]
        if nr.empty:return {"available":False,"indicator":indicator,"metadata":meta}
        n=nr.iloc[0]; direction=str(n["Better direction"] or meta.get("better_direction") or "Lower is better"); high=direction.lower().startswith("higher"); group=group.sort_values(["Value","City"],ascending=[not high,True]); vals=group["Value"].astype(float).tolist(); nv=float(n["Value"]); rank=vals.index(nv)+1
        peers=group[group["City"]!="Nashville"]; avg=float(peers["Value"].mean()) if not peers.empty else None; diff=nv-avg if avg is not None else None; pct=diff/avg*100 if diff is not None and avg not in (None,0) else None
        comp="about the same as" if diff is None or abs(diff)<1e-12 else ("better than" if (high and diff>0) or ((not high) and diff<0) else "worse than")
        best,worst=group.iloc[0],group.iloc[-1]; unit=str(n["Unit"] or ""); count=int(group["City"].nunique()); rows=[]
        for pos,(_,r) in enumerate(group.iterrows(),1):rows.append({"City":str(r["City"]),"Value":float(r["Value"]),"Value display":self.format_value(float(r["Value"]),unit),"Rank":pos,"Is Nashville":str(r["City"])=="Nashville","Is best":pos==1,"Is worst":pos==count})
        scope_label="Nashville, "+", ".join(c for c in scope if c!="Nashville") if comparison_cities else "Nashville and eight peer cities"
        return {"available":True,"indicator":indicator,"metadata":meta,"release_year":int(release),"data_period":str(n["Underlying data year / period"] or "").strip(),"unit":unit,"direction":direction,"higher_is_better":high,"nashville_value":nv,"nashville_value_display":self.format_value(nv,unit),"peer_average":avg,"peer_average_display":self.format_value(avg,unit),"difference":diff,"percent_difference":pct,"rank":rank,"city_count":count,"comparison":comp,"best_city":str(best["City"]),"best_value":float(best["Value"]),"best_value_display":self.format_value(float(best["Value"]),unit),"worst_city":str(worst["City"]),"worst_value":float(worst["Value"]),"worst_value_display":self.format_value(float(worst["Value"]),unit),"selection_note":note,"comparison_rows":rows,"comparison_scope":scope_label}
    def trend_facts(self,indicator,start_year=None,end_year=None,comparison_cities=None,limit=10):
        meta=self.metadata_for(indicator); scope=self._scope_cities(comparison_cities); subset=self.data[(self.data["Indicator"]==indicator)&self.data["Value"].notna()&self.data["City"].isin(scope)].copy()
        if subset.empty:return {"available":False,"indicator":indicator,"metadata":meta}
        rows=[]
        for release,g in subset.groupby("CHR&R release year"):
            nr=g[g["City"]=="Nashville"]
            if nr.empty:continue
            n=nr.iloc[0]; peers=g[g["City"]!="Nashville"]; unit=str(n["Unit"] or ""); period=str(n["Underlying data year / period"] or "").strip(); label=period or f"CHR&R {int(release)}"; end=period_end_year(period,int(release))
            if start_year is not None and end<start_year:continue
            if end_year is not None and end>end_year:continue
            avg=float(peers["Value"].mean()) if not peers.empty else None
            rows.append({"label":label,"period":period,"end_year":end,"release_year":int(release),"value":float(n["Value"]),"value_display":self.format_value(float(n["Value"]),unit),"peer_average":avg,"peer_average_display":self.format_value(avg,unit),"unit":unit})
        if len(rows)<2:return {"available":False,"indicator":indicator,"metadata":meta}
        dedup={};
        for r in sorted(rows,key=lambda x:x["release_year"]):dedup[r["label"]]=r
        rows=sorted(dedup.values(),key=lambda x:(x["end_year"],x["release_year"]))[-limit:]; first,latest=rows[0],rows[-1]; change=latest["value"]-first["value"]
        ds=self.data[self.data["Indicator"]==indicator]["Better direction"].dropna().astype(str); direction=str(ds.iloc[-1]) if not ds.empty else str(meta.get("better_direction") or "Lower is better"); high=direction.lower().startswith("higher")
        label="stayed about the same" if abs(change)<1e-12 else ("improved" if (high and change>0) or ((not high) and change<0) else "worsened")
        periods=[]
        for r in rows:
            ys=extract_years(r["period"])
            if len(ys)>=2:periods.append((min(ys),max(ys)))
        overlap=any(periods[i][0]<=periods[i-1][1] for i in range(1,len(periods)))
        return {"available":True,"indicator":indicator,"metadata":meta,"rows":rows,"first":first,"latest":latest,"change":change,"change_display":self.format_value(abs(change),latest["unit"]),"trend_label":label,"direction":direction,"overlapping_periods":overlap}
    def related_facts(self,indicator):
        m=self.metadata_for(indicator); return [self.current_facts(str(n)) for n in (m.get("related_indicator_1",""),m.get("related_indicator_2",""),m.get("related_indicator_3","")) if n]
    def overview_facts(self):
        facts=[self.current_facts(i) for i in self.indicator_names]; usable=[f for f in facts if f.get("available") and f.get("city_count",0)>=7 and f.get("rank") is not None]
        return {"available":bool(usable),"challenges":sorted(usable,key=lambda f:(f["rank"]/max(f["city_count"],1),f["rank"]),reverse=True)[:4],"strengths":sorted(usable,key=lambda f:(f["rank"]/max(f["city_count"],1),f["rank"]))[:3]}
    def indicator_catalog(self):return self.metadata[["indicator","plain_language_name","plain_language_definition","search_terms"]].to_dict(orient="records")
