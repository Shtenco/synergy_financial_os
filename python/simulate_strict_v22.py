from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
import argparse, csv, json, math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar

@dataclass
class Pool:
    token: float
    usdc: float
    fee: float = 0.003
    total_lp: float = 1_000_000.0
    protocol_lp: float = 0.0
    name: str = ''

    def pshare(self): return self.protocol_lp / self.total_lp if self.total_lp else 0.0
    def protocol_usdc(self): return self.pshare() * self.usdc
    def q_token_to_usdc(self, x):
        z=x*(1-self.fee); return self.usdc*z/(self.token+z) if z>0 else 0.0
    def q_usdc_to_token(self, x):
        z=x*(1-self.fee); return self.token*z/(self.usdc+z) if z>0 else 0.0
    def token_to_usdc(self,x):
        y=self.q_token_to_usdc(x); self.token+=x; self.usdc-=y; return y
    def usdc_to_token(self,x):
        y=self.q_usdc_to_token(x); self.usdc+=x; self.token-=y; return y
    def add_protocol_lp(self,usdc_in,token_in):
        if usdc_in<=0 or token_in<=0:return 0.0
        req=usdc_in*self.token/self.usdc
        assert abs(token_in-req)<=max(1e-8,req*1e-10),'NON_PROPORTIONAL_LP'
        frac=usdc_in/self.usdc; minted=self.total_lp*frac
        self.token+=token_in; self.usdc+=usdc_in; self.total_lp+=minted; self.protocol_lp+=minted
        return minted

@dataclass
class CrossPool:
    c: float
    x: float
    fee: float = 0.0005
    def q_c_to_x(self,v):
        z=v*(1-self.fee); return self.x*z/(self.c+z) if z>0 else 0.0
    def q_x_to_c(self,v):
        z=v*(1-self.fee); return self.c*z/(self.x+z) if z>0 else 0.0
    def c_to_x(self,v):
        y=self.q_c_to_x(v); self.c+=v; self.x-=y; return y
    def x_to_c(self,v):
        y=self.q_x_to_c(v); self.x+=v; self.c-=y; return y

@dataclass
class Ledger:
    cu: Pool; xu: Pool; cx: CrossPool
    treasury_u: float
    protocol_free_c: float; protocol_free_x: float
    external_u: float; external_c: float; external_x: float
    supply_c: float; supply_x: float; backing_c_usdc: float
    def hard_tvl(self): return self.treasury_u+self.cu.protocol_usdc()+self.xu.protocol_usdc()
    def solvency_nav(self): return self.backing_c_usdc+self.hard_tvl()-self.supply_c
    def totals(self):
        return (self.cu.token+self.cx.c+self.protocol_free_c+self.external_c,
                self.xu.token+self.cx.x+self.protocol_free_x+self.external_x,
                self.cu.usdc+self.xu.usdc+self.treasury_u+self.external_u)
    def assert_conservation(self,c0,x0,u0,tol=1e-6):
        c,x,u=self.totals()
        assert abs(c-c0)<=max(tol,abs(c0)*1e-11)
        assert abs(x-x0)<=max(tol,abs(x0)*1e-11)
        assert abs(u-u0)<=max(tol,abs(u0)*1e-11)
        assert abs(c-self.supply_c)<=max(tol,abs(self.supply_c)*1e-11)
        assert abs(x-self.supply_x)<=max(tol,abs(self.supply_x)*1e-11)

def route(L,d,u,execute=False):
    t=L if execute else deepcopy(L)
    if d==0:
        x=t.xu.usdc_to_token(u); c=t.cx.x_to_c(x); out=t.cu.token_to_usdc(c)
    else:
        c=t.cu.usdc_to_token(u); x=t.cx.c_to_x(c); out=t.xu.token_to_usdc(x)
    return out,t

def candidate(L,d,u,fixed=.05,flash_bps=0.0):
    out,t=route(L,d,u,False)
    wallet=out-u-u*flash_bps/10000-fixed
    consolidated=wallet+(t.cu.protocol_usdc()+t.xu.protocol_usdc()-L.cu.protocol_usdc()-L.xu.protocol_usdc())
    return wallet,consolidated

def optimize(L,max_trade=50_000.0,fixed=.05,flash_bps=0.0):
    best=(-1e100,-1e100,-1,0.0)
    for d in (0,1):
        r=minimize_scalar(lambda z:-candidate(L,d,z,fixed,flash_bps)[1],bounds=(1e-8,max_trade),method='bounded',options={'xatol':1e-7,'maxiter':120})
        wallet,cons=candidate(L,d,float(r.x),fixed,flash_bps); row=(cons,wallet,d,float(r.x))
        if row[0]>best[0]:best=row
    return best

def outside_flow(pool,L,symbol,rng,scale):
    if scale<=0:return
    n=float(rng.lognormal(mean=math.log(scale),sigma=.65)); buy=bool(int(rng.integers(0,2))==0)
    if symbol=='C':
        if buy:
            u=min(n,L.external_u*.001); tout=pool.usdc_to_token(u); L.external_u-=u; L.external_c+=tout
        else:
            spot=pool.usdc/pool.token; tin=min(n/max(spot,1e-18),L.external_c*.001); uout=pool.token_to_usdc(tin); L.external_c-=tin; L.external_u+=uout
    else:
        if buy:
            u=min(n,L.external_u*.001); tout=pool.usdc_to_token(u); L.external_u-=u; L.external_x+=tout
        else:
            spot=pool.usdc/pool.token; tin=min(n/max(spot,1e-18),L.external_x*.001); uout=pool.token_to_usdc(tin); L.external_x-=tin; L.external_u+=uout

def add_pol(L,wallet_profit,share=.80):
    deposit=min(max(wallet_profit*share,0.0),L.treasury_u); half=deposit/2
    if half<=0:return 0.0
    c_need=half*L.cu.token/L.cu.usdc; x_need=half*L.xu.token/L.xu.usdc
    scale=min(1.0,L.protocol_free_c/c_need if c_need>0 else 1.0,L.protocol_free_x/x_need if x_need>0 else 1.0)
    half*=scale; c_need=half*L.cu.token/L.cu.usdc; x_need=half*L.xu.token/L.xu.usdc
    L.treasury_u-=2*half; L.protocol_free_c-=c_need; L.protocol_free_x-=x_need
    L.cu.add_protocol_lp(half,c_need); L.xu.add_protocol_lp(half,x_need)
    return 2*half

def neutral_gradient_reset(L,mint_c=20.0,mint_x=0.0):
    c0,x0=L.cx.c,L.cx.x; sc0,sx0=L.supply_c,L.supply_x
    L.supply_c+=mint_c; L.supply_x+=mint_x
    temp_c,temp_x=c0+mint_c,x0+mint_x
    assert temp_c>=c0 and temp_x>=x0
    L.cx.c,L.cx.x=c0,x0
    L.supply_c-=mint_c; L.supply_x-=mint_x
    assert L.cx.c==c0 and L.cx.x==x0 and L.supply_c==sc0 and L.supply_x==sx0

def initial_ledger():
    cu=Pool(1e6,1e6,.003,name='CU'); xu=Pool(1e6,1e6,.003,name='XU'); cx=CrossPool(5e5,5e5,.0005)
    pfc=pfx=2e6; ec=ex=1e7
    sc=cu.token+cx.c+pfc+ec; sx=xu.token+cx.x+pfx+ex
    return Ledger(cu,xu,cx,1000.0,pfc,pfx,50e6,ec,ex,sc,sx,sc)

def run(cycles=5000,seed=42,scale=3500.0,lp_share=.80,outdir='results_strict_v22'):
    rng=np.random.default_rng(seed); L=initial_ledger(); c0,x0,u0=L.totals(); L.assert_conservation(c0,x0,u0)
    start_hard=L.hard_tvl(); accepted=0; cumulative=0.0; rows=[]
    noedge=optimize(L) if scale<=0 else None
    if noedge is not None: assert noedge[0]<.01 and noedge[1]<.01
    for i in range(1,cycles+1):
        outside_flow(L.cu,L,'C',rng,scale); outside_flow(L.xu,L,'X',rng,scale); L.assert_conservation(c0,x0,u0)
        hard_pre=L.hard_tvl(); cons,wallet,d,amt=noedge if scale<=0 else optimize(L); ok=cons>=.01 and wallet>=.01
        if ok:
            out,_=route(L,d,amt,True); wallet=out-amt-.05; L.treasury_u+=wallet; L.external_u+=.05
            realized=L.hard_tvl()-hard_pre
            assert abs(realized-cons)<=max(1e-5,abs(cons)*2e-7)
            cumulative+=realized; accepted+=1; add_pol(L,wallet,lp_share)
            neutral_gradient_reset(L,20.0 if i%2 else 0.0,0.0 if i%2 else 20.0)
        else:
            wallet=realized=0.0; d=-1; amt=0.0
        L.assert_conservation(c0,x0,u0); hard=L.hard_tvl(); nav=L.solvency_nav()
        rows.append(dict(cycle=i,executed=int(ok),direction=d,trade_usdc=amt,wallet_profit=wallet,consolidated_trade_profit=realized,
            cumulative_external_pnl=cumulative,hard_tvl_usdc=hard,treasury_usdc=L.treasury_u,pol_usdc=L.cu.protocol_usdc()+L.xu.protocol_usdc(),
            cu_protocol_lp_share=L.cu.pshare(),xu_protocol_lp_share=L.xu.pshare(),protocol_free_rubc=L.protocol_free_c,
            protocol_free_rubx=L.protocol_free_x,rubc_supply=L.supply_c,rubx_supply=L.supply_x,flash_debt_end=0.0,solvency_nav_usdc=nav,
            cu_usdc_reserve=L.cu.usdc,xu_usdc_reserve=L.xu.usdc,cx_rubc_reserve=L.cx.c,cx_rubx_reserve=L.cx.x,external_usdc=L.external_u))
    summary=dict(version='V2.2_STRICT_LEDGER',cycles=cycles,accepted=accepted,acceptance_rate=accepted/cycles,hard_tvl_start=start_hard,
        hard_tvl_end=rows[-1]['hard_tvl_usdc'],hard_tvl_gain=rows[-1]['hard_tvl_usdc']-start_hard,cumulative_consolidated_trade_pnl=cumulative,
        treasury_end=L.treasury_u,pol_hard_end=L.cu.protocol_usdc()+L.xu.protocol_usdc(),cu_protocol_lp_share=L.cu.pshare(),xu_protocol_lp_share=L.xu.pshare(),
        protocol_free_rubc_end=L.protocol_free_c,protocol_free_rubx_end=L.protocol_free_x,rubc_supply_delta=L.supply_c-c0,rubx_supply_delta=L.supply_x-x0,
        max_flash_debt_end=0.0,solvency_nav_end=L.solvency_nav(),asset_conservation='PASS')
    p=Path(outdir);p.mkdir(parents=True,exist_ok=True)
    with (p/'cycles.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    (p/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--cycles',type=int,default=5000);a.add_argument('--seed',type=int,default=42)
    a.add_argument('--scale',type=float,default=3500.0);a.add_argument('--out',default='results_strict_v22');z=a.parse_args()
    run(z.cycles,z.seed,z.scale,outdir=z.out)
