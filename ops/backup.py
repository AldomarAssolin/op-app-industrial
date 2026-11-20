#!/usr/bin/env python3
"""Backup PostgreSQL via Docker + rclone crypt. Executar no host, não no App."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4


NAME = re.compile(r"op-app-(\d{8}T\d{6}Z)-[a-f0-9]{8}\.dump(?:\.sha256)?\Z")


def run(*args, output=False, stdin=None, stdout=None):
    result = subprocess.run(
        args, stdin=stdin, stdout=subprocess.PIPE if output else (stdout or subprocess.DEVNULL),
        stderr=subprocess.PIPE, timeout=1800, check=False,
    )
    if result.returncode:
        # Não divulgar saída de ferramentas: pode conter configuração sensível.
        raise RuntimeError(f"{args[0]} falhou (código {result.returncode}); verificar no host")
    return result.stdout.decode().strip() if output else None


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expired(name, cutoff):
    match = NAME.fullmatch(name)
    return bool(match and datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) < cutoff)


def backup(directory, service, database, remote, retention=30):
    if retention < 1 or not re.fullmatch(r"[\w-]+", service) or not re.fullmatch(r"[\w-]+", database):
        raise ValueError("Serviço, banco ou retenção inválidos")
    # Subpasta exclusiva para esta rotina; nunca limpar a raiz do remoto.
    if not re.fullmatch(r"[\w-]+:op-app-diario", remote):
        raise ValueError("Destino deve ser REMOTO:op-app-diario")
    remote_name = remote.split(":")[0] + ":"
    remotes = run("rclone", "listremotes", "--long", output=True)
    if not any(line.split()[:2] == [remote_name, "crypt"] for line in remotes.splitlines()):
        raise ValueError("O destino precisa ser um remoto rclone do tipo crypt")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    with (directory / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        containers = run("docker", "ps", "--filter", f"label=com.docker.swarm.service.name={service}",
                         "--filter", "status=running", "--format", "{{.ID}}", output=True).splitlines()
        if len(containers) != 1:
            raise RuntimeError("Esperado exatamente um contêiner local do banco; nenhuma cópia ou limpeza realizada")
        container = containers[0]
        now = datetime.now(timezone.utc)
        name = f"op-app-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.dump"
        dump = directory / name
        # Temporário só vira dump final após pg_dump e leitura do índice.
        with tempfile.TemporaryDirectory(dir=directory, prefix=".work-") as work:
            work = Path(work)
            pending = work / name
            with pending.open("wb") as stream:
                run("docker", "exec", "-u", "postgres", container, "pg_dump", "--no-password",
                    "-U", "postgres", "--format=custom", "--dbname", database, stdout=stream)
            if not pending.stat().st_size:
                raise RuntimeError("Dump vazio")
            with pending.open("rb") as stream:
                run("docker", "exec", "-i", "-u", "postgres", container, "pg_restore", "--list", stdin=stream)
            pending.rename(dump)
            checksum = sha256(dump)
            manifest = directory / (name + ".sha256")
            manifest.write_text(f"{checksum}  {name}\n")
            for path in (dump, manifest):
                run("rclone", "copyto", str(path), f"{remote}/{path.name}", "--immutable")
            downloaded = work / "download.dump"
            downloaded_manifest = work / "download.sha256"
            run("rclone", "copyto", f"{remote}/{name}", str(downloaded))
            run("rclone", "copyto", f"{remote}/{name}.sha256", str(downloaded_manifest))
            if sha256(downloaded) != checksum or downloaded_manifest.read_bytes() != manifest.read_bytes():
                raise RuntimeError("Integridade da cópia externa não confirmada; retenção não aplicada")
        # Limpeza só ocorre após um novo backup recuperado e conferido.
        cutoff = now - timedelta(days=retention)
        files = run("rclone", "lsf", remote, "--files-only", "--max-depth", "1", output=True).splitlines()
        for name in files:
            if expired(name, cutoff):
                run("rclone", "deletefile", f"{remote}/{name}")
        for path in directory.iterdir():
            if path.is_file() and not path.is_symlink() and expired(path.name, cutoff):
                path.unlink()
        # Marcador atualizado somente após todas as etapas concluídas.
        marker = directory / ".last-success.tmp"
        marker.write_text(datetime.now(timezone.utc).isoformat() + "\n")
        marker.replace(directory / "last-success")
        print("Backup enviado, recuperado e conferido; retenção aplicada.", flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        backup(Path(os.environ["OP_BACKUP_DIR"]), os.environ["OP_DB_SERVICE"],
               os.environ["OP_DATABASE"], os.environ["OP_BACKUP_REMOTE"],
               int(os.environ.get("OP_RETENTION_DAYS", "30")))
    except Exception as error:
        print(f"FALHA no backup: {error}", flush=True)
        raise SystemExit(1)
