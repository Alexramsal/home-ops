"""Modal deployment entry point for the read-only Home-Ops dashboard."""

import modal

app = modal.App("home-ops-web")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("duckdb", "fastapi", "jinja2")
    .add_local_dir("src", remote_path="/app/src")
    .add_local_file("data/home_ops.duckdb", remote_path="/app/data/home_ops.duckdb")
)


@app.function(image=image, env={"HOME_OPS_DB_PATH": "/app/data/home_ops.duckdb"})
@modal.asgi_app()
def web():
    """Serve the bundled database snapshot without running collection."""
    import sys

    sys.path.insert(0, "/app/src")
    from home_ops.web import app as home_ops_app

    return home_ops_app
