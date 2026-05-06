from __future__ import annotations

import typer

from deeptutor.auth.cli_session import clear_cli_session, get_cli_user, save_cli_session
from deeptutor.auth.migration import migrate_legacy_data_to_user
from deeptutor.auth.passwords import hash_password, verify_password
from deeptutor.auth.store import UserAlreadyExists, get_auth_store


def register(app: typer.Typer) -> None:
    @app.command("register")
    def register_user(
        email: str = typer.Option(..., "--email", prompt=True),
        password: str = typer.Option(..., "--password", prompt=True, hide_input=True),
        display_name: str = typer.Option("", "--display-name"),
    ) -> None:
        store = get_auth_store()
        is_first_user = store.count_users() == 0
        try:
            user = store.create_user(
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
            )
        except UserAlreadyExists as exc:
            typer.echo("Email already registered.")
            raise typer.Exit(code=1) from exc
        if is_first_user:
            migrate_legacy_data_to_user(user.id)
        session = store.create_session(user.id, user_agent="deeptutor-cli")
        save_cli_session(token=session.token, user=user)
        typer.echo(f"Registered and logged in as {user.email}.")

    @app.command("login")
    def login(
        email: str = typer.Option(..., "--email", prompt=True),
        password: str = typer.Option(..., "--password", prompt=True, hide_input=True),
    ) -> None:
        store = get_auth_store()
        user = store.get_user_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            typer.echo("Invalid email or password.")
            raise typer.Exit(code=1)
        session = store.create_session(user.id, user_agent="deeptutor-cli")
        save_cli_session(token=session.token, user=user)
        typer.echo(f"Logged in as {user.email}.")

    @app.command("logout")
    def logout() -> None:
        clear_cli_session()
        typer.echo("Logged out.")

    @app.command("me")
    def me() -> None:
        user = get_cli_user()
        if user is None:
            typer.echo("Not logged in.")
            raise typer.Exit(code=1)
        typer.echo(f"{user.email} ({user.id})")
