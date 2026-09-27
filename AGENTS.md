@/Users/m/.codex/RTK.md

# extractfold Agent Notes

- Preserve the public API in `src/extractfold/engines/base.py`.
- Follow the proposal -> failing test -> implementation -> verification loop.
- Unit tests must not require model weights, network, or cloud credentials.
- Optional engines must import heavy dependencies lazily inside methods.
- Base package dependencies must remain empty.

## Durable lessons and owner corrections

- Before finishing substantial work, check whether a recurring mistake, a verified workaround, or an owner correction yields a reusable rule.
- Check existing instructions and skills first. Update the matching rule in place, reconcile contradictions, and avoid duplicate or single-session skills.
- Keep project-specific guidance in this repository; put a reusable workflow in the existing relevant skill. Keep shared policies in AGENTS.md and make them available to Claude Code through CLAUDE.md.
- Turn a fixed behavioral bug into the smallest meaningful regression check, reusing the existing tests or evals. Instruction-only edits need a diff and consistency review, not an artificial test suite.
- Record verified guidance and when it applies. Keep secrets and private client material out of shared instructions and global skills; preserve existing access, approval, and data-storage boundaries.

## Shared instruction alignment

Read this AGENTS.md and the project guidance in [CLAUDE.md](CLAUDE.md) once before working. Shared policies apply to every agent; commands, models, and tools explicitly tied to one runtime apply only to that runtime. CLAUDE.md imports AGENTS.md so both agents receive the same shared rules. When changing a shared policy, update its existing source and reconcile the counterpart in the same change. Do not recursively reload these files.
