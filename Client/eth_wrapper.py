from web3 import Web3, HTTPProvider
import pathlib
import json
from coincurve import PublicKey
from sha3 import keccak_256

CONTRACT_BUILD_DIR = pathlib.Path(__file__).parent.parent.absolute() / "Contracts" / "target"

CONTRACT_BIN_FILEPATH = str(CONTRACT_BUILD_DIR / "Repository.bin")
CONTRACT_ABI_FILEPATH = str(CONTRACT_BUILD_DIR / "Repository.abi")

contract_abi = json.load(open(CONTRACT_ABI_FILEPATH, "r"))

with open(CONTRACT_BIN_FILEPATH, "r") as infile:
    contract_bin = infile.read()


class RepositoryContractWrapper(object):
    """Class that wraps the calls to the solidity smart contract"""
    def __init__(self, conn_url, private_key):
        self.w3 = Web3(HTTPProvider(conn_url))

        self._private_key = private_key
        self._account_address = self.w3.toChecksumAddress(self._private_key_to_address(self._private_key))
        self.repository_address = None

        # Check that we are actually connected
        assert self.w3.isConnected()


    def _private_key_to_address(self, private_key):
        if private_key[0:2] == "0x":
            private_key = private_key[2:]

        private_key = bytes.fromhex(private_key)
        public_key = PublicKey.from_valid_secret(private_key).format(compressed=False)[1:]
        addr = keccak_256(public_key).digest()[-20:]
        return addr.hex()


    def _make_transaction(self):
        ret = {
            "nonce": self.w3.eth.getTransactionCount(account=self._account_address),
            "gas": 6000000,
            "gasPrice": self.w3.toWei("50", "gwei")
        }

        return ret


    @classmethod
    def connect_to_repository(cls, conn_url, private_key, repository_address):
        self = cls(conn_url, private_key)

        self.repository_address = self.w3.toChecksumAddress(repository_address)

        self._repo_contract = self.w3.eth.contract(address=self.repository_address, abi=contract_abi)

        return self


    @classmethod
    def deploy_new_repository(cls, conn_url, private_key, repository_name):
        self = cls(conn_url, private_key)

        # Create a contract object from the bytecode and abi
        self._repo_contract = self.w3.eth.contract(bytecode=contract_bin, abi=contract_abi)

        # Call the contract constructor
        tx = self._repo_contract.constructor(repository_name).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)


        # wait for the transaction to be mined
        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)

        # Create a new transaction object with the new deployed contract address
        self._repo_contract = self.w3.eth.contract(address=tx_receipt.contractAddress, abi=contract_abi)
        self.repository_address = tx_receipt.contractAddress

        return self


    def make_commit(self, file_paths, ipfs_hashes, branch_id, previous_commit, comment=""):

        file_paths = ';'.join(file_paths)
        ipfs_hashes = ';'.join(ipfs_hashes)

        MakeCommitFunction = self._repo_contract.get_function_by_name("MakeCommit")

        # Make the smart contract Transaction
        tx = MakeCommitFunction(branch_id, previous_commit, comment, file_paths, ipfs_hashes).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)


    def make_commit_multiparent(self, file_paths, ipfs_hashes, branch_id, parent1, parent2, comment=""):

        file_paths = ';'.join(file_paths)
        ipfs_hashes = ';'.join(ipfs_hashes)

        # Make the smart contract Transaction
        tx = self._repo_contract.functions.MakeCommitMultiParent(branch_id, parent1, parent2, comment, file_paths, ipfs_hashes).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)


    def fork_new_branch(self, branch_name, parent):

        tx = self._repo_contract.functions.ForkNewBranch(branch_name, parent).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)


    def squash_merge(self, parent_branch_id:int, child_branch_id:int, squash_commit_message:str):

        tx = self._repo_contract.functions.SquashMerge(parent_branch_id, child_branch_id, squash_commit_message).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)

    def add_editor_to_branch(self, branch_id, account_address):
        AddEditorToBranch = self._repo_contract.get_function_by_name("AddEditorToBranch")

        account_address = self.w3.toChecksumAddress(account_address)

        # Make the smart contract Transaction
        tx = AddEditorToBranch(branch_id, account_address).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)

    def remove_editor_from_branch(self, branch_id, account_address):
        RemoveEditorFromBranch = self._repo_contract.get_function_by_name("RemoveEditorFromBranch")

        account_address = self.w3.toChecksumAddress(account_address)

        # Make the smart contract Transaction
        tx = RemoveEditorFromBranch(branch_id, account_address).buildTransaction(self._make_transaction())
        signed_tx = self.w3.eth.account.signTransaction(tx, self._private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)

        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)


    def get_branch(self, id):
        return self._repo_contract.functions.branches(id).call()


    def get_commit(self, id):
        return self._repo_contract.functions.commits(id).call()


    def get_file(self, id):
        return self._repo_contract.functions.files(id).call()


    def get_branch_count(self):
        return self._repo_contract.functions.GetBranchesCount().call()


    def get_commits_count(self, branch_id=None):
        if branch_id is None:
            return self._repo_contract.functions.GetCommitsCount().call()
        elif isinstance(branch_id, int):
            return self._repo_contract.functions.GetCommitsCount(branch_id).call()


    def get_files_count(self, commit_id):
        return self._repo_contract.functions.GetFilesCount(commit_id).call()


    def get_files_from_commit(self, commit_id):
        return self._repo_contract.functions.GetFilesFromCommit(commit_id).call()


    def get_commits_from_branch(self, branch_id):
        return self._repo_contract.functions.GetCommitsFromBranch(branch_id).call()


    def most_recent_commit(self, branch_id):
        return self._repo_contract.functions.MostRecentCommitID(branch_id).call()

    def get_repository_name(self):
        return self._repo_contract.functions.name().call()

    def get_branch_editors(self, branch_id):
        return self._repo_contract.functions.GetBranchEditors(branch_id).call()

# This is here just for testing
if __name__ == "__main__":
    print(f"Contract Binary File \'{contract_bin}\'")
    print(f"Contract Binary File \'{contract_abi}\'")
