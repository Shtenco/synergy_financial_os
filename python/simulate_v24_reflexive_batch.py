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
    # Exactly $1 genesis hard cash: $0.5 in each USD price kernel.
    cu,xu=Pool(.5,.5),Pool(.5,.5)
    treasury=0.; inv_c=inv_x=0.; sc=sx=1_000_000.
    initial_hard=1.; initial_mark=initial_hard+sc*cu.price+sx*xu.price
    rows=[]

    for i in range(1,quanta+1):
        pre_c,pre_x=cu.price,xu.price
        active=cu if i%2 else xu

        # SAME 200-USDC flash principal is recycled every microcycle.
        sh=active.add_temp(flash)
        active.buy(buyer)
        temp_u,_=active.remove(sh)           # proportional REMOVE preserves spot price
        treasury += temp_u-flash             # 200 immediately reusable

        # Internal triangle synchronizer: move owned USDC to lower leg,
        # buy token and burn. Consolidated canonical cash is unchanged.
        hi=max(cu.price,xu.price)
        if cu.price<hi:
            spend,burn=cu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sc-=burn
        if xu.price<hi:
            spend,burn=xu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sx-=burn

        if policy:
            # +1% price => sell 1% ACTIVE EMISSION BAND.
            # Downside branch in the execution kernel uses 2x buy/burn per -1%.
            for sym,pool,pre in [('C',cu,pre_c),('X',xu,pre_x)]:
                rise=max(pool.price/pre-1.,0.)
                if rise:
                    active_emission=band*pool.token
                    q=rise*active_emission
                    treasury += pool.sell(q)
                    if sym=='C':sc+=q
                    else:sx+=q

            hi=max(cu.price,xu.price)
            if cu.price<hi:
                spend,burn=cu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sc-=burn
            if xu.price<hi:
                spend,burn=xu.buy_to_price(hi); assert spend<=treasury+1e-9; treasury-=spend; sx-=burn

        # Gradient/depth recharge: proportionally REMOVE excess persistent LP
        # until each USD price kernel is back at $0.5. Price is unchanged.
        u,t=cu.reset_usdc_depth(kernel_usdc); treasury+=u; inv_c+=t
        u,t=xu.reset_usdc_depth(kernel_usdc); treasury+=u; inv_x+=t

        hard=treasury+cu.usdc+xu.usdc
        expected=initial_hard+i*buyer
        assert abs(hard-expected)<1e-8
        marked=hard+sc*cu.price+sx*xu.price
        rows.append(dict(
            quantum=i,external_usdc_cumulative=i*buyer,hard_cash_usdc=hard,
            rubc_price=cu.price,rubx_price=xu.price,reserve_vault_usdc=treasury,
            cu_kernel_usdc=cu.usdc,xu_kernel_usdc=xu.usdc,
            protocol_inventory_rubc=inv_c,protocol_inventory_rubx=inv_x,
            rubc_supply=sc,rubx_supply=sx,spot_marked_nav_usdc=marked,
            incremental_marked_nav=marked-initial_mark,
            marked_multiplier_per_external_usdc=(marked-initial_mark)/(i*buyer),
            flash_principal_recycled=flash
        ))

    s=dict(
        version='V2.4_REFLEXIVE_SINGLE_BATCH_CONSTANT_DEPTH',quanta=quanta,
        genesis_hard_cash_usdc=initial_hard,flash_principal_usdc=flash,
        cumulative_temp_lp_notional_usdc=flash*quanta,external_usdc_total=quanta*buyer,
        hard_cash_end=rows[-1]['hard_cash_usdc'],reserve_vault_end=rows[-1]['reserve_vault_usdc'],
        price_kernel_usdc_end=rows[-1]['cu_kernel_usdc']+rows[-1]['xu_kernel_usdc'],
        hard_cash_multiplier_per_external_usdc=1.0,
        rubc_price_end=rows[-1]['rubc_price'],rubx_price_end=rows[-1]['rubx_price'],
        spot_marked_nav_end=rows[-1]['spot_marked_nav_usdc'],incremental_marked_nav=rows[-1]['incremental_marked_nav'],
        average_marked_multiplier_per_external_usdc=rows[-1]['marked_multiplier_per_external_usdc'],
        rubc_supply_end=sc,rubx_supply_end=sx,flash_debt_end=0.,cash_conservation='PASS',
        note='Marked NAV is a reflexive marginal-price valuation, not withdrawable canonical USDC.'
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
