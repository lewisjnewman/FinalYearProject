#!/bin/sh

# Delete any previous builds
rm -rf ./target/

# Compile the Smart Contract
solc --abi --bin ./VCS.sol -o target
