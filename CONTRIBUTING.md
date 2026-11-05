# Contributing to FitAI

Thanks for helping improve FitAI. This is the short version; [`AGENTS.MD`](AGENTS.MD) holds the detailed
architecture conventions and module ownership rules.

## Workflow

1. Fork the repository and create a branch from `main` (for example `feat/<topic>` or `fix/<topic>`).
   Do not commit to `main` directly.
2. Set up your environment with [`docs/setup.md`](docs/setup.md).
3. Keep each change small and focused, and add or update tests with every behaviour change.
4. Run the checks below before opening a pull request.
5. Open a pull request into `main` describing what changed, why, and which checks you ran. Keep meaningful
   commits separate (merge with a merge commit rather than squashing, if you maintain the repository).

## Checks

```bash
# backend/
python -m pytest -q
ruff check . && ruff format --check .

# frontend/
npm run lint && npm run type-check && npm test && npm run build
```

## Conventions

- **Architecture.** Router → Schema → Service → Repository → Model. Routers stay thin; business logic lives in
  services; only repositories touch the database. The AI engine reaches persistence through services.
- **Security.** Never commit secrets or `.env` files; update `.env.example` with placeholders only. Every route
  must be authenticated and scoped to the current user. Treat model output and uploaded files as untrusted.
- **Truthful behaviour.** FitAI must not invent personal data or numbers; calculations belong in deterministic
  code, not the model.
- **Style.** Python is formatted and linted with Ruff and uses type hints on public functions; the frontend is
  strict TypeScript linted with oxlint.
- **Commits.** One logical change per commit with a clear one-line message (for example
  `fix: handle empty document upload`).

## Reporting security issues

Do not open a public issue. Follow [`SECURITY.md`](SECURITY.md).

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
