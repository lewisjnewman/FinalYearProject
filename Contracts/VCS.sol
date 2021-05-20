pragma solidity >= 0.8.0 < 0.9.0;
pragma experimental ABIEncoderV2;

contract Repository {

    // the owner of this repository
    address owner;

    // The repository name
    string public name;


    struct File {
        // Stores the filepath relative to the top of the repository
        string filePath;

        // Stores the file hash from ipfs which is unique based on the file contents
        string ipfsHash;

        // Parent commit ID
        uint parentCommit;
    }


    struct Commit {

        // The author of this commit
        address author;

        // The id of the branch that this commit belongs to
        uint parentBranchId;

        // Comment attached to this commit (TODO - could this be a hash to a comment file stored on ipfs?)
        string comment;

        // The timestamp for when this commit was created
        uint creation_time;

        // The id of the commit that came before this commit
        uint previous;

        // For 3way merge commits we can have a commit with 2 parents
        bool multi_parent;
        uint previous2;
    }


    struct Branch {

        // The owner of this branch
        address owner;

        // The name that this branch was given
        string name;

        // List of people who are allowed to edit code on a branch
        address[] editors;
    }

    // Where the branch, commit and file data is acutally stored
    Branch[] public branches;
    Commit[] public commits;
    File[] public files;


    constructor(string memory _name) {
        // Set the repository owner to the person deploying this smart contract
        owner = msg.sender;

        // Create the mainline branch
        Branch memory b = Branch(owner, "mainline", new address[](0));     

        // Push the mainline branch onto the list of branches
        branches.push(b);

        // Add the owner of the branch as an editor
        branches[branches.length-1].editors.push(owner);

        // Create an initial commit on the mainline branch with no files in it
        commits.push(Commit(owner, 0, "Null Commit", block.timestamp, 0, false, 0));

        // Set the repository name
        name = _name;
    }

    // Given a branch id, check that the message sender is listed as a branch editor
    modifier CheckBranchAccess(uint _branchID) {
        require(_branchID < branches.length, "Invalid Branch ID");
        
        {

            Branch memory branch = branches[_branchID];

            bool is_ok = false;

            for (uint i = 0; i<branch.editors.length; i++) {
                if (branch.editors[i] == msg.sender){
                    is_ok = true;
                }
            }

            require(is_ok, "Transaction Sender is not part of the branch editors list");

        }

        _;
    }

    // Given a branch id, check that the message sender is the branch owner
    modifier CheckBranchOwner(uint _branchID) {
        require(_branchID < branches.length, "Invalid Branch ID");
        require(msg.sender == branches[_branchID].owner, "Transaction Sender is not the branch owner");
        _;
    }

    // Given a commit id, check that the message sender is the commit owner
    modifier CheckCommitAccess(uint _commitID) {
        require(_commitID < commits.length, "Invalid Commit ID");
        require(msg.sender == commits[_commitID].author, "You are not the owner of this commit");
        _;
    }

    // Function that returns the total number of branches across the repository
    function GetBranchesCount() public view returns(uint) {
        return uint(branches.length);
    }

    // Function that returns the total number of commits across all branches
    function GetCommitsCount() public view returns(uint) {
        return uint(commits.length);
    }

    // Function that returns the total number of commits in a branch
    function GetCommitsCount(uint _branchID) public view returns (uint) {
        require(_branchID < branches.length, "Incorrect Branch ID - GetCommitsCount");

        uint commitCount = 0;
        for(uint i = 0; i < commits.length; i++){
            if (commits[i].parentBranchId == _branchID) {
                commitCount++;
            }
        }
        return commitCount;
    }

    // Function that returns the total number of files in a commit
    function GetFilesCount(uint _commitID) public view returns (uint) {
        require(_commitID < commits.length, "Incorrect Commit ID - GetFilesCount");

        uint fileCount = 0;

        uint i;
        for(i = 0; i < files.length; i++){
            if (files[i].parentCommit == _commitID) {
                fileCount++;
            }
        }

        return fileCount;
    }


    // View that returns the file IDs of all the files that are part of this commit
    function GetFilesFromCommit(uint commitID) public view returns(uint[] memory){
        require(commitID < commits.length, "Incorrect Commit ID - GetFilesFromCommit");

        uint fileCount = GetFilesCount(commitID);

        uint[] memory _files = new uint[](fileCount);

        uint it = 0;

        for(uint i = 0; i < files.length; i++){
            if(files[i].parentCommit == commitID){
                _files[it++] = i;
            }
        }

        return _files;
    }

    // Function that returns a list of IDs of commits given the id of a branch
    function GetCommitsFromBranch(uint branchID) public view returns(uint[] memory){
        require(branchID < branches.length, "Incorrect Branch ID - GetCommitsFromBranch");

        uint commitCount = GetCommitsCount(branchID);

        uint[] memory _commits = new uint[](commitCount);

        uint it = 0;

        for(uint i = 0; i < files.length; i++){
            if(commits[i].parentBranchId == branchID){
                _commits[it++] = i;
            }
        }

        return _commits;
    }

    // Function that returns the most recent commit on a given branch
    function MostRecentCommitID(uint _branchID) public view returns(uint) {
        //Check that the given branch is going to exist
        require(_branchID < branches.length, "Incorrect Branch ID - MostRecentCommitID");

        // Iterate backwards through all the commits to find the most recent commit on the given branch
        uint i;
        for(i = uint(commits.length)-1; i>=0; i--){
            if (commits[i].parentBranchId == _branchID){
                break;
            }
        }

        // Return that commit
        return i;
    }

    // Function that returns a list of IDs of files given the id of a commit
    function GetFilesForCommit(uint _commitID) internal view returns(File[] memory) {
        require(_commitID < commits.length, "Incorrect Commit ID - GetFilesForCommit");


        uint fileCount = GetFilesCount(_commitID);

        File[] memory _files = new File[](fileCount);

        uint j = 0;
        for(uint i = 0; i < files.length; i++){
            if(files[i].parentCommit == _commitID) {
                _files[j++] = files[i];
            }
        }

        return _files;
    }


    // An Internal function for adding a new file to a given commit
    function AddFile(string memory file_path, string memory ipfs_hash, uint commitID) internal {
        files.push(File(file_path, ipfs_hash, commitID));
    }


    // An External function to be used in a transaction to create a new commit and specify the branch it belongs to
    function MakeCommit(uint _branchID, uint previous_commit, string calldata _comment, string calldata file_paths_string, string calldata ipfs_hashes_string) external CheckBranchAccess(_branchID) {

        require(previous_commit == MostRecentCommitID(_branchID), "Unable to add commit, previous commit is not the most recent commit made on this branch");

        string[] memory file_paths = splitString(file_paths_string);
        string[] memory ipfs_hashes = splitString(ipfs_hashes_string);

        require(file_paths.length == ipfs_hashes.length);

        commits.push(Commit(msg.sender, _branchID, _comment, block.timestamp, previous_commit, false, 0));

        for(uint i = 0; i < file_paths.length; i++){
            AddFile(file_paths[i], ipfs_hashes[i], uint(commits.length-1));
        }
    }


    // An Internal function to create a new commit similar to the function above, this is used by the ForkNewBranch function to clone a commit onto a new branch
    function MakeCommitInternal(uint _branchID, uint previous_commit, string memory _comment, File[] memory _files) internal CheckBranchAccess(_branchID) {

        commits.push(Commit(msg.sender, _branchID, _comment, block.timestamp, previous_commit, false, 0));

        for(uint i = 0; i < _files.length; i++){
            AddFile(_files[i].filePath, _files[i].ipfsHash, uint(commits.length-1));
        }
    }


    // An External function used to create a new branch, copying it from an existing branch along with the most recent commit on that branch
    function ForkNewBranch(string memory _name, uint _sourceBranch) public {
        require(_sourceBranch < branches.length);

        owner = msg.sender;

        Branch memory newBranch = Branch(owner, _name, new address[](0));

        branches.push(newBranch);
        
        // Add the owner of the branch as an editor
        branches[branches.length-1].editors.push(owner);

        uint commitID = MostRecentCommitID(_sourceBranch);

        File[] memory _files = GetFilesForCommit(commitID);

        MakeCommitInternal(uint(branches.length-1), commitID, commits[commitID].comment, _files);
    }

    // An External function used to create a squash merge between parent branch and child branch, a single commit is created in the parent branch that has all the changes from the child branch in it
    function SquashMerge(uint parent_branch, uint child_branch, string memory _comment) public CheckBranchAccess(parent_branch) {

        // Get the most recent commit on the child branch
        uint commitID = MostRecentCommitID(child_branch);

        // Get a copy of all the files for that commit
        File[] memory _files = GetFilesForCommit(commitID);

        MakeCommitInternal(parent_branch, commitID, _comment, _files);
    }

    // An External function to be used in a transaction to create a new commit with 2 parents
    function MakeCommitMultiParent(uint parent_branch, uint previous_commit, uint previous2_commit, string calldata _comment, string calldata file_paths_string, string calldata ipfs_hashes_string) external CheckBranchAccess(parent_branch) {

        require(previous_commit == MostRecentCommitID(parent_branch), "Unable to add commit, previous commit is not the most recent commit made on this branch");

        string[] memory file_paths = splitString(file_paths_string);
        string[] memory ipfs_hashes = splitString(ipfs_hashes_string);

        require(file_paths.length == ipfs_hashes.length);

        commits.push(Commit(msg.sender, parent_branch, _comment, block.timestamp, previous_commit, true, previous2_commit));

        for(uint i = 0; i < file_paths.length; i++){
            AddFile(file_paths[i], ipfs_hashes[i], uint(commits.length-1));
        }
    }


    // Extern function to add an editor to a branch
    function AddEditorToBranch(uint _branchID, address new_editor) external CheckBranchOwner(_branchID) {

        // check that the editor has not already been added to the branch
        for(uint i = 0; i < branches[_branchID].editors.length; i++){
            if (new_editor == branches[_branchID].editors[i]){
                // new editor is already an editor of the branch, revert this transaction
                revert();
            }
        }

        // append the editor to the list of approved branch editors
        branches[_branchID].editors.push(new_editor);
    }

    // Extern function to remove an editor from a branch
    function RemoveEditorFromBranch(uint _branchID, address editor) external CheckBranchOwner(_branchID) {

        int index = -1;
        for(uint i = 0; i < branches[_branchID].editors.length; i++){
            if (editor == branches[_branchID].editors[i]){
                index = int(i);
                break;
            }
        }
        if (index == -1){
            //editor is not a member of the branch anyway
            //revert the transaction as nothing will change
            revert();
        }

        // copy the last element to the place of the current element
        branches[_branchID].editors[uint(index)] = branches[_branchID].editors[branches[_branchID].editors.length-1];

        // delete the last element
        delete branches[_branchID].editors[branches[_branchID].editors.length-1];
    }

    function GetBranchEditors(uint _branchID) view external returns(address[] memory) {
        require(_branchID < branches.length, "Not a valid branch id");

        return branches[_branchID].editors;
    }

    // Private Helper function to split a single string delimited by a character into an array of strings
    function splitString(string calldata str) pure internal returns(string[] memory){
        bytes calldata b_str = bytes(str);
        bytes1 delim = ';';

        uint substringcount = 1;
        for(uint i = 0; i < b_str.length; i++){
            if (b_str[i] == delim && i != b_str.length-1){
                substringcount++;
            }
        }

        string[] memory substrings = new string[](substringcount);

        uint it = 0;
        uint current_start = 0;
        uint strcount = 0;
        bytes1 ch;
        do {
            ch = b_str[it];
            if(ch == delim || it == b_str.length){
                bytes memory new_string = b_str[current_start:it];
                substrings[strcount++] = string(new_string);
                current_start = it+1;
            }
            it++;
        } while(it < b_str.length);
        if(ch != delim){
                bytes memory new_string = b_str[current_start:];
                substrings[strcount] = string(new_string);
        }

        return substrings;
    }

}
