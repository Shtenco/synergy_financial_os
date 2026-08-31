from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

base=Path(__file__).resolve().parents[1]/'results'
df=pd.read_csv(base/'cycles.csv')
plots=[
 ('hard_tvl_curve.png','HardTVL',['hard_tvl_usdc'],'USDC'),
 ('external_pnl_curve.png','Cumulative external PnL',['cumulative_external_pnl_usdc'],'USDC'),
 ('supply_curves.png','RUBC / RUBX supply',['rubc_supply','rubx_supply'],'Token supply'),
 ('lp_reserves_curve.png','Pool reserves',['cu_usdc_reserve','xu_usdc_reserve','cx_rubc_reserve','cx_rubx_reserve'],'Reserve units'),
 ('flash_debt_curve.png','Flash debt at cycle end',['flash_debt_end'],'USDC'),
 ('solvency_nav_curve.png','Solvency NAV',['solvency_nav_usdc'],'USDC'),
]
for fn,title,cols,ylabel in plots:
    fig,ax=plt.subplots(figsize=(9,5))
    for c in cols: ax.plot(df.cycle,df[c],label=c)
    ax.set(title=title,xlabel='Cycle',ylabel=ylabel)
    if len(cols)>1: ax.legend()
    ax.grid(True,alpha=.25); fig.tight_layout(); fig.savefig(base/fn,dpi=160); plt.close(fig)
