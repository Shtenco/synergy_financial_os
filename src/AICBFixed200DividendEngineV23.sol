// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Fixed200V23 {
    function balanceOf(address account) external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IFlashFixed200V23 {
    function flash(address receiver, uint256 amount, bytes calldata data) external;
}

interface ITriangleRouterFixed200V23 {
    function executeTriangle(
        uint8 direction,
        uint256 usdcIn,
        uint256 minUsdcOut,
        bytes calldata routeData
    ) external returns (uint256 usdcOut);
}

interface IHardTVLDividendVaultV23 {
    function depositDividend(uint256 amount) external returns (uint256 hardAfter);
    function hardTVLUSDC() external view returns (uint256);
    function solvencyNAVUSDC() external view returns (int256);
}

/// @notice V2.3 settlement engine:
///         200 USDC flash -> triangle -> repay 200 -> send 100% realized surplus to HardTVL.
/// @dev No committed cycle can finish with flash debt, flash fee, RUBC/RUBX inflation,
///      or non-positive HardTVL delta. Unprofitable attempts revert atomically.
contract AICBFixed200DividendEngineV23 {
    uint256 public constant FLASH_PRINCIPAL = 200e6;

    address public owner;
    address public keeper;

    IERC20Fixed200V23 public immutable USDC;
    IERC20Fixed200V23 public immutable RUBC;
    IERC20Fixed200V23 public immutable RUBX;
    IFlashFixed200V23 public immutable flashAdapter;
    ITriangleRouterFixed200V23 public router;
    IHardTVLDividendVaultV23 public immutable dividendVault;

    struct Policy {
        uint256 minDividendUSDC;
        uint256 minHardTVLGainUSDC;
        bool requireExactSupplyRestoration;
    }

    struct Plan {
        uint8 direction;
        uint256 minUsdcOut;
        bytes routeData;
    }

    struct Snapshot {
        uint256 engineUSDC;
        uint256 rubcSupply;
        uint256 rubxSupply;
        uint256 hardTVL;
        int256 solvencyNAV;
    }

    Policy public policy;
    Snapshot private snap;
    bool private inCycle;
    uint256 public settledCycles;
    uint256 public cumulativeDividends;

    event PolicyUpdated(uint256 minDividendUSDC, uint256 minHardTVLGainUSDC, bool exactSupply);
    event RouterUpdated(address indexed router);
    event CycleSettled(
        uint256 indexed cycle,
        uint8 indexed direction,
        uint256 flashPrincipal,
        uint256 flashFee,
        uint256 dividendUSDC,
        uint256 hardTVLBefore,
        uint256 hardTVLAfter
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "OWNER");
        _;
    }

    modifier onlyKeeper() {
        require(msg.sender == keeper, "KEEPER");
        _;
    }

    constructor(
        address owner_,
        address keeper_,
        IERC20Fixed200V23 usdc_,
        IERC20Fixed200V23 rubc_,
        IERC20Fixed200V23 rubx_,
        IFlashFixed200V23 flashAdapter_,
        ITriangleRouterFixed200V23 router_,
        IHardTVLDividendVaultV23 dividendVault_,
        Policy memory policy_
    ) {
        require(owner_ != address(0) && keeper_ != address(0), "ZERO_ROLE");
        require(address(usdc_) != address(0) && address(rubc_) != address(0) && address(rubx_) != address(0), "ZERO_TOKEN");
        require(address(flashAdapter_) != address(0) && address(router_) != address(0) && address(dividendVault_) != address(0), "ZERO_ADAPTER");
        owner = owner_;
        keeper = keeper_;
        USDC = usdc_;
        RUBC = rubc_;
        RUBX = rubx_;
        flashAdapter = flashAdapter_;
        router = router_;
        dividendVault = dividendVault_;
        policy = policy_;
    }

    function setKeeper(address keeper_) external onlyOwner {
        require(keeper_ != address(0), "ZERO_KEEPER");
        keeper = keeper_;
    }

    function setRouter(ITriangleRouterFixed200V23 router_) external onlyOwner {
        require(address(router_) != address(0), "ZERO_ROUTER");
        router = router_;
        emit RouterUpdated(address(router_));
    }

    function setPolicy(Policy calldata p) external onlyOwner {
        policy = p;
        emit PolicyUpdated(p.minDividendUSDC, p.minHardTVLGainUSDC, p.requireExactSupplyRestoration);
    }

    /// @notice Every successful call settles exactly one 200-USDC zero-fee flash cycle.
    /// @dev If the external route cannot cover 200 USDC + minDividend, transaction reverts.
    function execute200(Plan calldata p) external onlyKeeper returns (uint256 dividendUSDC) {
        require(!inCycle, "ACTIVE");
        require(p.direction < 2, "DIRECTION");

        snap = Snapshot({
            engineUSDC: USDC.balanceOf(address(this)),
            rubcSupply: RUBC.totalSupply(),
            rubxSupply: RUBX.totalSupply(),
            hardTVL: dividendVault.hardTVLUSDC(),
            solvencyNAV: dividendVault.solvencyNAVUSDC()
        });

        inCycle = true;
        flashAdapter.flash(address(this), FLASH_PRINCIPAL, abi.encode(p));
        require(!inCycle, "FLASH_CALLBACK_INCOMPLETE");

        uint256 engineAfterRepay = USDC.balanceOf(address(this));
        require(engineAfterRepay >= snap.engineUSDC, "POST_REPAY_LOSS");
        dividendUSDC = engineAfterRepay - snap.engineUSDC;
        require(dividendUSDC >= policy.minDividendUSDC, "DIVIDEND_TOO_SMALL");

        if (policy.requireExactSupplyRestoration) {
            require(RUBC.totalSupply() == snap.rubcSupply, "RUBC_SUPPLY_CHANGED");
            require(RUBX.totalSupply() == snap.rubxSupply, "RUBX_SUPPLY_CHANGED");
        } else {
            require(RUBC.totalSupply() <= snap.rubcSupply, "RUBC_INFLATION");
            require(RUBX.totalSupply() <= snap.rubxSupply, "RUBX_INFLATION");
        }

        require(USDC.approve(address(dividendVault), 0), "DIV_APPROVE0");
        require(USDC.approve(address(dividendVault), dividendUSDC), "DIV_APPROVE");
        uint256 hardAfter = dividendVault.depositDividend(dividendUSDC);
        require(USDC.approve(address(dividendVault), 0), "DIV_APPROVE_RESET");

        require(hardAfter >= snap.hardTVL + dividendUSDC, "DIVIDEND_NOT_HARD_TVL");
        require(hardAfter >= snap.hardTVL + policy.minHardTVLGainUSDC, "HARD_TVL_GAIN");
        require(dividendVault.solvencyNAVUSDC() >= snap.solvencyNAV + int256(dividendUSDC), "NAV_GAIN");
        require(USDC.balanceOf(address(this)) == snap.engineUSDC, "ENGINE_PROFIT_NOT_SWEPT");

        settledCycles += 1;
        cumulativeDividends += dividendUSDC;
        emit CycleSettled(settledCycles, p.direction, FLASH_PRINCIPAL, 0, dividendUSDC, snap.hardTVL, hardAfter);
    }

    /// @notice Called by BalancerV2ZeroFee200USDCAdapter while Balancer V2 loan is live.
    function onFlash(uint256 amount, uint256 fee, bytes calldata data) external {
        require(msg.sender == address(flashAdapter), "FLASH_ADAPTER");
        require(inCycle, "NO_ACTIVE_CYCLE");
        require(amount == FLASH_PRINCIPAL, "NOT_200_USDC");
        require(fee == 0, "FLASH_FEE_NOT_ZERO");

        Plan memory p = abi.decode(data, (Plan));
        require(p.direction < 2, "DIRECTION");

        require(USDC.approve(address(router), 0), "ROUTER_APPROVE0");
        require(USDC.approve(address(router), FLASH_PRINCIPAL), "ROUTER_APPROVE");
        uint256 out = router.executeTriangle(p.direction, FLASH_PRINCIPAL, p.minUsdcOut, p.routeData);
        require(out >= p.minUsdcOut, "SLIPPAGE");
        require(USDC.approve(address(router), 0), "ROUTER_APPROVE_RESET");

        // Before the adapter pulls the 200-USDC repayment, the engine must already
        // hold its pre-cycle balance + principal + a real dividend.
        require(
            USDC.balanceOf(address(this)) >= snap.engineUSDC + FLASH_PRINCIPAL + policy.minDividendUSDC,
            "NO_REAL_SURPLUS"
        );

        // Balancer adapter pulls exactly 200 USDC and transfers it back to the Vault.
        require(USDC.approve(address(flashAdapter), 0), "FLASH_APPROVE0");
        require(USDC.approve(address(flashAdapter), FLASH_PRINCIPAL), "FLASH_APPROVE");
        inCycle = false;
    }
}
