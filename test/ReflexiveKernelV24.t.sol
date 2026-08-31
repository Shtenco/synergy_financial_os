// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../src/RUBTokenV24.sol";
import "../src/ProtocolReserveVaultV24.sol";
import "../src/ReflexiveCPMMKernelV24.sol";

contract MockUSDCV24 {
    string public constant name = "Mock USDC";
    string public constant symbol = "USDC";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to,uint256 amount) external { totalSupply+=amount; balanceOf[to]+=amount; }
    function transfer(address to,uint256 amount) external returns(bool){
        require(balanceOf[msg.sender]>=amount,"BAL"); balanceOf[msg.sender]-=amount; balanceOf[to]+=amount; return true;
    }
    function approve(address s,uint256 amount) external returns(bool){ allowance[msg.sender][s]=amount; return true; }
    function transferFrom(address from,address to,uint256 amount) external returns(bool){
        uint256 a=allowance[from][msg.sender]; require(a>=amount,"ALLOW");
        if(a!=type(uint256).max) allowance[from][msg.sender]=a-amount;
        require(balanceOf[from]>=amount,"BAL"); balanceOf[from]-=amount; balanceOf[to]+=amount; return true;
    }
}

contract ReflexiveKernelV24Test {
    MockUSDCV24 usdc;
    ProtocolReserveVaultV24 vault;
    RUBTokenV24 rubc;
    RUBTokenV24 rubx;
    ReflexiveCPMMKernelV24 kernel;

    function setUp() public {
        usdc = new MockUSDCV24();
        vault = new ProtocolReserveVaultV24(address(this));
        rubc = new RUBTokenV24("RUBC","RUBC",address(this),address(vault),1_000_000e18);
        rubx = new RUBTokenV24("RUBX","RUBX",address(this),address(vault),1_000_000e18);
        kernel = new ReflexiveCPMMKernelV24(
            address(this),
            IERC20KernelV24(address(usdc)),
            IRUBControllerV24(address(rubc)),
            IRUBControllerV24(address(rubx)),
            IReserveVaultKernelV24(address(vault))
        );

        vault.setKernel(address(kernel));
        rubc.setController(address(kernel));
        rubx.setController(address(kernel));
        kernel.setEngine(address(this));

        usdc.mint(address(this),1_000e6);
        usdc.approve(address(kernel),type(uint256).max);
        kernel.initialize();
    }

    function testOneDollarRecycledFlashMicrocycle() public {
        uint256 cSupply0 = rubc.totalSupply();
        uint256 xSupply0 = rubx.totalSupply();
        uint256 marked0 = kernel.spotMarkedNAVUSDC();
        require(kernel.hardCashUSDC()==1e6,"GENESIS_HARD");
        require(kernel.priceRUBCX18()==1e18 && kernel.priceRUBXX18()==1e18,"GENESIS_PRICE");

        // Simulates the 200-USDC principal already delivered by Balancer to the
        // enclosing engine. Here the test contract acts as that engine.
        kernel.openTemporaryLiquidity(0,200e6);
        uint256 bought = kernel.executeBuyerQuantum(0,1e6,address(0xBEEF),0);
        require(bought>0,"NO_BUY");
        uint256 returned = kernel.closeTemporaryLiquidity(0);
        require(returned==200e6,"FLASH_NOT_REUSABLE");

        // Temporary token-side mint must be completely extinguished before the
        // permanent AI-CB policy runs.
        require(rubc.totalSupply()==cSupply0,"TEMP_C_INFLATION");
        require(rubx.totalSupply()==xSupply0,"TEMP_X_INFLATION");
        require(kernel.priceRUBCX18()>1e18,"NO_PRICE_STEP");

        kernel.synchronizeUpward();
        kernel.applyEmissionPolicy(100,200,1000);
        kernel.synchronizeUpward();
        kernel.resetPriceKernelDepth(5e5);

        (uint256 cToken,uint256 cUSDC)=kernel.rubcUSDC();
        (uint256 xToken,uint256 xUSDC)=kernel.rubxUSDC();
        require(cToken>0 && xToken>0,"EMPTY_KERNEL");
        require(cUSDC==5e5 && xUSDC==5e5,"DEPTH_NOT_RESET");
        require(kernel.hardCashUSDC()==2e6,"EXTERNAL_DOLLAR_NOT_RETAINED");
        require(usdc.balanceOf(address(vault))==1e6,"RESERVE_NOT_SWEPT");
        require(kernel.spotMarkedNAVUSDC()>marked0,"MARKED_TVL_NOT_UP");
    }
}
