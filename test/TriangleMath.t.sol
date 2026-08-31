// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "../src/TriangleMath.sol";

contract TriangleMathTest {
    function testNoEdgeIsLossAfterFees() public pure {
        uint256 one=1_000_000e18;
        uint256 out=TriangleMath.triangleA(1000e18, one,one, one,one, one,one, 30,5);
        require(out < 1000e18, "NO_EDGE_SHOULD_NOT_PROFIT");
    }

    function testDirectionAProfitsWithExternalSpread() public pure {
        uint256 R=1_000_000e18;
        uint256 out=TriangleMath.triangleA(1000e18, R,980_000e18, 500_000e18,500_000e18, R,1_020_000e18, 30,5);
        require(out > 1000e18, "EXPECTED_EDGE");
    }
}
