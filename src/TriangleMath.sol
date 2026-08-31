// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

library TriangleMath {
    uint256 internal constant BPS = 10_000;

    function quoteCPMM(uint256 reserveIn, uint256 reserveOut, uint256 amountIn, uint256 feeBps)
        internal pure returns (uint256 amountOut)
    {
        require(reserveIn > 0 && reserveOut > 0, "EMPTY_POOL");
        require(feeBps < BPS, "BAD_FEE");
        uint256 amountInWithFee = amountIn * (BPS - feeBps);
        amountOut = (reserveOut * amountInWithFee) / (reserveIn * BPS + amountInWithFee);
    }

    function triangleA(
        uint256 usdcIn,
        uint256 xuX, uint256 xuU,
        uint256 cxC, uint256 cxX,
        uint256 cuC, uint256 cuU,
        uint256 extFeeBps, uint256 crossFeeBps
    ) internal pure returns (uint256 usdcOut) {
        uint256 x = quoteCPMM(xuU, xuX, usdcIn, extFeeBps);
        uint256 c = quoteCPMM(cxX, cxC, x, crossFeeBps);
        usdcOut = quoteCPMM(cuC, cuU, c, extFeeBps);
    }

    function triangleB(
        uint256 usdcIn,
        uint256 cuC, uint256 cuU,
        uint256 cxC, uint256 cxX,
        uint256 xuX, uint256 xuU,
        uint256 extFeeBps, uint256 crossFeeBps
    ) internal pure returns (uint256 usdcOut) {
        uint256 c = quoteCPMM(cuU, cuC, usdcIn, extFeeBps);
        uint256 x = quoteCPMM(cxC, cxX, c, crossFeeBps);
        usdcOut = quoteCPMM(xuX, xuU, x, extFeeBps);
    }
}
