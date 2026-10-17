// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AuditAnchor
 * @dev Minimal commitment contract for carbon registry audit reports.
 *
 * This contract provides commitment-only semantics: once a report hash is
 * committed, its timestamp and committer are immutably recorded.
 * No tokens, no funds, no financial operations.
 *
 * Deployment target: testnet (e.g., Sepolia, Mumbai).
 *
 * Hash scheme: SHA-256 of the canonical audit report JSON, as computed by
 * the registry auditor. Solidity's sha256() is compatible with standard
 * SHA-256 and can verify the commitment offline.
 */
contract AuditAnchor {
    /**
     * @dev Map from report hash (bytes32) to block timestamp of commitment.
     * Zero value means never committed.
     */
    mapping(bytes32 => uint256) public committedAt;

    /**
     * @dev Map from report hash (bytes32) to the address of the committer.
     */
    mapping(bytes32 => address) public committerOf;

    /**
     * @dev Emitted when a report hash is committed.
     */
    event Anchored(
        bytes32 indexed reportHash,
        address indexed committer,
        uint256 timestamp
    );

    /**
     * @dev Commit a report hash. Requires not already committed.
     *
     * @param reportHash The SHA-256 hash of the canonical audit report.
     */
    function commit(bytes32 reportHash) external {
        require(
            committedAt[reportHash] == 0,
            "Report hash already committed"
        );

        committedAt[reportHash] = block.timestamp;
        committerOf[reportHash] = msg.sender;

        emit Anchored(reportHash, msg.sender, block.timestamp);
    }

    /**
     * @dev Verify the commitment of a report hash.
     *
     * @param reportHash The SHA-256 hash to verify.
     * @return anchored True if the hash is committed.
     * @return timestamp The block timestamp of commitment (0 if not committed).
     * @return committer The address of the committer (zero if not committed).
     */
    function verify(bytes32 reportHash)
        external
        view
        returns (
            bool anchored,
            uint256 timestamp,
            address committer
        )
    {
        timestamp = committedAt[reportHash];
        anchored = timestamp != 0;
        committer = committerOf[reportHash];
    }
}
