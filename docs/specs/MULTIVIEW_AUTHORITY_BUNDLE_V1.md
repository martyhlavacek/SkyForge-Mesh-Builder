# MultiviewAuthorityBundleV1

The bundle binds an asset ID, supported profile, timestamp, source commit, camera declaration, exact ordered roles (`top`, `front`, `right`), per-view relative path/hash/dimensions/mode/alpha status, optional contact-sheet binding, approval provenance, and canonical SHA-256 digest.

Views must be regular contained files, not absolute paths, traversal paths, symlinks, directories, or composite-only references. Approval is bound to the content digest; any path, image, metadata, profile, or manifest mutation invalidates it. The contact sheet is review convenience and is never submitted as geometric authority.
