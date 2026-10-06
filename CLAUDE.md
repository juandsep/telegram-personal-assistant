# Working rules

- Write clean, modular code that follows industry standards for Python, GCP and Terraform.
- KISS: propose and implement the simplest, most native, direct solution first. Reach for complex approaches only when the simple one fails. Goal: fewer tokens, fast iteration, maintainable code.
- Never push to `main` or `dev`. Cut `feat/`, `fix/` or `chore/` from `dev`, push it, open a PR into `dev` (squash merge). Release = PR `dev` → `main` (merge commit, reviewer-gated). See CONTRIBUTING.md.
- Run `uv run pre-commit run --all-files` before every commit and push.

# Commands

```bash
uv sync                                   # deps
uv run pytest --cov --cov-fail-under=80   # tests (CI gate: 80%)
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pre-commit run --all-files
```

# Infra

- Terraform in `infra/`, state in `gs://jd-botjonh-tfstate`. Project `jd-botjonh`, region `us-central1`.
- Apply only from a reviewed plan: `terraform plan -out=tfplan`, show it, then `terraform apply tfplan`.
- Cloud Run services are deployed by GitHub Actions, not Terraform.
