// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20BalancerV2 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

interface IERC20MetadataBalancerV2 is IERC20BalancerV2 {
    function decimals() external view returns (uint8);
}

interface IBalancerV2FlashLoanRecipient {
    function receiveFlashLoan(
        IERC20BalancerV2[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external;
}

interface IBalancerV2VaultFlash {
    function flashLoan(
        IBalancerV2FlashLoanRecipient recipient,
        IERC20BalancerV2[] memory tokens,
        uint256[] memory amounts,
        bytes memory userData
    ) external;
}

interface IFixed200FlashEngine {
    function onFlash(uint256 amount, uint256 fee, bytes calldata data) external;
}

/// @notice Balancer V2 flash adapter that commits only zero-fee, exactly-200-USDC cycles.
/// @dev The Balancer V2 Vault requires principal + fee to be transferred back before
///      receiveFlashLoan() returns. This adapter deliberately reverts if feeAmounts[0] != 0.
contract BalancerV2ZeroFee200USDCAdapter is IBalancerV2FlashLoanRecipient {
    uint256 public constant PRINCIPAL = 200e6; // canonical 6-decimal USDC

    address public immutable owner;
    IBalancerV2VaultFlash public immutable vault;
    IERC20MetadataBalancerV2 public immutable USDC;

    address public engine;
    bool public engineBound;
    bool private active;
    uint256 public settledCycles;
    uint256 public cumulativePrincipalRepaid;

    event EngineBound(address indexed engine);
    event ZeroFeeFlashSettled(uint256 indexed cycle, uint256 principal, uint256 fee);

    modifier onlyOwner() {
        require(msg.sender == owner, "OWNER");
        _;
    }

    modifier onlyEngine() {
        require(msg.sender == engine && engineBound, "ENGINE");
        _;
    }

    constructor(address owner_, IBalancerV2VaultFlash vault_, IERC20MetadataBalancerV2 usdc_) {
        require(owner_ != address(0) && address(vault_) != address(0) && address(usdc_) != address(0), "ZERO");
        require(usdc_.decimals() == 6, "USDC_DECIMALS");
        owner = owner_;
        vault = vault_;
        USDC = usdc_;
    }

    function bindEngine(address engine_) external onlyOwner {
        require(!engineBound, "BOUND");
        require(engine_ != address(0), "ZERO_ENGINE");
        engine = engine_;
        engineBound = true;
        emit EngineBound(engine_);
    }

    /// @notice Compatibility surface used by the AI-CB engine.
    function flash(address receiver, uint256 amount, bytes calldata data) external onlyEngine {
        require(!active, "ACTIVE");
        require(receiver == engine, "RECEIVER");
        require(amount == PRINCIPAL, "NOT_200_USDC");

        IERC20BalancerV2[] memory tokens = new IERC20BalancerV2[](1);
        uint256[] memory amounts = new uint256[](1);
        tokens[0] = IERC20BalancerV2(address(USDC));
        amounts[0] = PRINCIPAL;

        active = true;
        vault.flashLoan(this, tokens, amounts, data);
        require(!active, "CALLBACK_INCOMPLETE");
    }

    function receiveFlashLoan(
        IERC20BalancerV2[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == address(vault), "VAULT");
        require(active, "NO_ACTIVE_FLASH");
        require(tokens.length == 1 && amounts.length == 1 && feeAmounts.length == 1, "LENGTH");
        require(address(tokens[0]) == address(USDC), "TOKEN");
        require(amounts[0] == PRINCIPAL, "PRINCIPAL");

        // Strong zero-fee invariant. If governance changes the Balancer V2 fee,
        // the whole transaction reverts instead of silently consuming HardTVL.
        require(feeAmounts[0] == 0, "FLASH_FEE_NOT_ZERO");
        require(USDC.balanceOf(address(this)) >= PRINCIPAL, "LOAN_NOT_RECEIVED");

        require(USDC.transfer(engine, PRINCIPAL), "TO_ENGINE");
        IFixed200FlashEngine(engine).onFlash(PRINCIPAL, 0, userData);

        // Engine approves exactly PRINCIPAL after creating a real external surplus.
        require(USDC.transferFrom(engine, address(this), PRINCIPAL), "PULL_REPAYMENT");
        require(USDC.transfer(address(vault), PRINCIPAL), "REPAY_VAULT");

        active = false;
        settledCycles += 1;
        cumulativePrincipalRepaid += PRINCIPAL;
        emit ZeroFeeFlashSettled(settledCycles, PRINCIPAL, 0);
    }
}
