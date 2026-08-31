// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20ReserveV24 {
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @notice Off-kernel reserve. Real external USDC is swept here instead of
/// permanently deepening the price-setting pools. Only the V2.4 kernel may
/// pull reserves back for synchronization, buy/burn, or depth restoration.
contract ProtocolReserveVaultV24 {
    address public owner;
    address public kernel;

    event KernelSet(address indexed kernel);
    event Pulled(address indexed token, address indexed to, uint256 amount);

    modifier onlyOwner() { require(msg.sender == owner, "OWNER"); _; }
    modifier onlyKernel() { require(msg.sender == kernel, "KERNEL"); _; }

    constructor(address owner_) {
        require(owner_ != address(0), "ZERO_OWNER");
        owner = owner_;
    }

    function setKernel(address kernel_) external onlyOwner {
        require(kernel_ != address(0), "ZERO_KERNEL");
        kernel = kernel_;
        emit KernelSet(kernel_);
    }

    function pull(address token, address to, uint256 amount) external onlyKernel {
        require(to != address(0), "ZERO_TO");
        require(IERC20ReserveV24(token).transfer(to, amount), "TRANSFER");
        emit Pulled(token, to, amount);
    }
}
