// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../src/BaseV3Adapter.sol";

interface Vm { function envString(string calldata) external returns(string memory); function createSelectFork(string calldata) external returns(uint256); }

contract BaseForkQuoteTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function testBaseQuoterAndRouterCode() public {
        string memory rpc = vm.envString("BASE_RPC_URL");
        vm.createSelectFork(rpc);
        address quoter = 0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a;
        address router = 0x2626664c2603336E57B271c5C0b26F421741e481;
        address pool = 0xd0b53D9277642d899DF5C87A3966A349A798F224;
        require(quoter.code.length > 0, "NO_QUOTER");
        require(router.code.length > 0, "NO_ROUTER");
        require(pool.code.length > 0, "NO_POOL");
    }
}
