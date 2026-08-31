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
        uint256 maxTempMintRUBC;
        uint256 maxTempMintRUBX;
        uint256 minNetProfitUSDC;
        uint256 minHardTVLGainUSDC;
        uint256 minSolvencyNAVGainUSDC;
        uint256 maxFlashFeeUSDC;
        bool forbidNetSupplyGrowth;
    }
    Policy public policy;

    struct Plan {
        uint8 direction;
        uint256 flashUSDC;
        uint256 minUsdcOut;
        uint256 tempMintRUBC;
        uint256 tempMintRUBX;
        bool remove100Add100;
        bytes routeData;
    }

    struct Snapshot {
        uint256 usdc;
        uint256 cSupply;
        uint256 xSupply;
        uint256 hard;
        int256 nav;
        uint256 cReserve;
        uint256 xReserve;
    }
    Snapshot private snap;
    bool private inCycle;

    event Cycle(uint8 indexed direction, uint256 flashUSDC, uint256 netProfitUSDC, uint256 hardBefore, uint256 hardAfter);

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

    function execute(Plan calldata p) external onlyKeeper returns (uint256 netProfit) {
        require(!inCycle,"ACTIVE");
        require(p.direction < 2,"DIR");
        require(p.flashUSDC <= policy.maxFlashUSDC,"FLASH_CAP");
        require(p.tempMintRUBC <= policy.maxTempMintRUBC && p.tempMintRUBX <= policy.maxTempMintRUBX,"MINT_CAP");

        (uint256 cr,uint256 xr)=crossPool.reserves();
        snap=Snapshot({
            usdc:USDC.balanceOf(address(this)), cSupply:RUBC.totalSupply(), xSupply:RUBX.totalSupply(),
            hard:accounting.hardTVLUSDC(), nav:accounting.solvencyNAVUSDC(), cReserve:cr, xReserve:xr
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
        (uint256 cr2,uint256 xr2)=crossPool.reserves();
        require(cr2==snap.cReserve && xr2==snap.xReserve,"CROSS_NOT_RESTORED");
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

        if(p.remove100Add100){
            require(crossPool.protocolShareBps()==BPS,"CROSS_NOT_100_PROTOCOL");
            (uint256 c0,uint256 x0)=crossPool.reserves();
            (uint256 cOut,uint256 xOut,uint256 shares)=crossPool.removeAllProtocolLiquidity();
            require(cOut==c0 && xOut==x0,"REMOVE100");
            if(p.tempMintRUBC>0) RUBC.cbMint(address(this),p.tempMintRUBC);
            if(p.tempMintRUBX>0) RUBX.cbMint(address(this),p.tempMintRUBX);
            crossPool.addProtocolLiquidity(c0+p.tempMintRUBC,x0+p.tempMintRUBX,shares);
        } else {
            if(p.tempMintRUBC>0) RUBC.cbMint(address(this),p.tempMintRUBC);
            if(p.tempMintRUBX>0) RUBX.cbMint(address(this),p.tempMintRUBX);
        }

        require(USDC.approve(address(router),0),"A0");
        require(USDC.approve(address(router),amount),"A1");
        uint256 out=router.executeTriangle(p.direction,amount,p.minUsdcOut,p.routeData);
        require(out>=p.minUsdcOut,"SLIPPAGE");
        require(USDC.approve(address(router),0),"AR");

        if(p.remove100Add100){
            (uint256 cNow,uint256 xNow,uint256 sharesNow)=crossPool.removeAllProtocolLiquidity();
            require(cNow>=snap.cReserve+p.tempMintRUBC,"RUBC_NOT_RETURNED");
            require(xNow>=snap.xReserve+p.tempMintRUBX,"RUBX_NOT_RETURNED");
            crossPool.addProtocolLiquidity(snap.cReserve,snap.xReserve,sharesNow);
        }

        if(p.tempMintRUBC>0) RUBC.cbBurn(p.tempMintRUBC);
        if(p.tempMintRUBX>0) RUBX.cbBurn(p.tempMintRUBX);
        require(USDC.balanceOf(address(this))>=snap.usdc+amount+fee,"NO_EXTERNAL_SURPLUS");
        require(USDC.approve(address(flash),0),"F0");
        require(USDC.approve(address(flash),amount+fee),"F1");
        inCycle=false;
    }
}
