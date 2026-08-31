// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../src/BalancerV2ZeroFee200USDCAdapter.sol";
import "../src/HardTVLDividendVaultV23.sol";
import "../src/AICBFixed200DividendEngineV23.sol";

contract MockERC20V23 {
    string public name;
    string public symbol;
    uint8 public immutable decimals;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory n, string memory s, uint8 d) {
        name = n; symbol = s; decimals = d;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= amount, "ALLOWANCE");
        if (a != type(uint256).max) allowance[from][msg.sender] = a - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "BALANCE");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }
}

contract MockBalancerV2VaultV23 is IBalancerV2VaultFlash {
    uint256 public feeAmount;

    function setFeeAmount(uint256 fee) external { feeAmount = fee; }

    function flashLoan(
        IBalancerV2FlashLoanRecipient recipient,
        IERC20BalancerV2[] memory tokens,
        uint256[] memory amounts,
        bytes memory userData
    ) external override {
        require(tokens.length == 1 && amounts.length == 1, "LENGTH");
        uint256 beforeBal = tokens[0].balanceOf(address(this));
        require(beforeBal >= amounts[0], "LIQUIDITY");
        require(tokens[0].transfer(address(recipient), amounts[0]), "SEND");

        uint256[] memory fees = new uint256[](1);
        fees[0] = feeAmount;
        recipient.receiveFlashLoan(tokens, amounts, fees, userData);

        uint256 afterBal = tokens[0].balanceOf(address(this));
        require(afterBal >= beforeBal + feeAmount, "NOT_REPAID");
    }
}

contract MockTriangleRouterV23 is ITriangleRouterFixed200V23 {
    MockERC20V23 public immutable USDC;
    uint256 public bonus;

    constructor(MockERC20V23 usdc_, uint256 bonus_) {
        USDC = usdc_;
        bonus = bonus_;
    }

    function setBonus(uint256 b) external { bonus = b; }

    function executeTriangle(
        uint8,
        uint256 usdcIn,
        uint256 minUsdcOut,
        bytes calldata
    ) external override returns (uint256 usdcOut) {
        require(USDC.transferFrom(msg.sender, address(this), usdcIn), "PULL");
        usdcOut = usdcIn + bonus;
        require(usdcOut >= minUsdcOut, "MIN_OUT");
        require(USDC.transfer(msg.sender, usdcOut), "RETURN");
    }
}

contract Fixed200BalancerV2Test {
    uint256 constant U = 1e6;

    struct Fixture {
        MockERC20V23 usdc;
        MockERC20V23 rubc;
        MockERC20V23 rubx;
        MockBalancerV2VaultV23 balancer;
        BalancerV2ZeroFee200USDCAdapter adapter;
        HardTVLDividendVaultV23 hardVault;
        MockTriangleRouterV23 router;
        AICBFixed200DividendEngineV23 engine;
    }

    function fixture(uint256 bonus) internal returns (Fixture memory f) {
        f.usdc = new MockERC20V23("USDC", "USDC", 6);
        f.rubc = new MockERC20V23("RUBC", "RUBC", 18);
        f.rubx = new MockERC20V23("RUBX", "RUBX", 18);
        f.balancer = new MockBalancerV2VaultV23();
        f.adapter = new BalancerV2ZeroFee200USDCAdapter(
            address(this),
            IBalancerV2VaultFlash(address(f.balancer)),
            IERC20MetadataBalancerV2(address(f.usdc))
        );
        f.hardVault = new HardTVLDividendVaultV23(address(this), IERC20DividendV23(address(f.usdc)));
        f.router = new MockTriangleRouterV23(f.usdc, bonus);

        AICBFixed200DividendEngineV23.Policy memory p = AICBFixed200DividendEngineV23.Policy({
            minDividendUSDC: 1,
            minHardTVLGainUSDC: 1,
            requireExactSupplyRestoration: true
        });
        f.engine = new AICBFixed200DividendEngineV23(
            address(this), address(this),
            IERC20Fixed200V23(address(f.usdc)), IERC20Fixed200V23(address(f.rubc)), IERC20Fixed200V23(address(f.rubx)),
            IFlashFixed200V23(address(f.adapter)), ITriangleRouterFixed200V23(address(f.router)),
            IHardTVLDividendVaultV23(address(f.hardVault)), p
        );
        f.adapter.bindEngine(address(f.engine));
        f.hardVault.bindEngine(address(f.engine));

        f.usdc.mint(address(f.balancer), 1_000_000 * U);
        f.usdc.mint(address(f.router), 10_000 * U);
        f.rubc.mint(address(this), 1_000_000 ether);
        f.rubx.mint(address(this), 1_000_000 ether);
    }

    function plan(uint256 minOut) internal pure returns (AICBFixed200DividendEngineV23.Plan memory p) {
        p = AICBFixed200DividendEngineV23.Plan({direction: 0, minUsdcOut: minOut, routeData: bytes("")});
    }

    function testFixed200RepaysAndSweepsDividendToHardTVL() external {
        Fixture memory f = fixture(2 * U);
        uint256 balancerBefore = f.usdc.balanceOf(address(f.balancer));
        uint256 cSupply = f.rubc.totalSupply();
        uint256 xSupply = f.rubx.totalSupply();

        uint256 dividend = f.engine.execute200(plan(202 * U));

        require(dividend == 2 * U, "DIVIDEND");
        require(f.usdc.balanceOf(address(f.balancer)) == balancerBefore, "PRINCIPAL_NOT_REPAID");
        require(f.hardVault.hardTVLUSDC() == 2 * U, "HARDTVL");
        require(f.hardVault.cumulativeDividends() == 2 * U, "CUM_DIV");
        require(f.adapter.settledCycles() == 1, "SETTLED");
        require(f.adapter.cumulativePrincipalRepaid() == 200 * U, "REPAID_TOTAL");
        require(f.rubc.totalSupply() == cSupply && f.rubx.totalSupply() == xSupply, "SUPPLY");
    }

    function testNonZeroBalancerFeeRevertsWholeCycle() external {
        Fixture memory f = fixture(2 * U);
        f.balancer.setFeeAmount(1);
        uint256 balancerBefore = f.usdc.balanceOf(address(f.balancer));

        (bool ok,) = address(f.engine).call(abi.encodeWithSelector(AICBFixed200DividendEngineV23.execute200.selector, plan(202 * U)));
        require(!ok, "MUST_REVERT_FEE");
        require(f.usdc.balanceOf(address(f.balancer)) == balancerBefore, "VAULT_CHANGED");
        require(f.hardVault.hardTVLUSDC() == 0, "FAKE_DIVIDEND");
        require(f.adapter.settledCycles() == 0, "FALSE_SETTLE");
    }

    function testNoExternalEdgeCannotCreateDividend() external {
        Fixture memory f = fixture(0);
        uint256 balancerBefore = f.usdc.balanceOf(address(f.balancer));

        (bool ok,) = address(f.engine).call(abi.encodeWithSelector(AICBFixed200DividendEngineV23.execute200.selector, plan(200 * U)));
        require(!ok, "MUST_REVERT_NO_EDGE");
        require(f.usdc.balanceOf(address(f.balancer)) == balancerBefore, "VAULT_CHANGED");
        require(f.hardVault.hardTVLUSDC() == 0, "PRINTED_HARDTVL");
        require(f.adapter.settledCycles() == 0, "FALSE_SETTLE");
    }
}
