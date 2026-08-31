from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import numpy as np
from simulate_strict_v22 import initial_ledger, outside_flow, route

FLASH = 200.0
FIXED_COST = 0.05
MIN_DIVIDEND = 0.01


def best_fixed_200(L):
    """Choose the better wallet-profit direction for one fixed 200-USDC attempt."""
    best = None
    for d in (0, 1):
        out, _ = route(L, d, FLASH, False)
        dividend = out - FLASH - FIXED_COST
        row = (dividend, d, out)
        if best is None or row[0] > best[0]:
            best = row
    return best


def run(cycles=5000, seed=42, scale=3500.0, outdir='results/v23_fixed200'):
    rng = np.random.default_rng(seed)
    L = initial_ledger()
    c0, x0, u0 = L.totals()
    L.assert_conservation(c0, x0, u0)

    # In V2.3 treasury_u is the canonical-USDC HardTVL dividend vault.
    start_hard = L.treasury_u
    executed = 0
    cumulative_dividends = 0.0
    min_realized = float('inf')
    rows = []

    for i in range(1, cycles + 1):
        outside_flow(L.cu, L, 'C', rng, scale)
        outside_flow(L.xu, L, 'X', rng, scale)
        L.assert_conservation(c0, x0, u0)

        dividend_quote, direction, quoted_out = best_fixed_200(L)
        ok = dividend_quote >= MIN_DIVIDEND

        if ok:
            flash_debt_during = FLASH
            out, _ = route(L, direction, FLASH, True)
            assert abs(out - quoted_out) < 1e-7
            dividend = out - FLASH - FIXED_COST
            assert dividend >= MIN_DIVIDEND

            # Atomic conceptual settlement:
            #   (1) Balancer principal 200 is repaid at zero fee.
            #   (2) FIXED_COST is paid to an external sink.
            #   (3) 100% of remaining canonical USDC goes to HardTVLDividendVaultV23.
            L.external_u += FIXED_COST
            L.treasury_u += dividend
            flash_debt_end = 0.0
            executed += 1
            cumulative_dividends += dividend
            min_realized = min(min_realized, dividend)
        else:
            dividend = 0.0
            direction = -1
            flash_debt_during = 0.0
            flash_debt_end = 0.0

        L.assert_conservation(c0, x0, u0)
        hard = L.treasury_u
        assert abs((hard - start_hard) - cumulative_dividends) <= 1e-6

        rows.append({
            'cycle': i,
            'executed': int(ok),
            'direction': direction,
            'flash_principal': FLASH if ok else 0.0,
            'flash_fee': 0.0,
            'flash_debt_during': flash_debt_during,
            'flash_debt_end': flash_debt_end,
            'dividend_usdc': dividend,
            'cumulative_dividends': cumulative_dividends,
            'hard_tvl_usdc': hard,
            'rubc_supply': L.supply_c,
            'rubx_supply': L.supply_x,
            'solvency_nav_usdc': hard,
        })

    summary = {
        'version': 'V2.3_BALANCER_V2_ZERO_FEE_FIXED_200_CONTRACT_EXACT',
        'attempts': cycles,
        'executed': executed,
        'execution_rate': executed / cycles,
        'flash_principal_per_executed_cycle': FLASH,
        'flash_fee_per_cycle': 0.0,
        'min_dividend_gate': MIN_DIVIDEND,
        'min_realized_dividend': 0.0 if executed == 0 else min_realized,
        'cumulative_dividends': cumulative_dividends,
        'hard_tvl_start': start_hard,
        'hard_tvl_end': L.treasury_u,
        'hard_tvl_gain': L.treasury_u - start_hard,
        'max_flash_debt_end': 0.0,
        'rubc_supply_delta': L.supply_c - c0,
        'rubx_supply_delta': L.supply_x - x0,
        'solvency_nav_end': L.treasury_u,
        'asset_conservation': 'PASS',
        'hard_tvl_equals_start_plus_dividends': abs((L.treasury_u - start_hard) - cumulative_dividends) <= 1e-6,
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
