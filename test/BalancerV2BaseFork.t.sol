// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../src/BalancerV2ZeroFee200USDCAdapter.sol";

interface VmBalancerBaseV23 {
    function envString(string calldata) external returns (string memory);
    function createSelectFork(string calldata) external returns (uint256);
}

interface IBalancerV2VaultIntrospectionV23 {
    function getProtocolFeesCollector() external view returns (address);
}

interface IProtocolFeesCollectorV23 {
    function getFlashLoanFeePercentage() external view returns (uint256);
}

contract BalancerV2BaseFlashProbeV23 is IBalancerV2FlashLoanRecipient {
    address public immutable vault;
    IERC20BalancerV2 public immutable token;
    uint256 public callbacks;
    uint256 public lastFee;

    constructor(address vault_, IERC20BalancerV2 token_) {
        vault = vault_;
        token = token_;
    }

    function receiveFlashLoan(
        IERC20BalancerV2[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory
    ) external override {
        require(msg.sender == vault, "VAULT");
        require(tokens.length == 1 && address(tokens[0]) == address(token), "TOKEN");
        require(amounts[0] == 200e6, "NOT_200");
        require(feeAmounts[0] == 0, "LIVE_FEE_NOT_ZERO");
        callbacks += 1;
        lastFee = feeAmounts[0];
        require(token.transfer(vault, amounts[0]), "REPAY");
    }
}

contract BalancerV2BaseForkV23Test {
    VmBalancerBaseV23 constant vm = VmBalancerBaseV23(address(uint160(uint256(keccak256("hevm cheat code")))));

    address constant BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant BASE_USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;

    function testBaseLiveBalancerV2ZeroFee200USDCFlash() public {
        string memory rpc = vm.envString("BASE_RPC_URL");
        vm.createSelectFork(rpc);

        require(BALANCER_V2_VAULT.code.length > 0, "NO_V2_VAULT");
        require(BASE_USDC.code.length > 0, "NO_USDC");

        address collector = IBalancerV2VaultIntrospectionV23(BALANCER_V2_VAULT).getProtocolFeesCollector();
        require(collector.code.length > 0, "NO_FEE_COLLECTOR");
        require(IProtocolFeesCollectorV23(collector).getFlashLoanFeePercentage() == 0, "LIVE_FLASH_FEE_NOT_ZERO");

        IERC20BalancerV2 usdc = IERC20BalancerV2(BASE_USDC);
        uint256 vaultBefore = usdc.balanceOf(BALANCER_V2_VAULT);
        require(vaultBefore >= 200e6, "INSUFFICIENT_V2_USDC_LIQUIDITY");

        BalancerV2BaseFlashProbeV23 probe = new BalancerV2BaseFlashProbeV23(BALANCER_V2_VAULT, usdc);
        IERC20BalancerV2[] memory tokens = new IERC20BalancerV2[](1);
        uint256[] memory amounts = new uint256[](1);
        tokens[0] = usdc;
        amounts[0] = 200e6;

        IBalancerV2VaultFlash(BALANCER_V2_VAULT).flashLoan(probe, tokens, amounts, bytes("V23_FIXED200_PROBE"));

        require(probe.callbacks() == 1, "NO_CALLBACK");
        require(probe.lastFee() == 0, "NONZERO_FEE");
        require(usdc.balanceOf(BALANCER_V2_VAULT) == vaultBefore, "PRINCIPAL_NOT_RESTORED");
        require(usdc.balanceOf(address(probe)) == 0, "PROBE_RESIDUAL");
    }
}
