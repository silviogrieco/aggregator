# --- FILE ACCUMULATOR ----------------------------------------------------
import json, os, tempfile
from pathlib import Path
from phe import paillier

class FileAccumulator:
    """
    Mantiene, per ogni election_id:
      - c  : ciphertext (int) della somma omomorfica parziale
      - exp: esponente (phe) del ciphertext
      - count: numero voti ricevuti
    Struttura file JSON:
    { "elections": { "<id>": { "c": "123...", "exp": 0, "count": 7 } } }
    """
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._atomic_write({"elections": {}})

    def _read(self) -> dict:
        # Se il file è vuoto o non valido, re-inizializza in modo sicuro
        try:
            if not self.path.exists() or self.path.stat().st_size == 0:
                self._atomic_write({"elections": {}})
                return {"elections": {}}
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # JSON corrotto / scrittura interrotta -> reset
            self._atomic_write({"elections": {}})
            return {"elections": {}}


    def _atomic_write(self, data: dict):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"), indent=None)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)


    def get(self, election_id: str) -> tuple[int, int, int] | None:
        """
        Ritorna (c, exp, count) oppure None se non c'è ancora accumulato.
        """
        data = self._read()
        rec = data.get("elections", {}).get(election_id)
        if not rec: return None
        return int(rec["c"]), int(rec.get("exp", 0)), int(rec.get("count", 0))

    def set(self, election_id: str, c: int, exp: int, count: int):
        data = self._read()
        data.setdefault("elections", {})[election_id] = {"c": str(c), "exp": int(exp), "count": int(count)}
        self._atomic_write(data)
        return

    def clear(self, election_id: str):
        data = self._read()
        if election_id in data.get("elections", {}):
            del data["elections"][election_id]
            self._atomic_write(data)
