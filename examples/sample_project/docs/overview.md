# Sample Project Overview

The sample project explores how to package a local strategy discussion so that a web GPT session can continue the reasoning without direct access to the Codex thread.

Current constraints:

- The handoff package must stay lightweight and portable.
- The manifest must remain machine-readable and use only repo-relative paths.
- The workflow must separate preview from final confirmation.
- The result should help continue research and option comparison, not trigger direct code implementation.

The current team concern is that too much context makes the handoff noisy, while too little context makes the external model miss important assumptions. The sample exists to show how the skill balances that trade-off.
