import json, os, threading

class SimulationStore:
    """
    Piccolo KV store file-based con locking.
    Salva un dict {simulation_id(str): {categoria, votazione_id, user_ids}} in self.path.
    """
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _read(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if not isinstance(data, dict):
                    return {}
                return data
            except FileNotFoundError:
                return {}
            except Exception:
                return {}

    def _write(self, data):

        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def set(self, sim_id: int, payload: dict) -> None:
        key = str(sim_id)
        data = self._read()
        data[key] = payload
        self._write(data)

    def get(self, sim_id: int):
        key = str(sim_id)
        data = self._read()
        return data.get(key)

    def pop(self, sim_id: int):
        key = str(sim_id)
        data = self._read()
        val = data.pop(key, None)
        self._write(data)
        return val

    def next_id(self) -> int:
        data = self._read()
        meta = data.get("_meta", {})
        next_id = meta.get("next_id")
        if not isinstance(next_id, int):
            # fallback: calcola dal massimo tra le chiavi numeriche
            numeric_keys = [int(k) for k in data.keys() if k.isdigit()]
            next_id = (max(numeric_keys) if numeric_keys else 0) + 1
        sim_id = next_id
        meta["next_id"] = sim_id + 1
        data["_meta"] = meta
        self._write(data)
        return sim_id