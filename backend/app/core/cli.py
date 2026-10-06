from __future__ import annotations

import getpass
import secrets

import click
from flask import Flask


def register_cli(app: Flask) -> None:
    @app.cli.command("seed-platform")
    def seed_platform_cmd():
        """Create/refresh plans, roles, permissions, feature flags, platform settings and email templates (idempotent)."""
        from app.core.tenant import bypass_scope
        from app.services.workspaces import seed_platform

        with bypass_scope():
            seed_platform()
        click.echo("Platform defaults seeded.")

    @app.cli.group("admin")
    def admin_group():
        """Super Admin accounts."""

    @admin_group.command("create")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.option("--role", type=click.Choice(["superadmin", "support", "finance"]), default="superadmin")
    @click.option("--password", default=None, help="Omit to be prompted (recommended) or to generate one with --generate")
    @click.option("--generate", is_flag=True)
    def admin_create(email, name, role, password, generate):
        from app.core.passwords import hash_password, password_problems
        from app.core.tenant import bypass_scope
        from app.extensions import db
        from app.models import AdminUser

        if generate:
            password = secrets.token_urlsafe(18)
            click.echo(f"Generated password (shown once): {password}")
        elif not password:
            password = getpass.getpass("Password: ")
        if len(password) < 12 or password_problems(password):
            raise click.ClickException("Password must be 12+ characters with letters and numbers.")
        with bypass_scope():
            if db.session.query(AdminUser).filter_by(email=email.lower()).first():
                raise click.ClickException("An admin with that email already exists.")
            db.session.add(AdminUser(email=email.lower(), name=name, password_hash=hash_password(password), role=role))
            db.session.commit()
        click.echo(f"Created {role} admin {email}. 2FA enrolment happens at first login.")

    @app.cli.group("jobs")
    def jobs_group():
        """Run background jobs once (useful without a worker)."""

    @jobs_group.command("run")
    def jobs_run():
        from app.jobs import tasks

        for fn in (tasks.billing_lifecycle, tasks.resume_automations, tasks.send_scheduled_emails, tasks.send_reminders, tasks.send_scheduled_reports):
            click.echo(f"{fn.name}: {fn()}")

    @app.cli.command("seed-sample")
    @click.option("--reset", "do_reset", is_flag=True, help="Only remove previously seeded sample customers")
    @click.option("--force", is_flag=True, help="Allow in production (not recommended)")
    def seed_sample_cmd(do_reset, force):
        """Synthetic customers (sample-*) so Super Admin dashboards have data in development."""
        from app.config import Config

        if Config.ENV == "production" and not force:
            raise click.ClickException("Refusing to seed sample data in production.")
        from app.seeds import sample_platform

        if do_reset:
            click.echo(f"Removed {sample_platform.reset()} sample workspaces.")
            return
        click.echo(f"Seeded {sample_platform.seed()}")

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Delete and recreate the demo workspace")
    @click.option("--plan", default="trial", help="trial (default) or a paid plan key such as growth")
    @click.option("--force", is_flag=True, help="Allow in production (not recommended)")
    def seed_demo_cmd(reset, plan, force):
        """Create a clearly-separated demo workspace (is_demo=true) with realistic data."""
        from app.config import Config

        if Config.ENV == "production" and not force:
            raise click.ClickException("Refusing to seed demo data in production. Use --force if you really mean it.")
        from app.seeds.demo import seed_demo

        info = seed_demo(reset=reset, plan=plan)
        click.echo(f"Demo workspace ready.\n  Login: {info['email']} / {info['password']}\n  Workspace: {info['workspace']}\n  Records: {info['counts']}")
