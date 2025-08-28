# test_e2e_fastapi.py

from FileAccumulator import FileAccumulator
# importa la tua VotingSystemAPI *refactorizzata* che espone le route per-elezione

f = FileAccumulator("data/votazioni/votazioni.json")


f.clear("4")
f.clear("5")
f.clear("6")
f.clear("7")
f.clear("e2e1")

