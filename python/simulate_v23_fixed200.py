from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import numpy as np
from simulate_strict_v22 import initial_ledger, outside_flow, route, add_pol

FLASH = 200.0
FIXED_COST = 0.05
MIN_DIVIDEND = 0.01


def best_fixed_200(L):
    best = None
    for d in (0, 1):
        out, t = route(L, d, FLASH, False)
        wallet = out - FLASH - FIXED_COST
        consolidated = wallet + (
            t.cu.protocol_usdc() + t.xu.protocol_usdc()
            - L.cu.protocol_usdc() - L.xu.protocol_usdc()
        )
        row = (consolidated, wallet, d, out)
        if best is None or row[0] > best[0]:
            best = row
    return best


def run(cycles=5000, seed=42, scale=3500.0, lp_share=.80, outdir='results/v23_fixed200'):
    rng = np.random.default_rng(seed)
    L = initial_ledger()
    c0, x0, u0 = L.totals()
    L.assert_conservation(c0, x0, u0)
    start_hard = L.hard_tvl()
    executed = 0
    cumulative_dividends = 0.0
    min_realized = float('inf')
    rows = []

    for i in range(1, cycles + 1):
        outside_flow(L.cu, L, 'C', rng, scale)
        outside_flow(L.xu, L, 'X', rng, scale)
        L.assert_conservation(c0, x0, u0)

        hard_pre = L.hard_tvl()
        consolidated, wallet, d, quoted_out = best_fixed_200(L)
        ok = wallet >= MIN_DIVIDEND and consolidated >= MIN_DIVIDEND

        if ok:
            flash_debt_during = FLASH
            out, _ = route(L, d, FLASH, True)
            assert abs(out - quoted_out) < 1e-7
            wallet = out - FLASH - FIXED_COST
            assert wallet >= MIN_DIVIDEND

            L.treasury_u += wallet
            L.external_u += FIXED_COST
            add_pol(L, wallet, lp_share)
            flash_debt_end = 0.0
            executed += 1
            cumulative_dividends += wallet
            min_realized = min(min_realized, wallet)
        else:
            wallet = 0.0
            d = -1
            flash_debt_during = 0.0
            flash_debt_end = 0.0

        L.assert_conservation(c0, x0, u0)
        hard = L.hard_tvl()
        if ok:
            assert hard >= hard_pre + MIN_DIVIDEND - 1e-9

        rows.append({
            'cycle': i, 'executed': int(ok), 'direction': d,
            'flash_principal': FLASH if ok else 0.0, 'flash_fee': 0.0,
            'flash_debt_during': flash_debt_during, 'flash_debt_end': flash_debt_end,
            'dividend_usdc': wallet, 'cumulative_dividends': cumulative_dividends,
            'hard_tvl_usdc': hard, 'treasury_usdc': L.treasury_u,
            'pol_usdc': L.cu.protocol_usdc() + L.xu.protocol_usdc(),
            'rubc_supply': L.supply_c, 'rubx_supply': L.supply_x,
            'solvency_nav_usdc': L.solvency_nav(),
        })

    summary = {
        'version': 'V2.3_BALANCER_V2_ZERO_FEE_FIXED_200',
        'attempts': cycles,
        'executed': executed,
        'execution_rate': executed / cycles,
        'flash_principal_per_executed_cycle': FLASH,
        'flash_fee_per_cycle': 0.0,
        'min_dividend_gate': MIN_DIVIDEND,
        'min_realized_dividend': 0.0 if executed == 0 else min_realized,
        'cumulative_dividends': cumulative_dividends,
        'hard_tvl_start': start_hard,
        'hard_tvl_end': L.hard_tvl(),
        'hard_tvl_gain': L.hard_tvl() - start_hard,
        'treasury_end': L.treasury_u,
        'pol_hard_end': L.cu.protocol_usdc() + L.xu.protocol_usdc(),
        'max_flash_debt_end': 0.0,
        'rubc_supply_delta': L.supply_c - c0,
        'rubx_supply_delta': L.supply_x - x0,
        'solvency_nav_end': L.solvency_nav(),
        'asset_conservation': 'PASS',
    }

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'cycles.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(rows)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--cycles', type=int, default=5000)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--scale', type=float, default=3500.0)
    p.add_argument('--out', default='results/v23_fixed200')
    a = p.parse_args()
    run(a.cycles, a.seed, a.scale, outdir=a.out)
