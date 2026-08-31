// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20AccountingV24 {
    function balanceOf(address who) external view returns (uint256);
    function totalSupply() external view returns (uint256);
}

interface IProtocolPoolAccountingV24 {
    /// @dev Canonical USDC reserve owned by protocol in this pool, 6 decimals.
    function protocolUSDCReserve() external view returns (uint256);

    /// @dev Internal marginal price, USDC per token in 1e18 fixed point.
    function spotPriceUSDCX18() external view returns (uint256);

    /// @dev Conservative liquidation quote for tokenAmount into canonical USDC.
    function quoteTokenToUSDC(uint256 tokenAmount) external view returns (uint256);
}

/// @notice Transparent dual accounting for V2.4.
///
/// HARD CASH is canonical USDC actually owned by the protocol after flash debt.
/// SYSTEMIC MARKED NAV additionally marks circulating RUBC/RUBX at the current
/// protocol-pool marginal prices. Internal swaps can change this second metric
/// without creating canonical USDC, so the two numbers must never be conflated.
contract SystemicNAVAccountingV24 {
    IERC20AccountingV24 public immutable USDC;
    IERC20AccountingV24 public immutable RUBC;
    IERC20AccountingV24 public immutable RUBX;

    address public immutable reserveVault;
    IProtocolPoolAccountingV24 public immutable rubcUSDC;
    IProtocolPoolAccountingV24 public immutable rubxUSDC;

    uint256 public immutable rubcUnit; // e.g. 1e18
    uint256 public immutable rubxUnit; // e.g. 1e18

    constructor(
        IERC20AccountingV24 usdc,
        IERC20AccountingV24 rubc,
        IERC20AccountingV24 rubx,
        address reserveVault_,
        IProtocolPoolAccountingV24 rubcUSDC_,
        IProtocolPoolAccountingV24 rubxUSDC_,
        uint256 rubcUnit_,
        uint256 rubxUnit_
    ) {
        USDC = usdc;
        RUBC = rubc;
        RUBX = rubx;
        reserveVault = reserveVault_;
        rubcUSDC = rubcUSDC_;
        rubxUSDC = rubxUSDC_;
        rubcUnit = rubcUnit_;
        rubxUnit = rubxUnit_;
    }

    function hardCashUSDC() public view returns (uint256) {
        return USDC.balanceOf(reserveVault)
            + rubcUSDC.protocolUSDCReserve()
            + rubxUSDC.protocolUSDCReserve();
    }

    /// @notice Reflexive valuation surface. Useful for monetary-policy state,
    /// NOT proof that the entire marked supply can be redeemed at marginal spot.
    function spotMarkedNAVUSDC() public view returns (uint256) {
        uint256 cValue = mulPrice(RUBC.totalSupply(), rubcUSDC.spotPriceUSDCX18(), rubcUnit);
        uint256 xValue = mulPrice(RUBX.totalSupply(), rubxUSDC.spotPriceUSDCX18(), rubxUnit);
        return hardCashUSDC() + cValue + xValue;
    }

    /// @notice Exit-aware sanity metric. It asks the actual pool math how much
    /// USDC can be obtained by liquidating `fractionBps` of both supplies.
    function liquidationNAVUSDC(uint16 fractionBps) external view returns (uint256) {
        require(fractionBps <= 10_000, "BPS");
        uint256 c = RUBC.totalSupply() * fractionBps / 10_000;
        uint256 x = RUBX.totalSupply() * fractionBps / 10_000;
        return hardCashUSDC()
            + rubcUSDC.quoteTokenToUSDC(c)
            + rubxUSDC.quoteTokenToUSDC(x);
    }

    function mulPrice(uint256 amount, uint256 priceX18, uint256 tokenUnit)
        internal pure returns (uint256 usdc6)
    {
        // priceX18 is USDC/token scaled 1e18; result converted to 6-decimal USDC.
        uint256 valueX18 = amount * priceX18 / tokenUnit;
        usdc6 = valueX18 / 1e12;
    }
}
