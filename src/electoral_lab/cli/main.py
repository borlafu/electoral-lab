"""CLI `electoral`."""

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(help="Electoral Lab: sondeos, incertidumbre, reparto legal y valor marginal del voto (29-N-2026).",
                  no_args_is_help=True)
sources = typer.Typer(help="Fuentes de datos.", no_args_is_help=True)
data = typer.Typer(help="Validación y semillas.", no_args_is_help=True)
app.add_typer(sources, name="sources")
app.add_typer(data, name="data")


@sources.command("refresh")
def sources_refresh(
    only: list[str] | None = typer.Option(None, help="seats, censo, candidacies, polls, results, ep2024"),
    refetch_results: bool = typer.Option(False, help="Volver a descargar las 52 páginas de resultados históricos"),
):
    """Descarga las fuentes, archiva los originales y regenera data/normalized."""
    from electoral_lab.ingestion.refresh import refresh

    for s in refresh(only=only, offline_results=not refetch_results):
        mark = "OK " if s.ok else "ERR"
        typer.echo(f"[{mark}] {s.name:<16} {s.rows:>6} filas  {s.message}")


@sources.command("list")
def sources_list(limit: int = 30):
    """Documentos originales archivados."""
    from electoral_lab.storage import catalog

    for r in catalog.list_raw(limit):
        typer.echo(f"{r['fetched_at']}  {r['source_id']:<32} {r['sha256'][:12]}  {r['url'] or ''}")


@sources.command("import-interior")
def sources_import_interior(zip_path: Path, election: str = typer.Option(..., help="p. ej. congreso_2023")):
    """Importa un ZIP oficial de resultados (infoelectoral.interior.gob.es, ficheros 03/07/08)."""
    from electoral_lab.ingestion import interior

    res, tot = interior.import_zip(zip_path, election)
    typer.echo(f"{len(res)} filas de resultados, {len(tot)} provincias. Guardado en data/normalized (sobrescribe {election}).")


@data.command("validate")
def data_validate():
    """Comprueba integridad y reproduce los escaños oficiales de 2019N y 2023 con el motor legal."""
    from electoral_lab.validation.checks import run_all

    ok = True
    for name, passed, msg in run_all():
        ok &= passed
        typer.echo(f"[{'OK ' if passed else 'ERR'}] {name}: {msg}")
    raise typer.Exit(0 if ok else 1)


@data.command("seed")
def data_seed():
    """Copia data/normalized a data/seed (instantánea incluida en el repositorio)."""
    from electoral_lab.ingestion.refresh import promote_to_seed

    for p in promote_to_seed():
        typer.echo(f"semilla: {p.name}")


@app.command("run")
def run_cmd(
    where: list[str] = typer.Argument(None, help="Circunscripciones o municipios (p. ej. Málaga Madrid Bilbao)"),
    sims: int = typer.Option(None, help="Número de simulaciones (por defecto, config)"),
    pivotal_sims: int = typer.Option(4000, help="Simulaciones usadas por el estimador condicional"),
    seed: int = typer.Option(None),
    config: Path = typer.Option(None, help="YAML de configuración alternativo"),
    set_: list[str] = typer.Option(None, "--set", help="Sobrescribe claves: territorial.sigma_scale=0.7"),
):
    """Ejecución completa: ajuste nacional, simulación, reparto y E_{p,c}."""
    from electoral_lab.geography.catalog import resolve
    from electoral_lab.pipeline import load_config, run

    overrides = {}
    for kv in set_ or []:
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            pass
        overrides[k] = v
    cfg = load_config(config, overrides)
    codes = [resolve(w) for w in (where or ["Málaga", "Madrid", "Bilbao"])]
    out = run(codes, cfg, n_sims=sims, pivotal_sims=pivotal_sims, seed=seed, log=typer.echo)
    typer.echo("")
    _print_report(out)


def _print_report(out: Path):
    import pandas as pd

    man = json.loads((out / "manifest.json").read_text())
    nat = pd.read_csv(out / "national_summary.csv")
    typer.echo(f"Ejecución {man['run_id']}  (último sondeo {man['last_poll']}, {man['n_polls']} sondeos, "
               f"{man['n_sims']} simulaciones)")
    typer.echo("\nEstimación nacional para el 29-N (voto válido, intervalo 90 %):")
    for r in nat.itertuples():
        typer.echo(f"  {r.group:<9} {100 * r.E_mean:5.1f} %  [{100 * r.E_lo:4.1f} – {100 * r.E_hi:4.1f}]  (sin error del día E)")
    seats = pd.read_csv(out / "seats_national.csv")
    typer.echo("\nEscaños (media, intervalo 90 %):")
    for r in seats[seats["mean"] >= 0.05].sort_values("mean", ascending=False).itertuples():
        typer.echo(f"  {r.party:<9} {r.mean:6.1f}  [{r.p05:.0f} – {r.p95:.0f}]   P(1.ª fuerza) {r.p_largest:.0%}")
    b = man["bloc_summary"]
    typer.echo(f"  Bloque derecha ≥176: {b['p_right_majority']:.0%}   bloque izquierda ≥176: {b['p_left_majority']:.0%}")
    if (out / "pivotal.csv").exists():
        piv = pd.read_csv(out / "pivotal.csv", dtype={"province": str})
        for _code, g in piv.groupby("province", sort=False):
            typer.echo(f"\n{g.province_name.iloc[0]} — valor marginal de un voto (E_p,c):")
            typer.echo(f"  {'partido':<9} {'escaños':>7} {'E (por 100k votos)':>19} {'1 entre…':>12} {'M(1000)':>9} {'directo':>9}  desplaza a")
            for r in g.itertuples():
                one = f"{r.one_in:,.0f}" if r.one_in < 1e9 else "—"
                typer.echo(f"  {r.party:<9} {r.seats_mean:7.2f} {r.E_per_100k:19.3f} {one:>12} {r.M1000:9.4f} "
                           f"{r.direct_M1000:9.4f}  {r.top_displaced or ''}")


@app.command("report")
def report_cmd(run_dir: Path = typer.Argument(None)):
    """Muestra el informe de una ejecución (por defecto, la última)."""
    from electoral_lab.pipeline import latest_run

    out = run_dir or latest_run()
    if out is None:
        typer.echo("No hay ejecuciones. Usa: electoral run")
        raise typer.Exit(1)
    _print_report(out)


@app.command("ui")
def ui_cmd(port: int = 8501):
    """Abre la interfaz local (Streamlit)."""
    import subprocess
    import sys

    app_path = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)], check=False)


if __name__ == "__main__":
    app()
