@/Users/m/.codex/RTK.md

# extractfold Agent Notes

- Preserve the public API in `src/extractfold/engines/base.py`.
- Follow the proposal -> failing test -> implementation -> verification loop.
- Unit tests must not require model weights, network, or cloud credentials.
- Optional engines must import heavy dependencies lazily inside methods.
- Base package dependencies must remain empty.
