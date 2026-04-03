from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class TimeSync:
    drift_ms: int = 0

    def sync(self, server_epoch_ms: int, local_epoch_ms: int | None = None) -> int:
        # Sincroniza reloj local contra servidor para evitar señales fuera de ventana por desfase de tiempo.
        local = local_epoch_ms if local_epoch_ms is not None else int(time.time() * 1000)
        self.drift_ms = server_epoch_ms - local
        return self.drift_ms

    def now_ms(self) -> int:
        # Tiempo "corregido" usado por el resto del bot.
        return int(time.time() * 1000) + self.drift_ms

    def seconds_to(self, end_epoch_ms: int) -> int:
        # Nunca devuelve negativos para simplificar validaciones aguas abajo.
        return max(0, (end_epoch_ms - self.now_ms()) // 1000)
