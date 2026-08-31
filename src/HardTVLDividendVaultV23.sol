// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20DividendV23 {
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @notice Canonical-USDC-only HardTVL sink for realized AI-CB dividends.
/// @dev RUBC/RUBX marks are deliberately excluded. A direct USDC donation also raises
///      hardTVLUSDC(), while cumulativeDividends counts only engine-settled profits.
contract HardTVLDividendVaultV23 {
    address public immutable owner;
    IERC20DividendV23 public immutable USDC;

    address public engine;
    bool public engineBound;
    uint256 public cumulativeDividends;
    uint256 public dividendCycles;

    event EngineBound(address indexed engine);
    event DividendDeposited(uint256 indexed cycle, uint256 amount, uint256 hardTVLAfter);

    modifier onlyOwner() {
        require(msg.sender == owner, "OWNER");
        _;
    }

    modifier onlyEngine() {
        require(msg.sender == engine && engineBound, "ENGINE");
        _;
    }

    constructor(address owner_, IERC20DividendV23 usdc_) {
        require(owner_ != address(0) && address(usdc_) != address(0), "ZERO");
        owner = owner_;
        USDC = usdc_;
    }

    function bindEngine(address engine_) external onlyOwner {
        require(!engineBound, "BOUND");
        require(engine_ != address(0), "ZERO_ENGINE");
        engine = engine_;
        engineBound = true;
        emit EngineBound(engine_);
    }

    function depositDividend(uint256 amount) external onlyEngine returns (uint256 hardAfter) {
        require(amount > 0, "ZERO_DIVIDEND");
        uint256 beforeBal = USDC.balanceOf(address(this));
        require(USDC.transferFrom(engine, address(this), amount), "TRANSFER");
        hardAfter = USDC.balanceOf(address(this));
        require(hardAfter == beforeBal + amount, "NON_EXACT_USDC");

        cumulativeDividends += amount;
        dividendCycles += 1;
        emit DividendDeposited(dividendCycles, amount, hardAfter);
    }

    function hardTVLUSDC() external view returns (uint256) {
        return USDC.balanceOf(address(this));
    }

    function solvencyNAVUSDC() external view returns (int256) {
        uint256 bal = USDC.balanceOf(address(this));
        require(bal <= uint256(type(int256).max), "INT_OVERFLOW");
        return int256(bal);
    }
}
