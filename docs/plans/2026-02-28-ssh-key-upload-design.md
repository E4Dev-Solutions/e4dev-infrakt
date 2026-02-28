# SSH Key Upload — Design

## Goal

Allow users to upload their own SSH private key files through the web UI, and select managed keys when adding servers.

## Architecture

**Backend:** New `POST /api/keys/upload` endpoint accepts multipart form data (name + private key file). Uses existing `import_key()` from `key_manager.py` which validates the key, copies it to `~/.infrakt/keys/<name>`, extracts the public key and fingerprint, and records it in the `ssh_keys` DB table. Max file size ~10KB. Returns `SSHKeyOut` (same schema as generate).

**Frontend — Settings > SSH Keys:** Add "Upload Key" button next to "Generate Key". Opens a modal with a name input and file picker. After upload, key appears in the existing SSH Keys table identically to generated keys.

**Frontend — Add Server modal:** Replace the plain text `ssh_key_path` input with a dropdown of managed SSH keys from `GET /api/keys`. Options: "None" (no key), each managed key by name, and "Upload new..." (opens the upload modal inline). When a key is selected, `ssh_key_path` is set to its stored path (e.g. `~/.infrakt/keys/my-key`).

**No schema changes needed.** `ssh_key_path` already accepts any string path. The dropdown simply populates it with the managed key's file path.

## Testing

- Backend unit tests: valid key upload, duplicate name rejection, invalid file rejection
- E2E: upload key modal in Settings, key picker dropdown in Add Server modal
