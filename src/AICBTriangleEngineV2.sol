// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V2 {
    function balanceOf(address) external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function transfer(address,uint256) external returns (bool);
    function transferFrom(address,address,uint256) external returns (bool);
    function approve(address,uint256) external returns (bool);
}

interface IRUBV2 is IERC20V2 {
    function cbMint(address to, uint256 amount) external;
    function cbBurn(uint256 amount) external;
}

interface IFlashUSDCV2 {
    function flash(address receiver, uint256 amount, bytes calldata data) external;
}

interface ITriangleRouterV2 {
    function executeTriangle(uint8 direction, uint256 usdcIn, uint256 minUsdcOut, bytes calldata routeData)
        external returns (uint256 usdcOut);
}

interface IProtocolCrossPoolV2 {
    function protocolShareBps() external view returns (uint256);
    function reserves() external view returns (uint256 rubcReserve, uint256 rubxReserve);
    function removeAllProtocolLiquidity() external returns (uint256 rubcOut, uint256 rubxOut, uint256 sharesBurned);
    function addProtocolLiquidity(uint256 rubcIn, uint256 rubxIn, uint256 exactSharesToRestore) external;
}

interface IHardAccountingV2 {
    function hardTVLUSDC() external view returns (uint256);
    function solvencyNAVUSDC() external view returns (int256);
}

contract AICBTriangleEngineV2 {
    uint256 constant BPS = 10_000;
    address public owner;
    address public keeper;

    IERC20V2 public immutable USDC;
    IRUBV2 public immutable RUBC;
    IRUBV2 public immutable RUBX;
    IFlashUSDCV2 public flash;
    ITriangleRouterV2 public router;
    IProtocolCrossPoolV2 public crossPool;
    IHardAccountingV2 public accounting;

    struct Policy {
        uint256 maxFlashUSDC;
        uint256 minNetProfitUSDC;
        uint256 minHardTVLGainUSDC;
        uint256 minSolvencyNAVGainUSDC;
        uint256 maxFlashFeeUSDC;
        uint256 maxGradientMintRUBC;
        uint256 maxGradientMintRUBX;
        bool forbidNetSupplyGrowth;
    }
    Policy public policy;

    struct Plan {
        uint8 direction;
        uint256 flashUSDC;
        uint256 minUsdcOut;
        bytes routeData;
    }

    struct Snapshot {
        uint256 usdc;
        uint256 cSupply;
        uint256 xSupply;
        uint256 hard;
        int256 nav;
    }
    Snapshot private snap;
    bool private inCycle;

    event Cycle(uint8 indexed direction, uint256 flashUSDC, uint256 netProfitUSDC, uint256 hardBefore, uint256 hardAfter);
    event GradientReset(uint256 tempMintRUBC, uint256 tempMintRUBX, uint256 rubcReserve, uint256 rubxReserve);

    modifier onlyOwner(){ require(msg.sender==owner,"OWNER"); _; }
    modifier onlyKeeper(){ require(msg.sender==keeper,"KEEPER"); _; }

    constructor(
        address owner_, address keeper_, IERC20V2 usdc_, IRUBV2 rubc_, IRUBV2 rubx_,
        IFlashUSDCV2 flash_, ITriangleRouterV2 router_, IProtocolCrossPoolV2 cross_, IHardAccountingV2 accounting_, Policy memory p
    ) {
        owner=owner_; keeper=keeper_; USDC=usdc_; RUBC=rubc_; RUBX=rubx_;
        flash=flash_; router=router_; crossPool=cross_; accounting=accounting_; policy=p;
    }

    function setPolicy(Policy calldata p) external onlyOwner { policy=p; }
    function setKeeper(address k) external onlyOwner { keeper=k; }

    // Profit primitive: no self-emission is credited as PnL.
    function execute(Plan calldata p) external onlyKeeper returns (uint256 netProfit) {
        require(!inCycle,"ACTIVE");
        require(p.direction < 2,"DIR");
        require(p.flashUSDC <= policy.maxFlashUSDC,"FLASH_CAP");

        snap=Snapshot({
            usdc:USDC.balanceOf(address(this)), cSupply:RUBC.totalSupply(), xSupply:RUBX.totalSupply(),
            hard:accounting.hardTVLUSDC(), nav:accounting.solvencyNAVUSDC()
        });
        inCycle=true;
        flash.flash(address(this),p.flashUSDC,abi.encode(p));
        require(!inCycle,"CALLBACK");

        uint256 afterUSDC=USDC.balanceOf(address(this));
        require(afterUSDC >= snap.usdc,"USDC_LOSS");
        netProfit=afterUSDC-snap.usdc;
        require(netProfit >= policy.minNetProfitUSDC,"PROFIT");
        if(policy.forbidNetSupplyGrowth){
            require(RUBC.totalSupply()<=snap.cSupply,"RUBC_INFLATION");
            require(RUBX.totalSupply()<=snap.xSupply,"RUBX_INFLATION");
        }
        uint256 hardAfter=accounting.hardTVLUSDC();
        int256 navAfter=accounting.solvencyNAVUSDC();
        require(hardAfter>=snap.hard+policy.minHardTVLGainUSDC,"HARDTVL");
        require(navAfter>=snap.nav+int256(policy.minSolvencyNAVGainUSDC),"NAV");
        emit Cycle(p.direction,p.flashUSDC,netProfit,snap.hard,hardAfter);
    }

    function onFlash(uint256 amount, uint256 fee, bytes calldata data) external {
        require(msg.sender==address(flash) && inCycle,"FLASH_CALLER");
        require(fee<=policy.maxFlashFeeUSDC,"FLASH_FEE");
        Plan memory p=abi.decode(data,(Plan));
        require(amount==p.flashUSDC,"FLASH_AMOUNT");

        require(USDC.approve(address(router),0),"A0");
        require(USDC.approve(address(router),amount),"A1");
        uint256 out=router.executeTriangle(p.direction,amount,p.minUsdcOut,p.routeData);
        require(out>=p.minUsdcOut,"SLIPPAGE");
        require(USDC.approve(address(router),0),"AR");

        require(USDC.balanceOf(address(this))>=snap.usdc+amount+fee,"NO_EXTERNAL_SURPLUS");
        require(USDC.approve(address(flash),0),"F0");
        require(USDC.approve(address(flash),amount+fee),"F1");
        inCycle=false;
    }

    // Accounting-neutral REMOVE100 -> ADD100 primitive. It is deliberately
    // separated from profit accounting and must restore reserves/ownership/supply exactly.
    function resetGradientNeutral(uint256 tempMintRUBC, uint256 tempMintRUBX) external onlyKeeper {
        require(!inCycle,"ACTIVE");
        require(crossPool.protocolShareBps()==BPS,"CROSS_NOT_100_PROTOCOL");
        require(tempMintRUBC<=policy.maxGradientMintRUBC && tempMintRUBX<=policy.maxGradientMintRUBX,"GRADIENT_CAP");

        (uint256 c0,uint256 x0)=crossPool.reserves();
        uint256 cs0=RUBC.totalSupply();
        uint256 xs0=RUBX.totalSupply();

        (uint256 cOut,uint256 xOut,uint256 shares)=crossPool.removeAllProtocolLiquidity();
        require(cOut==c0 && xOut==x0,"REMOVE100");

        if(tempMintRUBC>0) RUBC.cbMint(address(this),tempMintRUBC);
        if(tempMintRUBX>0) RUBX.cbMint(address(this),tempMintRUBX);
        crossPool.addProtocolLiquidity(c0+tempMintRUBC,x0+tempMintRUBX,shares);

        (uint256 cTemp,uint256 xTemp,uint256 shares2)=crossPool.removeAllProtocolLiquidity();
        require(cTemp==c0+tempMintRUBC && xTemp==x0+tempMintRUBX,"TEMP_STATE");
        crossPool.addProtocolLiquidity(c0,x0,shares2);

        if(tempMintRUBC>0) RUBC.cbBurn(tempMintRUBC);
        if(tempMintRUBX>0) RUBX.cbBurn(tempMintRUBX);

        (uint256 c1,uint256 x1)=crossPool.reserves();
        require(c1==c0 && x1==x0,"CROSS_NOT_RESTORED");
        require(crossPool.protocolShareBps()==BPS,"LP_OWNERSHIP_CHANGED");
        require(RUBC.totalSupply()==cs0 && RUBX.totalSupply()==xs0,"SUPPLY_NOT_RESTORED");
        emit GradientReset(tempMintRUBC,tempMintRUBX,c1,x1);
    }
}
