// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../src/BaseV3Adapter.sol";

interface Vm {
    function envString(string calldata) external returns(string memory);
    function createSelectFork(string calldata) external returns(uint256);
}

contract BaseForkQuoteTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;
    address constant WETH = 0x4200000000000000000000000000000000000006;
    address constant QUOTER = 0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a;
    address constant ROUTER = 0x2626664c2603336E57B271c5C0b26F421741e481;
    address constant POOL = 0xd0b53D9277642d899DF5C87A3966A349A798F224;

    function testBaseExactV3RoundTripQuotes() public {
        string memory rpc = vm.envString("BASE_RPC_URL");
        vm.createSelectFork(rpc);
        require(QUOTER.code.length > 0, "NO_QUOTER");
        require(ROUTER.code.length > 0, "NO_ROUTER");
        require(POOL.code.length > 0, "NO_POOL");

        IQuoterV2 q = IQuoterV2(QUOTER);
        (uint256 wethOut,,,) = q.quoteExactInputSingle(IQuoterV2.QuoteExactInputSingleParams({
            tokenIn: USDC,
            tokenOut: WETH,
            amountIn: 100e6,
            fee: 500,
            sqrtPriceLimitX96: 0
        }));
        require(wethOut > 0, "ZERO_WETH_QUOTE");

        (uint256 usdcBack,,,) = q.quoteExactInputSingle(IQuoterV2.QuoteExactInputSingleParams({
            tokenIn: WETH,
            tokenOut: USDC,
            amountIn: wethOut,
            fee: 500,
            sqrtPriceLimitX96: 0
        }));
        require(usdcBack > 0, "ZERO_USDC_QUOTE");
        require(usdcBack < 100e6, "ROUNDTRIP_SHOULD_PAY_FEE");
    }
}
