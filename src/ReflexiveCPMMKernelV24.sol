// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20KernelV24 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address who) external view returns (uint256);
    function totalSupply() external view returns (uint256);
}

interface IRUBControllerV24 is IERC20KernelV24 {
    function cbMint(address to, uint256 amount) external;
    function cbBurn(uint256 amount) external;
}

interface IReserveVaultKernelV24 {
    function pull(address token, address to, uint256 amount) external;
}

/// @notice Concrete zero-fee research CPMM kernel for the fixed V2.4 topology:
/// RUBC/USDC + RUBX/USDC + RUBC/RUBX.
///
/// It is intentionally protocol-owned. Temporary token-side LP is flash-minted
/// by the kernel, completely repaid/burned at REMOVE100, while canonical USDC
/// is borrowed externally only by the enclosing Balancer callback.
contract ReflexiveCPMMKernelV24 {
    uint256 private constant ONE_TOKEN = 1e18;
    uint256 private constant ONE_USDC = 1e6;
    uint256 private constant PRICE_SCALE = 1e18;
    uint256 private constant PRICE_RAW_SCALE = 1e30; // 1e18 price * 1e12 decimals bridge
    uint256 private constant BPS = 10_000;

    struct USDPool {
        uint256 tokenReserve; // 18 decimals
        uint256 usdcReserve;  // 6 decimals
    }

    struct CrossPool {
        uint256 rubcReserve;
        uint256 rubxReserve;
    }

    struct TempLP {
        bool open;
        uint8 leg;
        uint256 principalUSDC;
        uint256 shareNumerator;
        uint256 shareDenominator;
        uint256 tempMint;
    }

    address public owner;
    address public engine;

    IERC20KernelV24 public immutable USDC;
    IRUBControllerV24 public immutable RUBC;
    IRUBControllerV24 public immutable RUBX;
    IReserveVaultKernelV24 public immutable reserveVault;
    address public immutable reserveVaultAddress;

    USDPool public rubcUSDC;
    USDPool public rubxUSDC;
    CrossPool public rubcRubx;
    TempLP public tempLP;

    uint256 public referencePriceRUBC;
    uint256 public referencePriceRUBX;
    bool public initialized;

    event Initialized(uint256 hardCashUSDC, uint256 priceRUBC, uint256 priceRUBX);
    event TemporaryLiquidityOpened(uint8 indexed leg, uint256 usdc, uint256 tempMint);
    event BuyerQuantum(uint8 indexed leg, uint256 usdcIn, uint256 tokenOut, address indexed recipient);
    event TemporaryLiquidityClosed(uint8 indexed leg, uint256 principalReturned, uint256 surplusSwept);
    event Synchronized(uint256 usdcMoved, uint256 burnedRUBC, uint256 burnedRUBX);
    event MonetaryPolicy(int256 rubcSupplyDelta, int256 rubxSupplyDelta);
    event KernelDepthReset(uint256 targetUSDCPerLeg, uint256 sweptUSDC);

    modifier onlyOwner() { require(msg.sender == owner, "OWNER"); _; }
    modifier onlyEngine() { require(msg.sender == engine, "ENGINE"); _; }

    constructor(
        address owner_,
        IERC20KernelV24 usdc_,
        IRUBControllerV24 rubc_,
        IRUBControllerV24 rubx_,
        IReserveVaultKernelV24 reserveVault_
    ) {
        require(owner_ != address(0), "OWNER_ZERO");
        require(address(usdc_) != address(0) && address(rubc_) != address(0) && address(rubx_) != address(0), "TOKEN_ZERO");
        require(address(reserveVault_) != address(0), "VAULT_ZERO");
        owner = owner_;
        USDC = usdc_;
        RUBC = rubc_;
        RUBX = rubx_;
        reserveVault = reserveVault_;
        reserveVaultAddress = address(reserveVault_);
    }

    function setEngine(address engine_) external onlyOwner {
        require(engine_ != address(0), "ENGINE_ZERO");
        engine = engine_;
    }

    /// @notice Seeds exactly 1 canonical USDC of permanent USD price-kernel
    /// liquidity: 0.5 USDC + 0.5 token on each USD leg. Cross pool is seeded
    /// with 1 RUBC + 1 RUBX from locked protocol inventory.
    function initialize() external onlyOwner {
        require(!initialized, "INITIALIZED");
        require(USDC.transferFrom(msg.sender, address(this), ONE_USDC), "SEED_USDC");

        reserveVault.pull(address(RUBC), address(this), 15e17); // 0.5 USD leg + 1 cross
        reserveVault.pull(address(RUBX), address(this), 15e17);

        rubcUSDC = USDPool({tokenReserve: 5e17, usdcReserve: 5e5});
        rubxUSDC = USDPool({tokenReserve: 5e17, usdcReserve: 5e5});
        rubcRubx = CrossPool({rubcReserve: 1e18, rubxReserve: 1e18});

        referencePriceRUBC = PRICE_SCALE;
        referencePriceRUBX = PRICE_SCALE;
        initialized = true;
        emit Initialized(hardCashUSDC(), referencePriceRUBC, referencePriceRUBX);
    }

    // ---------------------------------------------------------------------
    // Fixed buyer path
    // ---------------------------------------------------------------------

    function openTemporaryLiquidity(uint8 leg, uint256 usdcPrincipal) external onlyEngine {
        require(initialized && !tempLP.open, "TEMP_STATE");
        require(leg < 2 && usdcPrincipal > 0, "TEMP_ARGS");
        USDPool storage p = _pool(leg);

        uint256 tokenIn = usdcPrincipal * p.tokenReserve / p.usdcReserve;
        require(tokenIn > 0, "TEMP_TOKEN_ZERO");
        require(USDC.transferFrom(msg.sender, address(this), usdcPrincipal), "TEMP_USDC_PULL");

        IRUBControllerV24 token = leg == 0 ? RUBC : RUBX;
        token.cbMint(address(this), tokenIn);

        uint256 denom = p.usdcReserve + usdcPrincipal;
        p.usdcReserve = denom;
        p.tokenReserve += tokenIn;

        tempLP = TempLP({
            open: true,
            leg: leg,
            principalUSDC: usdcPrincipal,
            shareNumerator: usdcPrincipal,
            shareDenominator: denom,
            tempMint: tokenIn
        });
        emit TemporaryLiquidityOpened(leg, usdcPrincipal, tokenIn);
    }

    function executeBuyerQuantum(
        uint8 leg,
        uint256 buyerUSDC,
        address tokenRecipient,
        uint256 minTokenOut
    ) external onlyEngine returns (uint256 tokenOut) {
        require(tempLP.open && tempLP.leg == leg, "TEMP_NOT_OPEN");
        require(tokenRecipient != address(0) && buyerUSDC > 0, "BUY_ARGS");
        USDPool storage p = _pool(leg);
        require(USDC.transferFrom(msg.sender, address(this), buyerUSDC), "BUYER_USDC_PULL");

        uint256 k = p.tokenReserve * p.usdcReserve;
        uint256 newUSDC = p.usdcReserve + buyerUSDC;
        uint256 newToken = k / newUSDC;
        tokenOut = p.tokenReserve - newToken;
        require(tokenOut >= minTokenOut && tokenOut > 0, "BUY_SLIPPAGE");
        p.usdcReserve = newUSDC;
        p.tokenReserve = newToken;

        IERC20KernelV24 token = leg == 0 ? IERC20KernelV24(address(RUBC)) : IERC20KernelV24(address(RUBX));
        require(token.transfer(tokenRecipient, tokenOut), "BUY_TOKEN_SEND");
        emit BuyerQuantum(leg, buyerUSDC, tokenOut, tokenRecipient);
    }

    /// @notice Removes the exact temporary LP share. Any USDC above the flash
    /// principal is swept to ReserveVault. Temporary token mint is then repaid
    /// exactly; if the temporary LP share lost tokens to the buyer, the deficit
    /// is restored from locked protocol inventory before burning.
    function closeTemporaryLiquidity(uint8 leg) external onlyEngine returns (uint256 usdcReturned) {
        TempLP memory t = tempLP;
        require(t.open && t.leg == leg, "TEMP_NOT_OPEN");
        USDPool storage p = _pool(leg);

        uint256 usdcOut = p.usdcReserve * t.shareNumerator / t.shareDenominator;
        uint256 tokenOut = p.tokenReserve * t.shareNumerator / t.shareDenominator;
        require(usdcOut >= t.principalUSDC, "TEMP_PRINCIPAL_LOSS");

        p.usdcReserve -= usdcOut;
        p.tokenReserve -= tokenOut;

        uint256 surplusUSDC = usdcOut - t.principalUSDC;
        require(USDC.transfer(msg.sender, t.principalUSDC), "PRINCIPAL_RETURN");
        if (surplusUSDC > 0) require(USDC.transfer(reserveVaultAddress, surplusUSDC), "SURPLUS_SWEEP");

        IRUBControllerV24 token = leg == 0 ? RUBC : RUBX;
        if (tokenOut < t.tempMint) {
            reserveVault.pull(address(token), address(this), t.tempMint - tokenOut);
        } else if (tokenOut > t.tempMint) {
            require(token.transfer(reserveVaultAddress, tokenOut - t.tempMint), "TOKEN_SURPLUS_SWEEP");
        }
        token.cbBurn(t.tempMint);

        delete tempLP;
        usdcReturned = t.principalUSDC;
        emit TemporaryLiquidityClosed(leg, usdcReturned, surplusUSDC);
    }

    // ---------------------------------------------------------------------
    // Reflexive monetary controller
    // ---------------------------------------------------------------------

    function synchronizeUpward()
        external onlyEngine
        returns (uint256 internalUSDCMoved, uint256 burnedRUBC, uint256 burnedRUBX)
    {
        require(!tempLP.open, "TEMP_OPEN");
        uint256 pc = priceRUBCX18();
        uint256 px = priceRUBXX18();
        if (pc > px) {
            (internalUSDCMoved, burnedRUBX) = _buyLowerToPrice(rubxUSDC, RUBX, pc);
        } else if (px > pc) {
            (internalUSDCMoved, burnedRUBC) = _buyLowerToPrice(rubcUSDC, RUBC, px);
        }
        _recenterCrossPool();
        emit Synchronized(internalUSDCMoved, burnedRUBC, burnedRUBX);
    }

    function applyEmissionPolicy(
        uint16 sellBpsPerUpPct,
        uint16 burnBpsPerDownPct,
        uint16 activeBandBps
    ) external onlyEngine returns (int256 rubcSupplyDelta, int256 rubxSupplyDelta) {
        require(!tempLP.open, "TEMP_OPEN");
        require(activeBandBps > 0 && activeBandBps <= BPS, "BAND");

        rubcSupplyDelta = _applyOnePolicy(
            rubcUSDC, RUBC, referencePriceRUBC,
            sellBpsPerUpPct, burnBpsPerDownPct, activeBandBps
        );
        rubxSupplyDelta = _applyOnePolicy(
            rubxUSDC, RUBX, referencePriceRUBX,
            sellBpsPerUpPct, burnBpsPerDownPct, activeBandBps
        );
        emit MonetaryPolicy(rubcSupplyDelta, rubxSupplyDelta);
    }

    /// @notice Proportionally restores each persistent USD price kernel to a
    /// constant USDC depth. Excess real USDC and token inventory go off-kernel
    /// to ReserveVault. If a leg is too shallow, ReserveVault tops it up in the
    /// same reserve ratio. Marginal price is preserved apart from integer dust.
    function resetPriceKernelDepth(uint256 targetUSDCPerLeg)
        external onlyEngine
        returns (uint256 sweptUSDC, uint256 sweptRUBC, uint256 sweptRUBX)
    {
        require(!tempLP.open && targetUSDCPerLeg > 0, "RESET_STATE");
        (uint256 uC, uint256 tC) = _resetOneDepth(rubcUSDC, RUBC, targetUSDCPerLeg);
        (uint256 uX, uint256 tX) = _resetOneDepth(rubxUSDC, RUBX, targetUSDCPerLeg);
        sweptUSDC = uC + uX;
        sweptRUBC = tC;
        sweptRUBX = tX;

        referencePriceRUBC = priceRUBCX18();
        referencePriceRUBX = priceRUBXX18();
        _recenterCrossPool();
        emit KernelDepthReset(targetUSDCPerLeg, sweptUSDC);
    }

    // ---------------------------------------------------------------------
    // Accounting views
    // ---------------------------------------------------------------------

    function hardCashUSDC() public view returns (uint256) {
        return USDC.balanceOf(reserveVaultAddress) + rubcUSDC.usdcReserve + rubxUSDC.usdcReserve;
    }

    /// @notice Marks only protocol-owned RUBC/RUBX inventory held by the kernel
    /// and ReserveVault. Temporary flash mint must be closed before this metric
    /// is used as a settlement gate.
    function spotMarkedNAVUSDC() public view returns (uint256) {
        uint256 pc = priceRUBCX18();
        uint256 px = priceRUBXX18();
        uint256 protocolC = RUBC.balanceOf(address(this)) + RUBC.balanceOf(reserveVaultAddress);
        uint256 protocolX = RUBX.balanceOf(address(this)) + RUBX.balanceOf(reserveVaultAddress);
        return hardCashUSDC() + _mark(protocolC, pc) + _mark(protocolX, px);
    }

    function systemicMarketValueUSDC() external view returns (uint256) {
        return hardCashUSDC() + _mark(RUBC.totalSupply(), priceRUBCX18()) + _mark(RUBX.totalSupply(), priceRUBXX18());
    }

    function priceRUBCX18() public view returns (uint256) {
        return rubcUSDC.usdcReserve * PRICE_RAW_SCALE / rubcUSDC.tokenReserve;
    }

    function priceRUBXX18() public view returns (uint256) {
        return rubxUSDC.usdcReserve * PRICE_RAW_SCALE / rubxUSDC.tokenReserve;
    }

    function crossPriceRUBCInRUBXX18() external view returns (uint256) {
        return rubcRubx.rubxReserve * PRICE_SCALE / rubcRubx.rubcReserve;
    }

    // ---------------------------------------------------------------------
    // Internals
    // ---------------------------------------------------------------------

    function _pool(uint8 leg) internal view returns (USDPool storage p) {
        if (leg == 0) return rubcUSDC;
        return rubxUSDC;
    }

    function _buyLowerToPrice(USDPool storage p, IRUBControllerV24 token, uint256 targetPrice)
        internal returns (uint256 spendUSDC, uint256 burnToken)
    {
        uint256 current = p.usdcReserve * PRICE_RAW_SCALE / p.tokenReserve;
        if (current >= targetPrice) return (0, 0);

        uint256 k = p.usdcReserve * p.tokenReserve;
        uint256 scaled = targetPrice * k / PRICE_RAW_SCALE;
        uint256 targetU = _sqrt(scaled);
        if (targetU <= p.usdcReserve) return (0, 0);
        spendUSDC = targetU - p.usdcReserve;
        reserveVault.pull(address(USDC), address(this), spendUSDC);

        uint256 oldToken = p.tokenReserve;
        p.usdcReserve = targetU;
        p.tokenReserve = k / targetU;
        burnToken = oldToken - p.tokenReserve;
        if (burnToken > 0) token.cbBurn(burnToken);
    }

    function _applyOnePolicy(
        USDPool storage p,
        IRUBControllerV24 token,
        uint256 referencePrice,
        uint16 sellBpsPerUpPct,
        uint16 burnBpsPerDownPct,
        uint16 activeBandBps
    ) internal returns (int256 supplyDelta) {
        uint256 price = p.usdcReserve * PRICE_RAW_SCALE / p.tokenReserve;
        if (price == referencePrice || referencePrice == 0) return 0;
        uint256 activeBand = p.tokenReserve * activeBandBps / BPS;

        if (price > referencePrice) {
            uint256 rise = price - referencePrice;
            uint256 q = activeBand * rise / referencePrice;
            q = q * sellBpsPerUpPct / 100; // 100 => 1x rise fraction
            if (q == 0) return 0;

            token.cbMint(address(this), q);
            uint256 k = p.usdcReserve * p.tokenReserve;
            uint256 oldU = p.usdcReserve;
            p.tokenReserve += q;
            p.usdcReserve = k / p.tokenReserve;
            uint256 harvested = oldU - p.usdcReserve;
            if (harvested > 0) require(USDC.transfer(reserveVaultAddress, harvested), "POLICY_USDC_SWEEP");
            supplyDelta = int256(q);
        } else {
            uint256 fall = referencePrice - price;
            uint256 q = activeBand * fall / referencePrice;
            q = q * burnBpsPerDownPct / 100; // 200 => 2x fall fraction
            if (q == 0) return 0;
            require(q < p.tokenReserve, "BURN_TOO_LARGE");

            uint256 denom = p.tokenReserve - q;
            uint256 spend = (p.usdcReserve * q + denom - 1) / denom;
            reserveVault.pull(address(USDC), address(this), spend);
            p.usdcReserve += spend;
            p.tokenReserve -= q;
            token.cbBurn(q);
            supplyDelta = -int256(q);
        }
    }

    function _resetOneDepth(USDPool storage p, IRUBControllerV24 token, uint256 targetU)
        internal returns (uint256 sweptU, uint256 sweptToken)
    {
        if (p.usdcReserve > targetU) {
            uint256 oldU = p.usdcReserve;
            uint256 newToken = p.tokenReserve * targetU / oldU;
            sweptU = oldU - targetU;
            sweptToken = p.tokenReserve - newToken;
            p.usdcReserve = targetU;
            p.tokenReserve = newToken;
            if (sweptU > 0) require(USDC.transfer(reserveVaultAddress, sweptU), "RESET_USDC_SWEEP");
            if (sweptToken > 0) require(token.transfer(reserveVaultAddress, sweptToken), "RESET_TOKEN_SWEEP");
        } else if (p.usdcReserve < targetU) {
            uint256 addU = targetU - p.usdcReserve;
            uint256 addToken = addU * p.tokenReserve / p.usdcReserve;
            reserveVault.pull(address(USDC), address(this), addU);
            reserveVault.pull(address(token), address(this), addToken);
            p.usdcReserve += addU;
            p.tokenReserve += addToken;
        }
    }

    function _recenterCrossPool() internal {
        uint256 pc = priceRUBCX18();
        uint256 px = priceRUBXX18();
        uint256 targetRatio = pc * PRICE_SCALE / px; // RUBX per RUBC
        uint256 k = rubcRubx.rubcReserve * rubcRubx.rubxReserve;
        uint256 targetX = _sqrt(k * targetRatio / PRICE_SCALE);
        if (targetX == 0) return;
        uint256 targetC = k / targetX;

        if (targetC > rubcRubx.rubcReserve) {
            reserveVault.pull(address(RUBC), address(this), targetC - rubcRubx.rubcReserve);
        } else if (targetC < rubcRubx.rubcReserve) {
            require(RUBC.transfer(reserveVaultAddress, rubcRubx.rubcReserve - targetC), "CROSS_C_SWEEP");
        }
        if (targetX > rubcRubx.rubxReserve) {
            reserveVault.pull(address(RUBX), address(this), targetX - rubcRubx.rubxReserve);
        } else if (targetX < rubcRubx.rubxReserve) {
            require(RUBX.transfer(reserveVaultAddress, rubcRubx.rubxReserve - targetX), "CROSS_X_SWEEP");
        }
        rubcRubx.rubcReserve = targetC;
        rubcRubx.rubxReserve = targetX;
    }

    function _mark(uint256 tokenAmount, uint256 priceX18) internal pure returns (uint256 usdc6) {
        // tokenAmount(1e18) * price(1e18) / 1e30 => USDC(1e6)
        return tokenAmount * priceX18 / 1e30;
    }

    function _sqrt(uint256 x) internal pure returns (uint256 z) {
        if (x == 0) return 0;
        z = x;
        uint256 y = (x + 1) / 2;
        while (y < z) {
            z = y;
            y = (x / y + y) / 2;
        }
    }
}
