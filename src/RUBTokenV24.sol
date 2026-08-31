// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal ERC20 used by the V2.4 research kernel. Permanent initial
/// supply is created once; only the AI-CB kernel may subsequently mint/burn.
contract RUBTokenV24 {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    address public admin;
    address public controller;

    event Transfer(address indexed from, address indexed to, uint256 amount);
    event Approval(address indexed owner, address indexed spender, uint256 amount);
    event ControllerSet(address indexed controller);

    modifier onlyAdmin() { require(msg.sender == admin, "ADMIN"); _; }
    modifier onlyController() { require(msg.sender == controller, "CONTROLLER"); _; }

    constructor(
        string memory name_,
        string memory symbol_,
        address admin_,
        address initialHolder,
        uint256 initialSupply
    ) {
        require(admin_ != address(0) && initialHolder != address(0), "ZERO");
        name = name_;
        symbol = symbol_;
        admin = admin_;
        _mint(initialHolder, initialSupply);
    }

    function setController(address controller_) external onlyAdmin {
        require(controller_ != address(0), "ZERO_CONTROLLER");
        controller = controller_;
        emit ControllerSet(controller_);
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            require(allowed >= amount, "ALLOWANCE");
            allowance[from][msg.sender] = allowed - amount;
            emit Approval(from, msg.sender, allowance[from][msg.sender]);
        }
        _transfer(from, to, amount);
        return true;
    }

    function cbMint(address to, uint256 amount) external onlyController {
        _mint(to, amount);
    }

    /// @notice Controller burns its own inventory. For temporary LP debt the
    /// kernel first restores any token shortfall from ReserveVault, then burns
    /// exactly the amount it temporarily minted.
    function cbBurn(uint256 amount) external onlyController {
        uint256 bal = balanceOf[msg.sender];
        require(bal >= amount, "BURN_BALANCE");
        balanceOf[msg.sender] = bal - amount;
        totalSupply -= amount;
        emit Transfer(msg.sender, address(0), amount);
    }

    function _mint(address to, uint256 amount) internal {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(to != address(0), "ZERO_TO");
        uint256 bal = balanceOf[from];
        require(bal >= amount, "BALANCE");
        balanceOf[from] = bal - amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}
