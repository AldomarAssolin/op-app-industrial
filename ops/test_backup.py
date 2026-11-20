"""Ensaios de falhas: sem Docker, rede ou credenciais reais."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops import backup as module


class BackupTests(unittest.TestCase):
    def simulate(self, failure=None):
        self.remote = {}
        self.deleted = []
        self.listed = False
        self.old = "op-app-20000101T000000Z-1234abcd.dump"
        self.remote[self.old] = b"old"

        def fake(*args, output=False, stdin=None, stdout=None):
            if args[:3] == ("rclone", "listremotes", "--long"):
                return "opbackup: crypt backup cifrado\nopdrive: drive"
            if args[:2] == ("docker", "ps"):
                return "db1\ndb2" if failure == "replicas" else "db1"
            if "pg_dump" in args:
                stdout.write(b"dump valido")
                if failure == "dump":
                    raise RuntimeError("pg_dump falhou")
            elif "pg_restore" in args:
                if failure == "index":
                    raise RuntimeError("indice invalido")
            elif args[:2] == ("rclone", "copyto"):
                source, target = args[2:4]
                if source.startswith("opbackup:"):
                    data = self.remote[source.rsplit("/", 1)[1]]
                    if failure == "corrupt" and source.endswith(".dump"):
                        data = b"corrompido"
                    Path(target).write_bytes(data)
                else:
                    if failure == "upload":
                        raise RuntimeError("Drive indisponivel")
                    self.remote[target.rsplit("/", 1)[1]] = Path(source).read_bytes()
            elif args[:2] == ("rclone", "lsf"):
                self.listed = True
                return "\n".join(self.remote) + "\nnao-apagar.txt"
            elif args[:2] == ("rclone", "deletefile"):
                self.deleted.append(args[2].rsplit("/", 1)[1])
        return fake

    def execute(self, directory):
        module.backup(directory, "example_db", "example_pilot", "opbackup:op-app-diario")

    def test_sucesso_so_limpa_arquivos_antigos_da_rotina(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            old = directory / "op-app-20000101T000000Z-1234abcd.dump"
            old.write_bytes(b"old")
            unrelated = directory / "manual.dump"
            unrelated.write_bytes(b"keep")
            with patch.object(module, "run", side_effect=self.simulate()):
                self.execute(directory)
            self.assertEqual(self.deleted, [self.old])
            self.assertFalse(old.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue((directory / "last-success").exists())
            self.assertEqual(len(list(directory.glob("op-app-*.dump"))), 1)

    def test_falhas_nao_aplicam_retencao_nem_registram_sucesso(self):
        for failure in ("dump", "index", "upload", "corrupt", "replicas"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                directory = Path(root)
                with patch.object(module, "run", side_effect=self.simulate(failure)):
                    with self.assertRaises(RuntimeError):
                        self.execute(directory)
                self.assertFalse(self.listed)
                self.assertEqual(self.deleted, [])
                self.assertFalse((directory / "last-success").exists())
                if failure in ("dump", "index", "replicas"):
                    self.assertEqual(list(directory.glob("*.dump")), [])

    def test_destino_sem_criptografia_e_rejeitado(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(module, "run", return_value="opbackup: drive"):
                with self.assertRaisesRegex(ValueError, "crypt"):
                    self.execute(Path(root))

    def test_retencao_nao_aceita_caminhos_ou_nome_manual(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        for name in ("../op-app-20000101T000000Z-1234abcd.dump", "manual.dump", "op-app-20261117T235624Z.dump"):
            self.assertFalse(module.expired(name, cutoff))


if __name__ == "__main__":
    unittest.main()
