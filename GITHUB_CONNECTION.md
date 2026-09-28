# GitHub synchronization on this workstation

The website can deploy through Vercel independently of a Git push. Never report GitHub synchronization as successful without verifying the remote commit.

On 2026-09-28, a noninteractive push inside the sandbox failed with:
`Unable to persist credentials with the 'wincredman' credential store.`
Outside the sandbox, that error disappeared, but GitHub authentication was unavailable. Secure Git Credential Manager reconnect is required.

For future GitHub fetch/push work:
- Use the user's Windows credential store outside the sandbox when authorized; never copy credentials into files, remote URLs, chat or repo settings.
- Set GIT_TERMINAL_PROMPT=0 and GCM_INTERACTIVE=never for normal automation. A failure should be returned as a clear status, not launch repeated dialogs.
- Scope safe.directory to this exact repository for that invocation; do not trust all directories or change system-wide ownership.
- Stop retrying authentication failures. Request a single user-approved reconnect.
- Capture and inspect the Git process exit code separately from subsequent commands.
- After a push, compare the remote branch SHA with local HEAD. Configure upstream only through a successful push.

The dismissed Windows popup itself was not captured, so its exact message is unconfirmed. No RAM diagnosis has been established.
