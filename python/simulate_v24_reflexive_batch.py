from __future__ import annotations
from dataclasses import dataclass
import argparse, csv, json, math
from pathlib import Path

@dataclass
class Pool:
    token: float
    usdc: float
    @property
    def price(self): return self.usdc/self.token
    def add_temp(self,u):
        t=u*self.token/self.usdc; sh=u/(self.usdc+u); self.usdc+=u; self.token+=t; return sh
    def remove(self,sh):
        u=self.usdc*sh; t=self.token*sh; self.usdc*=1-sh; self.token*=1-sh; return u,t
    def buy(self,u):
        k=self.token*self.usdc; self.usdc+=u; nt=k/self.usdc; out=self.token-nt; self.token=nt; return out
    def sell(self,t):
        k=self.token*self.usdc; self.token+=t; nu=k/self.token; out=self.usdc-nu; self.usdc=nu; return out
    def buy_to_price(self,p):
        if self.price>=p:return 0.,0.
        k=self.token*self.usdc; nu=math.sqrt(k*p); nt=math.sqrt(k/p)
        spend=nu-self.usdc; out=self.token-nt; self.usdc=nu; self.token=nt; return spend,out
    def reset_usdc_depth(self,target):
        if self.usdc<=target:return 0.,0.
        frac=1-target/self.usdc; u=self.usdc*frac; t=self.token*frac
        self.usdc-=u; self.token-=t; return u,t

def run(quanta=100,buyer=1.,flash=200.,band=.10,policy=True,kernel_usdc=.5,out='results/v24_reflexive'):
    cu,xu=Pool(.5,.5),Pool(.5,.5)
    treasury=0.; external_c=external_x=0.; sc=sx=1_000_000.
    initial_hard=1.; initial_protocol_mark=initial_hard+sc*cu.price+sx*xu.price
    rows=[]

    for i in range(1,quanta+1):
        pre_c,pre_x=cu.price,xu.price
        active=cu if i%2 else xu
        sh=active.add_temp(flash)
        bought=active.buy(buyer)
        if i%2:external_c+=bought
        else:external_x+=bought
        temp_u,_=active.remove(sh); treasury+=temp_u-flash

        hi=max(cu.price,xu.price)
        if cu.price<hi:
            spend,burn=cu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sc-=burn
        if xu.price<hi:
            spend,burn=xu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sx-=burn

        if policy:
            for sym,pool,pre in [('C',cu,pre_c),('X',xu,pre_x)]:
                rise=max(pool.price/pre-1.,0.)
                if rise:
                    q=rise*(band*pool.token); treasury+=pool.sell(q)
                    if sym=='C':sc+=q
                    else:sx+=q
            hi=max(cu.price,xu.price)
            if cu.price<hi:
                spend,burn=cu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sc-=burn
            if xu.price<hi:
                spend,burn=xu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sx-=burn

        # Constant-depth recharge: sweep excess permanent LP to reserve.
        u,_=cu.reset_usdc_depth(kernel_usdc); treasury+=u
        u,_=xu.reset_usdc_depth(kernel_usdc); treasury+=u

        hard=treasury+cu.usdc+xu.usdc; assert abs(hard-(1.+i*buyer))<1e-8
        protocol_c=sc-external_c; protocol_x=sx-external_x
        assert protocol_c>=0 and protocol_x>=0
        protocol_mark=hard+protocol_c*cu.price+protocol_x*xu.price
        systemic_mark=hard+sc*cu.price+sx*xu.price
        rows.append(dict(
            quantum=i,external_usdc_cumulative=i*buyer,hard_cash_usdc=hard,
            rubc_price=cu.price,rubx_price=xu.price,reserve_vault_usdc=treasury,
            cu_kernel_usdc=cu.usdc,xu_kernel_usdc=xu.usdc,rubc_supply=sc,rubx_supply=sx,
            external_rubc=external_c,external_rubx=external_x,
            protocol_owned_rubc=protocol_c,protocol_owned_rubx=protocol_x,
            protocol_ownership_rubc_pct=100*protocol_c/sc,protocol_ownership_rubx_pct=100*protocol_x/sx,
            protocol_marked_tvl_usdc=protocol_mark,systemic_market_value_usdc=systemic_mark,
            protocol_incremental_marked_tvl=protocol_mark-initial_protocol_mark,
            protocol_marked_multiplier_per_external_usdc=(protocol_mark-initial_protocol_mark)/(i*buyer),
            flash_principal_recycled=flash
        ))

    r=rows[-1]
    s=dict(
        version='V2.4_REFLEXIVE_SINGLE_BATCH_PROTOCOL_MARKED_TVL',quanta=quanta,
        genesis_hard_cash_usdc=1.,flash_principal_usdc=flash,cumulative_temp_lp_notional_usdc=flash*quanta,
        external_usdc_total=quanta*buyer,hard_cash_end=r['hard_cash_usdc'],reserve_vault_end=r['reserve_vault_usdc'],
        price_kernel_usdc_end=r['cu_kernel_usdc']+r['xu_kernel_usdc'],hard_cash_multiplier_per_external_usdc=1.0,
        rubc_price_end=r['rubc_price'],rubx_price_end=r['rubx_price'],protocol_owned_rubc_end=r['protocol_owned_rubc'],
        protocol_owned_rubx_end=r['protocol_owned_rubx'],protocol_ownership_rubc_pct=r['protocol_ownership_rubc_pct'],
        protocol_ownership_rubx_pct=r['protocol_ownership_rubx_pct'],protocol_marked_tvl_end=r['protocol_marked_tvl_usdc'],
        protocol_incremental_marked_tvl=r['protocol_incremental_marked_tvl'],
        average_protocol_marked_multiplier_per_external_usdc=r['protocol_marked_multiplier_per_external_usdc'],
        systemic_market_value_end=r['systemic_market_value_usdc'],rubc_supply_end=sc,rubx_supply_end=sx,
        external_rubc_end=external_c,external_rubx_end=external_x,flash_debt_end=0.,cash_conservation='PASS',
        note='ProtocolMarkedTVL marks protocol-owned inventory at marginal internal prices; it is not immediately withdrawable canonical USDC.'
    )
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    with (p/'cycles.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    (p/'summary.json').write_text(json.dumps(s,indent=2));print(json.dumps(s,indent=2));return s

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--quanta',type=int,default=100);a.add_argument('--buyer',type=float,default=1.)
    a.add_argument('--flash',type=float,default=200.);a.add_argument('--band',type=float,default=.10);a.add_argument('--kernel-usdc',type=float,default=.5)
    a.add_argument('--no-policy',action='store_true');a.add_argument('--out',default='results/v24_reflexive');z=a.parse_args()
    run(z.quanta,z.buyer,z.flash,z.band,not z.no_policy,z.kernel_usdc,z.out)
