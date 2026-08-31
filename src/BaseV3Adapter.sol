// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Lite {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address owner) external view returns (uint256);
}

interface IQuoterV2 {
    struct QuoteExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint24 fee;
        uint160 sqrtPriceLimitX96;
    }
    function quoteExactInputSingle(QuoteExactInputSingleParams memory params)
        external returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate);
}

interface ISwapRouter02 {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

contract BaseV3Adapter {
    address public constant BASE_USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;
    address public constant BASE_WETH = 0x4200000000000000000000000000000000000006;
    address public constant BASE_QUOTER_V2 = 0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a;
    address public constant BASE_SWAP_ROUTER_02 = 0x2626664c2603336E57B271c5C0b26F421741e481;
    address public constant BASE_WETH_USDC_005_POOL = 0xd0b53D9277642d899DF5C87A3966A349A798F224;

    IQuoterV2 public immutable quoter;
    ISwapRouter02 public immutable router;

    constructor(address quoter_, address router_) {
        quoter = IQuoterV2(quoter_);
        router = ISwapRouter02(router_);
    }

    function quoteExactInputSingle(address tokenIn, address tokenOut, uint24 fee, uint256 amountIn)
        external returns (uint256 amountOut, uint256 gasEstimate)
    {
        (amountOut,,,gasEstimate) = quoter.quoteExactInputSingle(IQuoterV2.QuoteExactInputSingleParams({
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            amountIn: amountIn,
            fee: fee,
            sqrtPriceLimitX96: 0
        }));
    }

    function swapExactInputSingle(
        address tokenIn, address tokenOut, uint24 fee, uint256 amountIn, uint256 minOut, address recipient
    ) external returns (uint256 amountOut) {
        require(IERC20Lite(tokenIn).approve(address(router), 0), "APPROVE0");
        require(IERC20Lite(tokenIn).approve(address(router), amountIn), "APPROVE");
        amountOut = router.exactInputSingle(ISwapRouter02.ExactInputSingleParams({
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            fee: fee,
            recipient: recipient,
            amountIn: amountIn,
            amountOutMinimum: minOut,
            sqrtPriceLimitX96: 0
        }));
        require(IERC20Lite(tokenIn).approve(address(router), 0), "RESET");
    }
}
