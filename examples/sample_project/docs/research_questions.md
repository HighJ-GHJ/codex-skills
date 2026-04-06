# Research Questions

The web GPT follow-up should help answer these questions:

1. How should we define the minimal sufficient context for a strategy handoff?
2. Which files belong in the main reading layer, and which ones should remain attachment-only?
3. What should the final reply template require so the output can be saved as `final_reply.md` and later validated by `handoff_id`?
4. How can we make the preview phase clear enough that a user can confidently confirm or regenerate the package?

Known non-goals:

- Do not automate browser sending.
- Do not rely on hidden local state or login profiles.
- Do not rewrite the task as “just implement the feature”.
