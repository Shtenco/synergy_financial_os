// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20AccountingV24 {
    function balanceOf(address who) external view returns (uint256);
    function totalSupply() external view returns (uint256);
}

interface IProtocolPoolAccountingV24 {
    function protocolUSDCReserve() external view returns (uint256);
    function protocolTokenReserve() external view returns (uint256);
    function spotPriceUSDCX18() external view returns (uint256);
    function quoteTokenToUSDC(uint256 tokenAmount) external view returns (uint256);
}

interface IProtocolCrossPoolAccountingV24 {
    function protocolRUBCReserve() external view returns (uint256);
    function protocolRUBXReserve() external view returns (uint256);
}

/// @notice V2.4 exposes three deliberately different value surfaces:
/// 1) HardCashUSDC: actual canonical USDC owned after debt;
/// 2) ProtocolMarkedTVL: only protocol-owned RUBC/RUBX inventory marked at
///    current internal marginal prices;
/// 3) SystemicMarketValue: total token supply marked at marginal prices.
///
/// This prevents the reflexive multiplier from depending on other users'
/// balances while still making the internal revaluation effect measurable.
contract SystemicNAVAccountingV24 {
    IERC20AccountingV24 public immutable USDC;
    IERC20AccountingV24 public immutable RUBC;
    IERC20AccountingV24 public immutable RUBX;

    address public immutable reserveVault;
    IProtocolPoolAccountingV24 public immutable rubcUSDC;
    IProtocolPoolAccountingV24 public immutable rubxUSDC;
    IProtocolCrossPoolAccountingV24 public immutable rubcRubx;

    uint256 public immutable rubcUnit;
    uint256 public immutable rubxUnit;

    constructor(
        IERC20AccountingV24 usdc,
        IERC20AccountingV24 rubc,
        IERC20AccountingV24 rubx,
        address reserveVault_,
        IProtocolPoolAccountingV24 rubcUSDC_,
        IProtocolPoolAccountingV24 rubxUSDC_,
        IProtocolCrossPoolAccountingV24 rubcRubx_,
        uint256 rubcUnit_,
        uint256 rubxUnit_
    ) {
        USDC = usdc;
        RUBC = rubc;
        RUBX = rubx;
        reserveVault = reserveVault_;
        rubcUSDC = rubcUSDC_;
        rubxUSDC = rubxUSDC_;
        rubcRubx = rubcRubx_;
        rubcUnit = rubcUnit_;
        rubxUnit = rubxUnit_;
    }

    function hardCashUSDC() public view returns (uint256) {
        return USDC.balanceOf(reserveVault)
            + rubcUSDC.protocolUSDCReserve()
            + rubxUSDC.protocolUSDCReserve();
    }

    function protocolRUBC() public view returns (uint256) {
        return RUBC.balanceOf(reserveVault)
            + rubcUSDC.protocolTokenReserve()
            + rubcRubx.protocolRUBCReserve();
    }

    function protocolRUBX() public view returns (uint256) {
        return RUBX.balanceOf(reserveVault)
            + rubxUSDC.protocolTokenReserve()
            + rubcRubx.protocolRUBXReserve();
    }

    /// @notice Mark only protocol-owned token assets. This is the closest
    /// V2.4 analogue of a reflexive protocol TVL surface.
    function protocolMarkedTVLUSDC() public view returns (uint256) {
        uint256 cValue = mulPrice(protocolRUBC(), rubcUSDC.spotPriceUSDCX18(), rubcUnit);
        uint256 xValue = mulPrice(protocolRUBX(), rubxUSDC.spotPriceUSDCX18(), rubxUnit);
        return hardCashUSDC() + cValue + xValue;
    }

    /// @notice Whole-system marginal market-value surface. This includes
    /// externally held RUBC/RUBX and is therefore not protocol NAV.
    function systemicMarketValueUSDC() public view returns (uint256) {
        uint256 cValue = mulPrice(RUBC.totalSupply(), rubcUSDC.spotPriceUSDCX18(), rubcUnit);
        uint256 xValue = mulPrice(RUBX.totalSupply(), rubxUSDC.spotPriceUSDCX18(), rubxUnit);
        return hardCashUSDC() + cValue + xValue;
    }

    /// @notice Exit-aware sanity surface. This asks the pool curves what a
    /// selected fraction of protocol-owned inventory can actually realize.
    function protocolLiquidationNAVUSDC(uint16 fractionBps) external view returns (uint256) {
        require(fractionBps <= 10_000, "BPS");
        uint256 c = protocolRUBC() * fractionBps / 10_000;
        uint256 x = protocolRUBX() * fractionBps / 10_000;
        return hardCashUSDC()
            + rubcUSDC.quoteTokenToUSDC(c)
            + rubxUSDC.quoteTokenToUSDC(x);
    }

    function mulPrice(uint256 amount, uint256 priceX18, uint256 tokenUnit)
        internal pure returns (uint256 usdc6)
    {
        uint256 valueX18 = amount * priceX18 / tokenUnit;
        usdc6 = valueX18 / 1e12;
    }
}
