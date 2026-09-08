# Security and privacy

JobScout is local-first and does not require credentials for the bundled public sources. Runtime state, user configuration, and generated outputs are ignored by Git by default.

Do not commit:

- personal application history,
- private API credentials,
- resumes or cover letters containing personal contact information,
- `data/` or `output/` directories from a real search.

If you add an authenticated source, load secrets from environment variables rather than source control.
