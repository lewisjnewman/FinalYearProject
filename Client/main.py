#!/usr/bin/env python3

import ipfshttpclient
import json
import sys
import os
import argparse
import datetime

from eth_wrapper import RepositoryContractWrapper
from getpass import getpass
from subprocess import Popen, PIPE

# Example .repodata.json file
"""
{
    "repo_name": "testing",
    "repo_address": "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    "current_branch_id": 0,
}
"""

CONNECTION_ADDRESS = "http://localhost:7545"

current_branch = None
current_commit = None


def fetch(repo: RepositoryContractWrapper, commit_id: int):
    """Replace the current local files, their contents and the directory
    structure with the ones specified at the given commit"""

    for root, dirs, files in os.walk("./"):
        for name in files:
            filepath = os.path.join(root, name)

            if filepath == "./.repodata.json":
                # Don't delete the repodata file - that is going to end badly
                continue

            os.remove(filepath)
        for directory in dirs:
            fulldir = os.path.join(root, directory)
            os.rmdir(fulldir)

    file_ids = repo.get_files_from_commit(commit_id)

    ipfs = ipfshttpclient.connect()

    for fid in file_ids:
        filedata = repo.get_file(fid)

        filepath = filedata[0]
        ipfshash = filedata[1]

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as outfile:
            outfile.write(ipfs.cat(ipfshash))


def clone(repo_addr, private_key):
    repo = RepositoryContractWrapper.connect_to_repository(CONNECTION_ADDRESS, private_key, repo_addr)

    # Get the most recent commit on the branch with id 0 - mainline
    commit_id = repo.most_recent_commit(0)

    # Update the local files
    fetch(repo, commit_id)

    # Calculate the current repository data
    repodata = {
        "repo_name": repo.get_repository_name(),
        "repo_address": repo_addr,
        "current_branch_id": 0,
        "current_commit_id": commit_id,
    }

    # Save it to the repodata file
    with open("./.repodata.json", "w") as repodatafile:
        json.dump(repodata, repodatafile)




def checkout(repo: RepositoryContractWrapper, branch_id: int):
    with open("./.repodata.json", "r") as infile:
        repodata = json.load(infile)

    commit_id = repo.most_recent_commit(branch_id)

    fetch(repo, commit_id)

    repodata["current_branch_id"] = branch_id
    repodata["current_commit_id"] = commit_id

    with open("./.repodata.json", "w") as outfile:
        json.dump(repodata, outfile)


def make_commit(repo: RepositoryContractWrapper, commit_message: str):
    ipfs = ipfshttpclient.connect()

    filepaths = []
    ipfs_hashes = []

    for root, dirs, files in os.walk("./"):
        for name in files:
            filepath = os.path.join(root, name)

            if filepath == "./.repodata.json":
                continue

            print(filepath)

            filepaths.append(filepath)
            ipfs_hashes.append(ipfs.add(filepath)["Hash"])

    print(f"filepaths = {filepaths}")
    print(f"ipfs_hashes = {ipfs_hashes}")
    print(f"current_branch = {current_branch}")

    repo.make_commit(filepaths, ipfs_hashes, current_branch, current_commit, comment=commit_message)
    commit_id = repo.most_recent_commit(current_branch)

    with open("./.repodata.json", "r") as infile:
        repodata = json.load(infile)

    repodata["current_commit_id"] = commit_id

    with open("./.repodata.json", "w") as outfile:
        json.dump(repodata, outfile)


def new_branch(repo: RepositoryContractWrapper, branch_name: str):
    repo.fork_new_branch(branch_name, current_branch)


def squash_merge(repo: RepositoryContractWrapper, child_branch, comment):
    if comment is None:
        comment = f"Squash Merge From Branch ID {child_branch}"
    repo.squash_merge(current_branch, child_branch, comment)
    current_commit = repo.most_recent_commit(current_branch)


def get_history(repo: RepositoryContractWrapper, commit_id):
    commit_list = [commit_id]
    while True:
        commit = repo.get_commit(commit_id)
        commit_list.append(commit[4])
        if commit[5]:
            commit_list.append(commit[6])
        if commit[4] == 0:
            break
        commit_id = commit[4]
    return commit_list


def get_all_files_from_commit(repo: RepositoryContractWrapper, commit_id):
    file_id_list = repo.get_files_from_commit(commit_id)
    files = []
    for f in file_id_list:
        files.append(repo.get_file(f))
    return files


def three_way_merge(repo: RepositoryContractWrapper, child_branch, comment):

    # Get the list of commits on the parent branch
    parent_head_commit = repo.most_recent_commit(current_branch)
    parent_head_history = get_history(repo, parent_head_commit)

    # Get the list of commits on the child branch
    child_head_commit = repo.most_recent_commit(child_branch)
    child_head_history = get_history(repo, child_head_commit)

    # Find the common ancestor
    common_ancestor_commit = max(set(parent_head_history) & set(child_head_history))

    # Get the list of file hashes/file paths
    parent_head_files = get_all_files_from_commit(repo, parent_head_commit)
    child_head_files = get_all_files_from_commit(repo, child_head_commit)
    common_ancestor_files = get_all_files_from_commit(repo, common_ancestor_commit)

    # Convert into dictionaries of file_path:ipfs_hash
    parent_head_files = dict(map(lambda x: x[:2], parent_head_files))
    child_head_files = dict(map(lambda x: x[:2], child_head_files))
    common_ancestor_files = dict(map(lambda x: x[:2], common_ancestor_files))

    # list which is going to contain the resulting merge of both commits
    resulting_files = {}

    merge_conflict = False

    for file in parent_head_files.keys() | child_head_files.keys():
        parent_hash = parent_head_files.get(file, None)
        child_hash = child_head_files.get(file, None)
        ancestor_hash = common_ancestor_files.get(file, None)

        if parent_hash == child_hash:
            # Both branches are equal here
            if parent_hash != None:
                resulting_files[file] = parent_hash
        elif parent_hash == ancestor_hash and parent_hash != child_hash:
            # the file has been updated on the child branch but not on the parent branch
            # we take the updates on the child branch
            resulting_files[file] = child_hash
        elif child_hash == ancestor_hash and parent_hash != child_hash:
            # the file has been updated on the parent branch but not on the child branch
            # we take the updates on the parent branch
            resulting_files[file] = parent_hash
        elif parent_hash != child_hash and parent_hash != ancestor_hash and ancestor_hash != child_hash:
            # the same file in both parent and child have been updated independantly causing a merge conflict

            ipfs = ipfshttpclient.connect()

            # write the 3 different copies into temp so that the diff3 program can read them
            with open("/tmp/PARENT", "wb") as outfile:
                outfile.write(ipfs.cat(parent_hash))
            with open("/tmp/CHILD", "wb") as outfile:
                outfile.write(ipfs.cat(child_hash))
            with open("/tmp/BASE", "wb") as outfile:
                outfile.write(ipfs.cat(ancestor_hash))

            process = Popen(["diff3", "-m", "/tmp/PARENT", "/tmp/BASE", "/tmp/CHILD"], stdout=PIPE)
            (output, err) = process.communicate()
            exit_code = process.wait()

            if exit_code == 0:
                #diff3 successfully merged the files together

                # upload the merged file to ipfs
                filehash = ipfs.add_bytes(output)

                # use the merged file hash
                resulting_files[file] = filehash

                pass
            elif exit_code == 1:
                #diff3 could not merge the files together
                print(f"WARNING: could not resolve conflict in file {file}")
                merge_conflict=True
        else:
            # I've missed something here
            raise Exception

    # Return early if there has been a merge conflict
    if merge_conflict == True:
        print("ERROR: Merge Conflicts Detected. Merge Aborted")
        return

    # Convert dictionary into 2 lists
    resulting_files = list(zip(*resulting_files.items()))

    # Create a multi parent commit
    repo.make_commit_multiparent(resulting_files[0], resulting_files[1], current_branch, parent_head_commit, child_head_commit, comment)

    # Update the directory
    fetch(repo, repo.most_recent_commit(current_branch))

    print("Merge Completed")

def list_branches(repo: RepositoryContractWrapper):
    count = repo.get_branch_count()

    for i in range(count):
        branch = repo.get_branch(i)
        print(f"{i} - {branch[1]} owned by {branch[0]}" )


def list_commits(repo: RepositoryContractWrapper):
    # Get the total number of commits there have been
    count = repo.get_commits_count()

    for i in range(count):
        commit = repo.get_commit(i)

        if commit[1]!=current_branch:
            continue

        comment = commit[2]
        owner = commit[0]
        timestamp = datetime.datetime.fromtimestamp(commit[3])

        print(f"Commit Number {i}:\n{comment}\nCommit Made By {owner} at {timestamp}\nPrevious Commit {commit[4]}\n")


def create_repository(new_repository_name, private_key):
    print(f"DEBUG: create_repository({new_repository_name}, {private_key})")

    repo = RepositoryContractWrapper.deploy_new_repository(CONNECTION_ADDRESS, private_key, new_repository_name)

    repodata = {
        "repo_name": new_repository_name,
        "repo_address": repo.repository_address,
        "current_branch_id": 0,
        "current_commit_id": 0,
    }
    with open("./.repodata.json", "w") as repodatafile:
        json.dump(repodata, repodatafile)

    return repo


def load_repository(private_key):
    with open("./.repodata.json", "r") as repodatafile:
        repodata = json.load(repodatafile)

    global current_branch, current_commit
    current_branch = repodata["current_branch_id"]
    current_commit = repodata["current_commit_id"]

    repo = RepositoryContractWrapper.connect_to_repository(CONNECTION_ADDRESS, private_key, repodata["repo_address"])

    return repo


def branch_info(repo: RepositoryContractWrapper):
    branch_data = repo.get_branch(current_branch)
    editors = repo.get_branch_editors(current_branch)

    print(f"Branch ID: {current_branch}")
    print(f"Branch Name: {branch_data[1]}")
    print(f"Branch Owner: {branch_data[0]}")
    print(f"Branch Editors: {editors}")


def add_editor(repo: RepositoryContractWrapper, address: str):
    print(f"Adding \"{address}\" to branch")
    repo.add_editor_to_branch(current_branch, address)


def rm_editor(repo: RepositoryContractWrapper, address: str):
    print(f"Removing \"{address}\" from branch")
    repo.remove_editor_from_branch(current_branch, address)


parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(title="subcommand")

parser_commit = subparsers.add_parser("commit")
parser_commit.set_defaults(subcommand="commit")
parser_commit.add_argument("-m", "--message", help="The Commit message to add")

parser_log = subparsers.add_parser("log")
parser_log.set_defaults(subcommand="log")

parser_branches = subparsers.add_parser("branches")
parser_branches.set_defaults(subcommand="branches")

parser_branch = subparsers.add_parser("branch")
parser_branch.set_defaults(subcommand="branch")
parser_branch.add_argument("branch_name", help="The name of the branch")

parser_checkout = subparsers.add_parser("checkout")
parser_checkout.set_defaults(subcommand="checkout")
parser_checkout.add_argument("branch_id", help="The id of the branch to switch to")

parser_merge = subparsers.add_parser("merge")
parser_merge.set_defaults(subcommand="merge")
parser_merge.add_argument("child_branch_id", help="The id of the branch we are merging from")
parser_merge.add_argument("--squash", action="store_true", help="This merge is a squash merge")
parser_merge.add_argument("-m", "--message", help="The Commit message to add to the resulting merge commit")

parser_init = subparsers.add_parser("init")
parser_init.set_defaults(subcommand="init")
parser_init.add_argument("repo_name", help="The name of the repository")

parser_clone = subparsers.add_parser("clone")
parser_clone.set_defaults(subcommand="clone")
parser_clone.add_argument("repo_address", help="The name of the repository")

parser_branchinfo = subparsers.add_parser("branchinfo")
parser_branchinfo.set_defaults(subcommand="branchinfo")

parser_add_editor = subparsers.add_parser("addeditor")
parser_add_editor.set_defaults(subcommand="addeditor")
parser_add_editor.add_argument("account_address", help="The address of the account you want to add as an editor")

parser_rm_editor = subparsers.add_parser("rmeditor")
parser_rm_editor.set_defaults(subcommand="rmeditor")
parser_rm_editor.add_argument("account_address", help="The address of the account you want to remove as an editor")

parser_branchinfo = subparsers.add_parser("branchinfo")
parser_branchinfo.set_defaults(subcommand="branchinfo")

parser_fetch = subparsers.add_parser("fetch")
parser_fetch.set_defaults(subcommand="fetch")
parser_fetch.add_argument("commit_id", help="The id of the commit that you want to fetch")    

def main(args):
    try:
        args.subcommand
    except AttributeError as e:
        print(f"DEBUG: {e}")
        parser.print_help()
        exit(0)

    private_key = os.getenv("VCS_PRIVATE_KEY") or getpass("Private Key: ")

    if args.subcommand == "init":
        create_repository(args.repo_name, private_key)
    elif args.subcommand == "clone":
        clone(args.repo_address, private_key)
    elif args.subcommand == "branches":
        repo = load_repository(private_key)
        list_branches(repo)
    elif args.subcommand == "branch":
        repo = load_repository(private_key)
        new_branch(repo, args.branch_name)
    elif args.subcommand == "branchinfo":
        repo = load_repository(private_key)
        branch_info(repo)
    elif args.subcommand == "addeditor":
        repo = load_repository(private_key)
        add_editor(repo, args.account_address)
    elif args.subcommand == "rmeditor":
        repo = load_repository(private_key)
        rm_editor(repo, args.account_address)
    elif args.subcommand == "checkout":
        repo = load_repository(private_key)
        checkout(repo, int(args.branch_id))
    elif args.subcommand == "commit":
        repo = load_repository(private_key)
        make_commit(repo, args.message)
    elif args.subcommand == "merge":
        repo = load_repository(private_key)
        if args.squash:
            squash_merge(repo, int(args.child_branch_id), args.message)
        else:
            three_way_merge(repo, int(args.child_branch_id), args.message)
    elif args.subcommand == "fetch":
        repo = load_repository(private_key)
        fetch(repo, int(args.commit_id))
    elif args.subcommand == "log":
        repo = load_repository(private_key)
        list_commits(repo)
    else:
        parser.print_help()


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)
