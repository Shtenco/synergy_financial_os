// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V24 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address who) external view returns (uint256);
}

interface IFlash200V24 {
    function flash(address receiver, uint256 amount, bytes calldata data) external;
}

/// @notice Known three-pool kernel. There is intentionally no route search.
/// The kernel owns the fixed RUBC/USDC + RUBX/USDC + RUBC/RUBX topology.
interface IReflexiveKernelV24 {
    /// Add temporary LP to the active external USD leg using the same 200-USDC
    /// flash principal. Matching protocol-token inventory is temporary.
    function openTemporaryLiquidity(uint8 activeLeg, uint256 usdcPrincipal) external;

    /// Consume one external 1-USDC buyer quantum against the active leg.
    function executeBuyerQuantum(
        uint8 activeLeg,
        uint256 buyerUSDC,
        address tokenRecipient,
        uint256 minTokenOut
    ) external returns (uint256 tokenOut);

    /// REMOVE100 of the temporary position. The 200-USDC principal becomes
    /// available for immediate reuse by the next microcycle.
    function closeTemporaryLiquidity(uint8 activeLeg) external returns (uint256 usdcReturned);

    /// Internal triangle controller. It may move protocol-owned USDC between
    /// treasury/pools without changing consolidated cash, buy/burn the lower
    /// leg, and maintain RUBC/RUBX coherence.
    function synchronizeUpward() external returns (uint256 internalUSDCMoved, uint256 burnedRUBC, uint256 burnedRUBX);

    /// Monetary policy band:
    /// +1% price step => sell 1% of active emission band;
    /// -1% price step => buy/burn 2% of active emission band.
    function applyEmissionPolicy(
        uint16 sellBpsPerUpPct,
        uint16 burnBpsPerDownPct,
        uint16 activeBandBps
    ) external returns (int256 rubcSupplyDelta, int256 rubxSupplyDelta);

    function hardCashUSDC() external view returns (uint256);
    function spotMarkedNAVUSDC() external view returns (uint256);
}

/// @notice One Balancer-V2 flash loan can be recycled through many $1
/// microcycles in a single atomic buyer batch:
///
/// flash 200 -> ADDLP200 -> external $1 -> REMOVE200 -> policy/reinvest
///           -> ADDLP200 -> external $1 -> REMOVE200 -> ... -> repay 200.
///
/// Hard cash and reflexive marked NAV are deliberately reported separately.
contract ReflexiveSingleBatchV24 {
    uint256 public constant FLASH_PRINCIPAL = 200e6;
    uint256 public constant BUYER_QUANTUM = 1e6;

    address public owner;
    address public keeper;
    IERC20V24 public immutable USDC;
    IFlash200V24 public immutable flashAdapter;
    IReflexiveKernelV24 public kernel;

    struct Policy {
        uint16 sellBpsPerUpPct;       // 100 = 1% active band per +1% price
        uint16 burnBpsPerDownPct;     // 200 = 2% active band per -1% price
        uint16 activeBandBps;         // e.g. 1000 = 10% liquidity-active tranche
        uint16 maxQuanta;             // safety bound for one atomic batch
        uint256 minHardCashGainPerQuantum; // normally 1e6 minus explicit costs
    }

    struct Batch {
        uint16 quanta;
        uint8 firstLeg;               // 0=RUBC/USDC, 1=RUBX/USDC; alternate after
        uint256 minTokenOutPerQuantum;
    }

    Policy public policy;
    bool private inFlash;
    uint256 private hardBefore;
    uint256 private markedBefore;
    uint256 private externalUSDCIn;
    address private buyer;

    event BatchSettled(
        uint256 externalUSDCIn,
        uint256 flashPrincipal,
        uint256 hardCashBefore,
        uint256 hardCashAfter,
        uint256 markedNAVBefore,
        uint256 markedNAVAfter,
        uint256 microcycles
    );

    modifier onlyOwner() { require(msg.sender == owner, "OWNER"); _; }
    modifier onlyKeeperOrUser() { require(msg.sender == keeper || msg.sender == tx.origin, "CALLER"); _; }

    constructor(
        address owner_,
        address keeper_,
        IERC20V24 usdc_,
        IFlash200V24 flashAdapter_,
        IReflexiveKernelV24 kernel_,
        Policy memory p
    ) {
        require(owner_ != address(0) && keeper_ != address(0), "ROLE");
        require(p.sellBpsPerUpPct == 100, "SELL_RULE");
        require(p.burnBpsPerDownPct == 200, "BURN_RULE");
        require(p.maxQuanta > 0, "QUANTA");
        owner = owner_;
        keeper = keeper_;
        USDC = usdc_;
        flashAdapter = flashAdapter_;
        kernel = kernel_;
        policy = p;
    }

    function setPolicy(Policy calldata p) external onlyOwner {
        require(p.sellBpsPerUpPct == 100, "SELL_RULE");
        require(p.burnBpsPerDownPct == 200, "BURN_RULE");
        require(p.maxQuanta > 0, "QUANTA");
        policy = p;
    }

    function setKernel(IReflexiveKernelV24 k) external onlyOwner {
        require(address(k) != address(0), "KERNEL");
        kernel = k;
    }

    /// @notice Buyer funds are part of the same atomic batch. No asynchronous
    /// external order is assumed and no route search exists.
    function executeBatch(Batch calldata b) external onlyKeeperOrUser {
        require(!inFlash, "ACTIVE");
        require(b.quanta > 0 && b.quanta <= policy.maxQuanta, "QUANTA");
        require(b.firstLeg < 2, "LEG");

        buyer = msg.sender;
        externalUSDCIn = uint256(b.quanta) * BUYER_QUANTUM;
        hardBefore = kernel.hardCashUSDC();
        markedBefore = kernel.spotMarkedNAVUSDC();

        require(USDC.transferFrom(msg.sender, address(this), externalUSDCIn), "BUYER_USDC");
        inFlash = true;
        flashAdapter.flash(address(this), FLASH_PRINCIPAL, abi.encode(b));
        require(!inFlash, "FLASH_CALLBACK");

        uint256 hardAfter = kernel.hardCashUSDC();
        uint256 markedAfter = kernel.spotMarkedNAVUSDC();
        require(
            hardAfter >= hardBefore + uint256(b.quanta) * policy.minHardCashGainPerQuantum,
            "HARD_CASH_GATE"
        );
        require(markedAfter >= markedBefore, "MARKED_NAV_DOWN");

        emit BatchSettled(
            externalUSDCIn,
            FLASH_PRINCIPAL,
            hardBefore,
            hardAfter,
            markedBefore,
            markedAfter,
            b.quanta
        );

        buyer = address(0);
        externalUSDCIn = 0;
    }

    /// @notice Called by the fixed-200 Balancer adapter.
    function onFlash(uint256 amount, uint256 fee, bytes calldata data) external {
        require(msg.sender == address(flashAdapter) && inFlash, "FLASH_CALLER");
        require(amount == FLASH_PRINCIPAL, "NOT_200");
        require(fee == 0, "NONZERO_FEE");
        Batch memory b = abi.decode(data, (Batch));

        require(USDC.approve(address(kernel), 0), "K0");
        require(USDC.approve(address(kernel), type(uint256).max), "K1");

        for (uint256 i = 0; i < b.quanta; ++i) {
            uint8 leg = uint8((uint256(b.firstLeg) + i) & 1);

            // Reuse exactly the same 200-USDC flash principal each microcycle.
            kernel.openTemporaryLiquidity(leg, FLASH_PRINCIPAL);
            kernel.executeBuyerQuantum(leg, BUYER_QUANTUM, buyer, b.minTokenOutPerQuantum);
            uint256 returned = kernel.closeTemporaryLiquidity(leg);
            require(returned >= FLASH_PRINCIPAL, "TEMP_LP_PRINCIPAL");

            // Internal revaluation/reinvestment step. Moving system-owned USDC
            // between treasury and protocol-owned pools does not change hard cash,
            // but it can change the reserve ratios and therefore marked NAV.
            kernel.synchronizeUpward();
            kernel.applyEmissionPolicy(
                policy.sellBpsPerUpPct,
                policy.burnBpsPerDownPct,
                policy.activeBandBps
            );
        }

        require(USDC.approve(address(kernel), 0), "K_RESET");

        // The flash adapter pulls exactly 200 USDC once, after all microcycles.
        require(USDC.approve(address(flashAdapter), 0), "F0");
        require(USDC.approve(address(flashAdapter), FLASH_PRINCIPAL), "F1");
        inFlash = false;
    }
}
