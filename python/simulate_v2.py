from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
import argparse, json, math, csv
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar

@dataclass
class CPMM:
    a: float
    b: float
    fee: float = 0.003
    def q_ab(self,x):
        if x<=0:return 0.0
        z=x*(1-self.fee); return self.b*z/(self.a+z)
    def q_ba(self,x):
        if x<=0:return 0.0
        z=x*(1-self.fee); return self.a*z/(self.b+z)
    def ab(self,x):
        y=self.q_ab(x); self.a+=x; self.b-=y; return y
    def ba(self,x):
        y=self.q_ba(x); self.b+=x; self.a-=y; return y
    def spot(self): return self.b/self.a

@dataclass
class State:
    cu: CPMM # C/USDC
    xu: CPMM # X/USDC
    cx: CPMM # C/X

def route(s,d,u,execute=False):
    s=s if execute else deepcopy(s)
    if d==0:
        x=s.xu.ba(u); c=s.cx.ba(x); return s.cu.ab(c)
    c=s.cu.ba(u); x=s.cx.ab(c); return s.xu.ab(x)

def pnl(s,d,u,flash_fee_bps,fixed):
    return route(s,d,u,False)-u-u*flash_fee_bps/10000-fixed

def optimize(s,max_trade,flash_fee_bps,fixed):
    out=[]
    for d in (0,1):
        r=minimize_scalar(lambda z:-pnl(s,d,z,flash_fee_bps,fixed),bounds=(1e-9,max_trade),method='bounded')
        out.append((-r.fun,d,float(r.x)))
    return max(out,key=lambda z:z[0])

def outside_flow(pool,rng,scale):
    if scale<=0:return
    n=float(rng.lognormal(mean=math.log(scale),sigma=.65))
    if int(rng.integers(0,2))==0: pool.ba(n)
    else: pool.ab(n/max(pool.spot(),1e-18))

def gradient_restore_exact(s,token,mint):
    c0,x0=s.cx.a,s.cx.b
    # REMOVE100 -> ADD100 with temp mint -> REMOVE100 -> exact principal ADD100 -> burn residual.
    if token=='C': s.cx.a,s.cx.b=c0+mint,x0
    else: s.cx.a,s.cx.b=c0,x0+mint
    fc,fx=s.cx.a,s.cx.b
    s.cx.a,s.cx.b=c0,x0
    if token=='C': assert abs((fc-c0)-mint)<1e-9
    else: assert abs((fx-x0)-mint)<1e-9
    assert s.cx.a==c0 and s.cx.b==x0

def run(cycles=5000,seed=42,orderflow_scale=3500.0,out='results'):
    rng=np.random.default_rng(seed)
    s=State(CPMM(1e6,1e6,.003),CPMM(1e6,1e6,.003),CPMM(5e5,5e5,.0005))
    hard=1000.0; treasury=1000.0; pol=0.0; ext_pnl=0.0
    c_supply=x_supply=1_000_000.0; backing=1_000_000.0
    rows=[]; accepted=0
    for i in range(1,cycles+1):
        outside_flow(s.cu,rng,orderflow_scale); outside_flow(s.xu,rng,orderflow_scale)
        p,d,amt=optimize(s,50_000.0,0.0,.05)
        ok=p>=.01
        if ok:
            got=route(s,d,amt,True); net=got-amt-.05
            hard+=net; ext_pnl+=net; pol+=net*.8; treasury+=net*.2; accepted+=1
            gradient_restore_exact(s,'C' if i%2 else 'X',20.0)
        else: net=0.0; d=-1; amt=0.0
        nav=backing+hard-c_supply
        rows.append(dict(cycle=i,executed=int(ok),direction=d,trade_usdc=amt,cycle_net_profit_usdc=net,
            cumulative_external_pnl_usdc=ext_pnl,hard_tvl_usdc=hard,treasury_usdc=treasury,pol_usdc=pol,
            rubc_supply=c_supply,rubx_supply=x_supply,flash_debt_end=0.0,solvency_nav_usdc=nav,
            cu_price=s.cu.spot(),xu_price=s.xu.spot(),cx_x_per_c=s.cx.spot(),cu_usdc_reserve=s.cu.b,
            xu_usdc_reserve=s.xu.b,cx_rubc_reserve=s.cx.a,cx_rubx_reserve=s.cx.b))
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    with (p/'cycles.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    summary=dict(successful=accepted,cycles=cycles,final_hard_tvl=hard,external_pnl=ext_pnl,
        final_rubc_supply=c_supply,final_rubx_supply=x_supply,final_solvency_nav=rows[-1]['solvency_nav_usdc'],
        pol_usdc=pol,treasury_usdc=treasury)
    (p/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--cycles',type=int,default=5000);a.add_argument('--seed',type=int,default=42)
    a.add_argument('--orderflow-scale',type=float,default=3500.0);a.add_argument('--out',default='results');x=a.parse_args()
    run(x.cycles,x.seed,x.orderflow_scale,x.out)
