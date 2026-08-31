// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V24 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address who) external view returns (uint256);
}

interface IFlash200V24 {
    function flash(address receiver, uint256 amount, bytes calldata data) external;
}

interface IReflexiveKernelV24 {
    function openTemporaryLiquidity(uint8 activeLeg, uint256 usdcPrincipal) external;
    function executeBuyerQuantum(uint8 activeLeg,uint256 buyerUSDC,address tokenRecipient,uint256 minTokenOut)
        external returns (uint256 tokenOut);
    function closeTemporaryLiquidity(uint8 activeLeg) external returns (uint256 usdcReturned);
    function synchronizeUpward() external returns (uint256 internalUSDCMoved,uint256 burnedRUBC,uint256 burnedRUBX);
    function applyEmissionPolicy(uint16 sellBpsPerUpPct,uint16 burnBpsPerDownPct,uint16 activeBandBps)
        external returns (int256 rubcSupplyDelta,int256 rubxSupplyDelta);
    function resetPriceKernelDepth(uint256 targetUSDCPerLeg)
        external returns (uint256 sweptUSDC,uint256 sweptRUBC,uint256 sweptRUBX);
    function hardCashUSDC() external view returns (uint256);
    function spotMarkedNAVUSDC() external view returns (uint256);
}

/// @notice One fixed $200 Balancer principal is reused N times inside one
/// atomic buyer batch. The topology is fixed; there is no route search.
contract ReflexiveSingleBatchV24 {
    uint256 public constant FLASH_PRINCIPAL = 200e6;
    uint256 public constant BUYER_QUANTUM = 1e6;

    address public owner;
    address public keeper;
    IERC20V24 public immutable USDC;
    IFlash200V24 public immutable flashAdapter;
    IReflexiveKernelV24 public kernel;

    struct Policy {
        uint16 sellBpsPerUpPct;       // 100: sell 1% active band per +1% price
        uint16 burnBpsPerDownPct;     // 200: buy/burn 2% active band per -1%
        uint16 activeBandBps;
        uint16 maxQuanta;
        uint256 minHardCashGainPerQuantum;
        uint256 targetKernelUSDCPerLeg;
    }

    struct Batch {
        uint16 quanta;
        uint8 firstLeg;
        uint256 minTokenOutPerQuantum;
    }

    Policy public policy;
    bool private inFlash;
    uint256 private hardBefore;
    uint256 private markedBefore;
    uint256 private externalUSDCIn;
    address private buyer;

    event BatchSettled(
        uint256 externalUSDCIn,
        uint256 flashPrincipal,
        uint256 cumulativeTempLPNotional,
        uint256 hardCashBefore,
        uint256 hardCashAfter,
        uint256 markedNAVBefore,
        uint256 markedNAVAfter,
        uint256 microcycles
    );

    modifier onlyOwner() { require(msg.sender == owner, "OWNER"); _; }

    constructor(
        address owner_, address keeper_, IERC20V24 usdc_, IFlash200V24 flashAdapter_,
        IReflexiveKernelV24 kernel_, Policy memory p
    ) {
        require(owner_ != address(0) && keeper_ != address(0), "ROLE");
        _validatePolicy(p);
        owner = owner_; keeper = keeper_; USDC = usdc_;
        flashAdapter = flashAdapter_; kernel = kernel_; policy = p;
    }

    function _validatePolicy(Policy memory p) internal pure {
        require(p.sellBpsPerUpPct == 100, "SELL_RULE");
        require(p.burnBpsPerDownPct == 200, "BURN_RULE");
        require(p.activeBandBps > 0 && p.activeBandBps <= 10_000, "BAND");
        require(p.maxQuanta > 0, "QUANTA");
        require(p.targetKernelUSDCPerLeg > 0, "KERNEL_DEPTH");
    }

    function setPolicy(Policy calldata p) external onlyOwner { _validatePolicy(p); policy = p; }
    function setKernel(IReflexiveKernelV24 k) external onlyOwner { require(address(k)!=address(0),"KERNEL"); kernel=k; }

    function executeBatch(Batch calldata b) external {
        require(!inFlash, "ACTIVE");
        require(b.quanta > 0 && b.quanta <= policy.maxQuanta, "QUANTA");
        require(b.firstLeg < 2, "LEG");

        buyer = msg.sender;
        externalUSDCIn = uint256(b.quanta) * BUYER_QUANTUM;
        hardBefore = kernel.hardCashUSDC();
        markedBefore = kernel.spotMarkedNAVUSDC();

        require(USDC.transferFrom(msg.sender,address(this),externalUSDCIn),"BUYER_USDC");
        inFlash = true;
        flashAdapter.flash(address(this),FLASH_PRINCIPAL,abi.encode(b));
        require(!inFlash,"FLASH_CALLBACK");
        require(USDC.approve(address(flashAdapter),0),"FLASH_ALLOWANCE_RESET");

        uint256 hardAfter = kernel.hardCashUSDC();
        uint256 markedAfter = kernel.spotMarkedNAVUSDC();
        require(hardAfter >= hardBefore + uint256(b.quanta)*policy.minHardCashGainPerQuantum,"HARD_CASH_GATE");
        require(markedAfter >= markedBefore,"MARKED_NAV_DOWN");
        require(USDC.balanceOf(address(this)) == 0,"ENGINE_USDC_RESIDUAL");

        emit BatchSettled(externalUSDCIn,FLASH_PRINCIPAL,FLASH_PRINCIPAL*uint256(b.quanta),
            hardBefore,hardAfter,markedBefore,markedAfter,b.quanta);
        buyer = address(0); externalUSDCIn = 0;
    }

    function onFlash(uint256 amount,uint256 fee,bytes calldata data) external {
        require(msg.sender==address(flashAdapter) && inFlash,"FLASH_CALLER");
        require(amount==FLASH_PRINCIPAL,"NOT_200");
        require(fee==0,"NONZERO_FEE");
        Batch memory b=abi.decode(data,(Batch));

        require(USDC.approve(address(kernel),0),"K0");
        require(USDC.approve(address(kernel),type(uint256).max),"K1");

        for(uint256 i=0;i<b.quanta;++i){
            uint8 leg=uint8((uint256(b.firstLeg)+i)&1);
            kernel.openTemporaryLiquidity(leg,FLASH_PRINCIPAL);
            kernel.executeBuyerQuantum(leg,BUYER_QUANTUM,buyer,b.minTokenOutPerQuantum);
            uint256 returned=kernel.closeTemporaryLiquidity(leg);
            require(returned==FLASH_PRINCIPAL,"TEMP_LP_PRINCIPAL");

            // Raise the lagging leg, apply the +1%/-1% asymmetric policy,
            // then synchronize a second time because policy sales can reopen
            // a RUBC/RUBX price gap.
            kernel.synchronizeUpward();
            kernel.applyEmissionPolicy(policy.sellBpsPerUpPct,policy.burnBpsPerDownPct,policy.activeBandBps);
            kernel.synchronizeUpward();

            // REMOVE/ADD-style gradient recharge: keep marginal price but reset
            // permanent USDC depth so the next $1 remains a high-gain price quantum.
            kernel.resetPriceKernelDepth(policy.targetKernelUSDCPerLeg);
        }

        require(USDC.approve(address(kernel),0),"K_RESET");
        require(USDC.approve(address(flashAdapter),0),"F0");
        require(USDC.approve(address(flashAdapter),FLASH_PRINCIPAL),"F1");
        inFlash=false;
    }
}
