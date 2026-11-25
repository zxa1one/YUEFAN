"""Mode-independent group distance and auditable, missing-aware ranking."""
from math import radians, sin, cos, asin, sqrt, isfinite
from result_order import result_key
# V0.15: remove unsupported popularity and preserve the latest rating/distance ratio.
WEIGHTS={'rating':48.89/51.11,'distance':2.22/51.11}
STATUS={'open':0,'unknown':1,'closed':2}
def haversine(a,b):
    x,y=map(radians,a); u,v=map(radians,b)
    return 6371*2*asin(min(1,sqrt(sin((v-y)/2)**2+cos(y)*cos(v)*sin((u-x)/2)**2)))
def distance_cost(ds):
    return .7*sum(ds)/len(ds)+.3*max(ds) if ds else None

def budget_info(price,budget):
    if budget is None:return None,None
    if price is None:return 'unknown',None
    delta=round(abs(price-budget),2)
    return ('near' if delta<=budget*.2+1e-9 else 'outside'),delta

def valid(v):return type(v) in (int,float) and isfinite(v) and v>=0

def normalize_weights(weights,keys):
    total=sum(weights[k] for k in keys)
    return {k:weights[k]/total for k in keys} if total else {}

def rank(restaurants,members,mode='composite',budget=None):
    if mode not in ('composite','price_asc','price_desc','distance_asc','distance_desc','rating','results'):mode='composite'
    for r in restaurants:
        routes=r.get('routes',{})
        ds=[routes.get(m['id'],{}).get('km') for m in members if m.get('location') is not None or 'location' not in m]
        r['locationCoverage']=sum(valid(d) for d in ds)
        r['distance']=distance_cost(ds) if ds and all(valid(d) for d in ds) else None
        r['average']=sum(ds)/len(ds) if r['distance'] is not None else None
        r['maximum']=max(ds) if r['distance'] is not None else None
    active=[r for r in restaurants if r['status']=='open'] or restaurants
    # A known rating must not be discarded merely because another candidate has no rating.
    rated=[r for r in active if valid(r.get('rating')) and r['rating']<=5]
    cohort=rated or active
    # Commercial popularity is intentionally disabled in this release, even in demo mode.
    for r in restaurants:
        for field in ('popularity','popularity_weights','popularity_counts','popularity_source','popularity_as_of','sales','sales_source','sales_as_of'):
            r.pop(field,None)
    available=[k for k in WEIGHTS if cohort and all(valid(r.get(k)) for r in cohort)]
    effective=normalize_weights(WEIGHTS,available)
    distances=[r['distance'] for r in cohort if valid(r.get('distance'))]
    lo,hi=(min(distances),max(distances)) if distances else (0,0)
    for r in restaurants:
        score=0;parts={}
        for k,w in effective.items():
            v=r.get(k)
            if not valid(v):parts={};break
            if k=='rating':q=max(0,min(1,v/5))
            else:q=.5 if lo==hi else 1-max(0,min(1,(v-lo)/(hi-lo)))
            parts[k]=round(q*100,2);score+=w*q*100
        r['score']=round(score,2) if parts else None
        r['parts']=parts
        r['budgetMatch'],r['budgetDifference']=budget_info(r.get('price'),budget)
        r['votes']=sum(m.get('vote')==r['id'] for m in members)
    if mode=='results':
        return sorted(restaurants,key=result_key),effective
    field,desc={'composite':('score',True),'price_asc':('price',False),'price_desc':('price',True),'distance_asc':('distance',False),'distance_desc':('distance',True),'rating':('rating',True),'results':('votes',True)}.get(mode,('score',True))
    def key(r):
        v=r.get(field);s=r.get('score');budget_key=()
        if mode=='composite' and budget is not None:
            group={'near':0,'outside':1,'unknown':2}[r['budgetMatch']]
            budget_key=(group,r['budgetDifference'] if group==1 else 0)
        return (STATUS.get(r['status'],1),*budget_key,v is None,(-v if desc else v) if v is not None else 0,s is None,-s if s is not None else 0,r['id'])
    return sorted(restaurants,key=key),effective
