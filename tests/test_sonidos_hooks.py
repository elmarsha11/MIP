"""
Tests de los hooks de sonido (.claude/hooks/sonidos_claude.py).

No reproducen audio: interceptan el lanzador de procesos y verifican que cada
evento elija el .wav correcto. Los .wav se simulan con archivos vacios en un
directorio temporal.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUTA_HOOK = PROJECT_ROOT / ".claude" / "hooks" / "sonidos_claude.py"

_spec = importlib.util.spec_from_file_location("sonidos_claude", RUTA_HOOK)
sonidos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sonidos)


NOMBRES_WAV = [
    "empieza.wav",
    "Solicitud.wav",
    "Continua.wav",
    "Finalizo.wav",
    "Token.wav",
]


class BaseSonidos(unittest.TestCase):
    """Aisla el estado en disco y captura los .wav que se habrian reproducido."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)

        self.carpeta_wav = base / "Sonidos de Claudio"
        self.carpeta_wav.mkdir()
        for nombre in NOMBRES_WAV:
            (self.carpeta_wav / nombre).write_bytes(b"")

        self.carpeta_estado = base / "estado"
        self.carpeta_estado.mkdir()

        self.reproducidos: list[str] = []

        # La carpeta de sonidos y la de estado se redirigen al temporal.
        self._orig_carpeta = sonidos._carpeta_sonidos
        self._orig_ruta_estado = sonidos._ruta_estado
        self._orig_lanzar = sonidos._lanzar_desacoplado
        self._orig_which = sonidos.shutil.which
        self._orig_platform = sonidos.sys.platform

        sonidos._carpeta_sonidos = lambda: self.carpeta_wav
        sonidos._ruta_estado = lambda sid: self.carpeta_estado / f"{sid}.json"
        sonidos._lanzar_desacoplado = lambda argv: self.reproducidos.append(
            Path(argv[-1]).name
        )
        # Fingimos Linux con paplay disponible para tener un camino estable.
        sonidos.sys.platform = "linux"
        sonidos.shutil.which = lambda prog: "/usr/bin/paplay" if prog == "paplay" else None

    def tearDown(self) -> None:
        sonidos._carpeta_sonidos = self._orig_carpeta
        sonidos._ruta_estado = self._orig_ruta_estado
        sonidos._lanzar_desacoplado = self._orig_lanzar
        sonidos.shutil.which = self._orig_which
        sonidos.sys.platform = self._orig_platform
        self._tmp.cleanup()

    def evento(self, nombre: str, **extra) -> None:
        payload = {
            "hook_event_name": nombre,
            "session_id": "s1",
            "prompt_id": "turno-1",
        }
        payload.update(extra)
        sonidos.manejar(payload)


class TestEmpieza(BaseSonidos):
    def test_suena_con_herramienta_de_desarrollo(self) -> None:
        self.evento("PreToolUse", tool_name="Edit")
        self.assertEqual(self.reproducidos, ["empieza.wav"])

    def test_bash_tambien_cuenta(self) -> None:
        self.evento("PreToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["empieza.wav"])

    def test_no_suena_leyendo_o_buscando(self) -> None:
        for herramienta in ("Read", "Grep", "Glob", "WebFetch", "TodoWrite"):
            self.evento("PreToolUse", tool_name=herramienta)
        self.assertEqual(self.reproducidos, [])

    def test_una_sola_vez_por_turno(self) -> None:
        self.evento("PreToolUse", tool_name="Edit")
        self.evento("PreToolUse", tool_name="Write")
        self.evento("PreToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["empieza.wav"])

    def test_vuelve_a_sonar_en_el_turno_siguiente(self) -> None:
        self.evento("PreToolUse", tool_name="Edit", prompt_id="turno-1")
        self.evento("PreToolUse", tool_name="Edit", prompt_id="turno-2")
        self.assertEqual(self.reproducidos, ["empieza.wav", "empieza.wav"])

    def test_stop_rearma_el_turno(self) -> None:
        """Sin prompt_id el reset lo hace Stop, no el identificador de turno."""
        self.evento("PreToolUse", tool_name="Edit", prompt_id=None)
        self.evento("PreToolUse", tool_name="Edit", prompt_id=None)
        self.evento("Stop")
        self.evento("PreToolUse", tool_name="Edit", prompt_id=None)
        self.assertEqual(
            self.reproducidos, ["empieza.wav", "Finalizo.wav", "empieza.wav"]
        )


class TestSolicitudYContinua(BaseSonidos):
    def test_permiso_suena_solicitud(self) -> None:
        self.evento("Notification")
        self.assertEqual(self.reproducidos, ["Solicitud.wav"])

    def test_continua_solo_despues_de_un_permiso(self) -> None:
        self.evento("Notification")
        self.evento("PostToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["Solicitud.wav", "Continua.wav"])

    def test_sin_permiso_previo_no_suena_continua(self) -> None:
        self.evento("PostToolUse", tool_name="Bash")
        self.evento("PostToolUse", tool_name="Edit")
        self.assertEqual(self.reproducidos, [])

    def test_la_marca_se_consume_una_sola_vez(self) -> None:
        self.evento("Notification")
        self.evento("PostToolUse", tool_name="Bash")
        self.evento("PostToolUse", tool_name="Bash")
        self.evento("PostToolUse", tool_name="Edit")
        self.assertEqual(self.reproducidos, ["Solicitud.wav", "Continua.wav"])

    def test_permiso_rechazado_no_suena_continua(self) -> None:
        self.evento("Notification")
        self.evento("PermissionDenied", tool_name="Bash")
        self.evento("PostToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["Solicitud.wav"])

    def test_permiso_vencido_no_suena_continua(self) -> None:
        self.evento("Notification")
        estado = json.loads((self.carpeta_estado / "s1.json").read_text())
        estado["permiso_aprobado_pendiente"] -= sonidos.VENTANA_PERMISO_S + 60
        (self.carpeta_estado / "s1.json").write_text(json.dumps(estado))

        self.evento("PostToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["Solicitud.wav"])

    def test_stop_descarta_permiso_pendiente(self) -> None:
        self.evento("Notification")
        self.evento("Stop")
        self.evento("PostToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["Solicitud.wav", "Finalizo.wav"])


class TestFinalizoYToken(BaseSonidos):
    def test_stop_suena_finalizo(self) -> None:
        self.evento("Stop")
        self.assertEqual(self.reproducidos, ["Finalizo.wav"])

    def test_rate_limit_suena_token(self) -> None:
        self.evento("StopFailure")
        self.assertEqual(self.reproducidos, ["Token.wav"])


class TestAislamientoEntreSesiones(BaseSonidos):
    def test_el_permiso_no_cruza_de_sesion(self) -> None:
        sonidos.manejar({"hook_event_name": "Notification", "session_id": "s1"})
        sonidos.manejar(
            {"hook_event_name": "PostToolUse", "session_id": "s2", "tool_name": "Bash"}
        )
        self.assertEqual(self.reproducidos, ["Solicitud.wav"])

    def test_el_turno_no_cruza_de_sesion(self) -> None:
        sonidos.manejar(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "s1",
                "prompt_id": "t",
                "tool_name": "Edit",
            }
        )
        sonidos.manejar(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "s2",
                "prompt_id": "t",
                "tool_name": "Edit",
            }
        )
        self.assertEqual(self.reproducidos, ["empieza.wav", "empieza.wav"])


class TestRobustez(BaseSonidos):
    def test_evento_desconocido_no_hace_nada(self) -> None:
        self.evento("SessionStart")
        self.evento("PreCompact")
        self.assertEqual(self.reproducidos, [])

    def test_payload_vacio_no_explota(self) -> None:
        sonidos.manejar({})
        self.assertEqual(self.reproducidos, [])

    def test_wav_faltante_no_explota(self) -> None:
        (self.carpeta_wav / "Finalizo.wav").unlink()
        self.evento("Stop")
        self.assertEqual(self.reproducidos, [])

    def test_carpeta_inexistente_no_explota(self) -> None:
        sonidos._carpeta_sonidos = lambda: self.carpeta_wav / "no-existe"
        self.evento("Stop")
        self.assertEqual(self.reproducidos, [])

    def test_estado_corrupto_se_ignora(self) -> None:
        (self.carpeta_estado / "s1.json").write_text("{ esto no es json")
        self.evento("PreToolUse", tool_name="Edit")
        self.assertEqual(self.reproducidos, ["empieza.wav"])

    def test_busqueda_de_wav_sin_distinguir_mayusculas(self) -> None:
        (self.carpeta_wav / "Continua.wav").unlink()
        (self.carpeta_wav / "continua.WAV").write_bytes(b"")
        self.evento("Notification")
        self.evento("PostToolUse", tool_name="Bash")
        self.assertEqual(self.reproducidos, ["Solicitud.wav", "continua.WAV"])


if __name__ == "__main__":
    unittest.main()
