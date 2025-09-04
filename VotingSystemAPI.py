import httpx
from fastapi import APIRouter, HTTPException

from phe import paillier
from UserFunctions import *
import logging

from FileAccumulator import FileAccumulator
from SimulationStore import SimulationStore


logging.basicConfig(filename='python_logs.log', level=logging.INFO, format='%(asctime)s - %(message)s')

class PublicKeyResponse(BaseModel):
    n: str
    g: str
    pk_fingerprint: str

class SubmitVoteBody(BaseModel):
    votazione_id: int
    ciphertext: str
    topic: str
    num_utenti: int

class ResultModel(BaseModel):
    votazione_id: int
    num_utenti: int

class User(BaseModel):
    id: str
    nome: str
    cognome: str
    categoria: str
    is_admin: bool = False

class UserCategoryUpdate(BaseModel):
    user_id: str
    categoria: str

class VoteModel(BaseModel):
    id: int
    topic: str
    categoria: str
    concluded: bool = False

class SimulationStart(BaseModel):
    count: int
    categoria: str
    topic: str

class SimulationResponse(BaseModel):
    simulation_id: int
    categoria: str
    votazione_id: int
    generated_users: list[User]
    result: dict[str, int]  # {"Totale SI":..., "Totale NO":..., "Totale voti":...}

class SimulationEndModel(BaseModel):
    simulation_id: int

class SuccessResponse(BaseModel):
    status: str

class DecryptTallyResponse(BaseModel):
    plain_sum: int

class DecryptTallyModel(BaseModel):
    votazione_id: int
    ciphertext_sum: int

class DeleteUserModel(BaseModel):
    user_id: str

class NewCategoriaModel(BaseModel):
    nome: str

class NewElectionModel(BaseModel):
    topic: str
    categoria: str

class DeleteElectionModel(BaseModel):
    votazione_id: int

AUTH_BASE = "https://authority-k9w7.onrender.com/api/authority/"
VOTE_BASE = "https://aggregator-ynd5.onrender.com/api/aggregator/"

class VotingSystemAPI:


    def __init__(self):
        self.router = APIRouter(prefix="/api/aggregator")
        self.acc = FileAccumulator("data/votazioni/votazioni.json")
        self.sim_store = SimulationStore("data/simulations/simulations.json")

        # endpoints per-elezione
        self.router.post("/elections/vote")(self.submit_vote)
        self.router.post("/elections/result")(self.get_result)

        self.router.get("/elections/users")(self.list_non_admin_users)
        self.router.post("/elections/users/category")(self.update_user_category)
        self.router.post("/elections/users/delete_user")(self.delete_user)

        self.router.post("/categoria")(self.new_categoria)
        self.router.get("/categoria/list")(self.list_categorie)
        self.router.post("/elections/insert")(self.new_election)
        self.router.post("/elections/delete")(self.delete_election)

        self.router.get("/elections/votazioni")(self.list_all_votes)

        self.router.post("/simulation")(self.start_simulation)
        self.router.post("/simulation/end")(self.end_simulation)


    # ---------------------------------------------------------------------
    # KEY MANAGEMENT (per elezione)
    # ---------------------------------------------------------------------


    # ---------------------------------------------------------------------
    # VOTING
    # ---------------------------------------------------------------------

    async def get_pk(self, votazione_id):

        """
        Crea/Restituisce la chiave pubblica per la specifica votazione mediante richiesta al server Authority
        :param votazione_id:
        :return public_key:
        """
        try:
            async with httpx.AsyncClient(base_url=AUTH_BASE, timeout=30.0) as client:

                resp = await client.post(f"elections", json={"votazione_id": f"{votazione_id}"})
                return PublicKeyResponse(**resp.json())

        except Exception as e:
            logging.info("KeyError: Elezione non trovata/inizializzata")
            raise HTTPException(status_code=404, detail="Elezione non trovata o non inizializzata: " + str(e))

    async def get_decrypt_tally(self, votazione_id, ciphertext):
        """
        Restituisce la somma dei voti decriptata mediante richiesta al server Authority
        :param votazione_id:
        :param ciphertext:
        :return decrypt_tally:
        """
        try:
            async with httpx.AsyncClient(base_url=AUTH_BASE, timeout=30.0) as client:
                payload = DecryptTallyModel(
                    votazione_id=votazione_id,
                    ciphertext_sum=ciphertext
                )
                resp = await client.post(f"elections/decrypt_tally", json=payload.model_dump())
                resp_body = resp.json()
                return DecryptTallyResponse(**resp_body)

        except Exception as e:
            logging.info("DecryptError: Decifratura non riuscita")
            raise HTTPException(status_code=404, detail="Decifratura non riuscita: " + str(e))

    async def new_categoria(self, payload: NewCategoriaModel):
        """
        Crea una nuova categoria
        :param payload:
        :return void:
        """
        nome = payload.nome
        try:
            create_categoria(nome)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Categoria non creata: "+ str(e))

    async def submit_vote(self, body: SubmitVoteBody):
        """
        Riceve un ciphertext come stringa.
        Aggrega omomorficamente sommando i ciphertext.
        :param body:
        :return status:
        """
        try:
            votazione_id = str(body.votazione_id)
            c_int = int(body.ciphertext)
        except Exception as e:
            logging.info("Exception: Payload non valido" + str(e))
            raise HTTPException(status_code=400, detail=f"Payload non valido: {e}")

        #carico la chiave pubblica per la votazione con id votazione_id

        pk_model = await self.get_pk(votazione_id)
        pk = paillier.PaillierPublicKey(n=int(pk_model.n))

        # ricostruisco l'EncryptedNumber
        enc_vote = paillier.EncryptedNumber(pk, c_int, 0)

        # aggregazione: somma dei ciphertext
        current = self.acc.get(votazione_id)
        if current is None:
            # primo voto: salva direttamente
            self.acc.set(votazione_id, enc_vote.ciphertext(), enc_vote.exponent, 1)
            current = self.acc.get(votazione_id)
        else:
            #successivamente: prende dal file la somma omomorfica attuale e la aggiorna
            acc_c, acc_exp, acc_count = current
            acc = paillier.EncryptedNumber(pk, acc_c, acc_exp)
            updated = acc + enc_vote
            self.acc.set(votazione_id, updated.ciphertext(), updated.exponent, acc_count + 1)

        acc_c, acc_exp, acc_count = current
        logging.info("num_utenti: " + str(body.num_utenti) + " acc_count: " + str(acc_count))

        return {"status": "ok"}

    # ---------------------------------------------------------------------
    # TALLY
    # ---------------------------------------------------------------------
    async def get_result(self, body: ResultModel):
        """
        Carica sul database la somma in chiaro dei voti mediante richiesta al server Authority
        :param body:
        :return status:
        """

        try:
            votazione_id = str(body.votazione_id)
            num_utenti_int = int(body.num_utenti)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payload non valido: {e}")


        resp = get_election(int(votazione_id))
        row = resp.data
        if row is None:
            raise HTTPException(status_code=404, detail="Votazione non trovata")
        conclusa = bool(row[0].get("concluded"))
        si = str(row[0].get("si"))
        no = str(row[0].get("no"))

        if conclusa:
            return {
                "status": "ok",
                    "si": si,
                    "no": no
                }


        current = self.acc.get(votazione_id)
        if current is None:
            raise HTTPException(404, "Nessun voto per questa elezione")

        acc_c, acc_exp, acc_count = current


        if num_utenti_int <= acc_count:
            acc_c, acc_exp, count = current

            #richiesta di decifratura al server Authority
            tally_model = await self.get_decrypt_tally(votazione_id, acc_c)

            yes_total = tally_model.plain_sum
            no_total = count - yes_total

            try:
                update_election(int(votazione_id), yes_total, no_total, True)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Update non riuscito: {e}")

            #elimino i dati dell'accumulatore relativi alla votazione conclusa
            self.acc.clear(votazione_id)
            return {
                "status": "ok",
                    "si": str(yes_total),
                    "no": str(no_total)
                }

        else:
            return{"status": "Votazione non conclusa"}



    # mappa simulation_id -> {categoria, votazione_id, user_ids}

    # ================== ENDPOINTS UTENTI (DB via UserFunctions) ==================


    async def list_non_admin_users(self):
        """
        Restituisce la lista di utenti non admin
        :return user_model:
        """
        status, users = get_all_users()
        if not status or status.get("status") != "ok":
            msg = status.get("message", "Errore nel recupero utenti") if isinstance(status, dict) else "Errore nel recupero utenti"
            raise HTTPException(status_code=500, detail=msg)


        user_model = []
        for user in users:
            user_model.append(User(
                    id=str(user.get("id")),
                    nome=str(user.get("nome")) or "",
                    cognome=str(user.get("cognome")) or "",
                    categoria=str(user.get("categoria")) or "",
                    is_admin=False
                ))

        return user_model


    async def update_user_category(self, body: UserCategoryUpdate):
        """
        Aggiorna la categoria di uno specifico utente
        :param body:
        :return status:
        """
        try:
            user_id = body.user_id
            categoria = body.categoria
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payload non valido: {e}")

        res = change_categoria(user_id, categoria)
        if not res or res.get("status") != "ok":
            msg = res.get("message", "Impossibile aggiornare la categoria") if isinstance(res, dict) else "Impossibile aggiornare la categoria"
            raise HTTPException(status_code=400, detail=msg)
        return SuccessResponse(status="ok")



    async def delete_user(self, body: DeleteUserModel):

        """
        Elimina un utente dal database
        :param body:
        :return status:
        """
        try:
            user_id = body.user_id
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payload non valido: {e}")

        res = delete_user(user_id)
        status = res.get("status")
        if not res or status != "ok":
            msg = f"Impossibile eliminare l'utente {user_id} causa {status}"
            raise HTTPException(status_code=400, detail=msg)

        return SuccessResponse(status="ok")

    # ================== VOTAZIONI (DB) ==================

    async def list_all_votes(self):
        """
        Restituisce la lista di tutte le votazioni effettuate
        :return [VoteModel]:
        """
        try:
             return list_elections()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))



    # ================== SIMULAZIONE (usa i NUOVI endpoint per-elezione) ==================
    async def start_simulation(self, body: SimulationStart):
        """
        Crea una simulazione di 10+ votazioni efffettuate da utenti fittizzi creati a run-time

        Flusso:
          1) Crea la votazione (tabella 'votazioni') -> prendi id come votazione_id.
          2) Crea 'count' utenti fittizi con la stessa categoria condivisa.
          3) Richiesta al server Authority per la chiave pubblica.
          4) Per ogni utente: genera voto 0/1, cifra e POST /api/elections/vote {election_id, ciphertext, topic, num_utenti}.
          5) POST /api/elections/result {voatzione_id, num_utenti} -> decritta e scrive si/no/concluded in DB.
          6) Leggi i risultati da 'votazioni' e ritorna tutto.
        :param body:
        :return SimulationResponse{}:
        """

        simulation_id = self.sim_store.next_id()
        try:
            count = body.count
            topic = body.topic or f"Simulazione {simulation_id}"
            categoria = body.categoria
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payload non valido: {e}")

        if count < 10 or count > 30:
            raise HTTPException(status_code=400, detail="count deve essere tra 10 e 30")

        try:
            # 1) crea votazione per categoria
            v_res = insert_election(topic, categoria)
            logging.info(v_res)
            votazione_id = int(v_res.get("id"))

            if not v_res or votazione_id is None:
                raise RuntimeError("Creazione votazione fallita")

            payload = {
                "votazione_id": votazione_id,
                "categoria": categoria,
                "topic": topic,
                "user_ids": None
            }
            self.sim_store.set(simulation_id, payload)

            # 2) crea utenti fittizi
            generated_users: list[User] = []
            user_ids: list[str] = []
            for i in range(body.count):
                nome, cognome = rand_name()
                email = make_email(nome, cognome, simulation_id, i)
                password = rand_password()
                if not is_valid_email(email):
                    email = make_email(nome.replace(" ", ""), cognome.replace(" ", ""), simulation_id, i)

                uid = create_auth_user(email, password, simulation_id)
                logging.info(f"uid generato: {uid}")

                supabase.table("profiles").update({
                    "nome": nome, "cognome": cognome, "categoria": categoria
                }).eq("id", uid).execute()

                new_user = User(
                    id=uid, nome=nome, cognome=cognome, categoria=categoria
                )
                generated_users.append(new_user)
                user_ids.append(uid)
                logging.info(f"Utente fittizio {new_user} creato con successo")

                payload["user_ids"] = user_ids
                self.sim_store.set(simulation_id, payload)

            #3)richiesta della chiave pubblica
            async with httpx.AsyncClient(base_url=AUTH_BASE, timeout=30.0) as auth:

                r_create = await auth.post(f"elections", json={"votazione_id": f"{votazione_id}"})
                if r_create.status_code not in (200, 201):
                    raise RuntimeError(f"Errore create_election: {r_create.text}")

                pk_body = PublicKeyResponse(**r_create.json())
                pub_key = paillier.PaillierPublicKey(n=int(pk_body.n))


            #4)Voto casuale 0/1 per ogni utente generato
            async with httpx.AsyncClient(base_url=VOTE_BASE, timeout=30.0) as vote_cli:
                total = body.count
                for _uid in user_ids:
                    vote = random.choice([0, 1])
                    enc = pub_key.encrypt(vote)
                    ciphertext_int = extract_ciphertext(enc)

                    r_sub = await vote_cli.post(
                        f"elections/vote",
                        json={"votazione_id": str(votazione_id),  "ciphertext": str(ciphertext_int), "topic": topic, "num_utenti": total},
                    )
                    if r_sub.status_code != 200:
                        raise RuntimeError(f"Errore submit_vote: {r_sub.text}")

                #5)Ritorna i risultati con richiesta all'endpoint /result
                r_res = await vote_cli.post(
                    f"elections/result",
                    json={"votazione_id": votazione_id, "num_utenti": total},
                )
                if r_res.status_code != 200:
                    raise RuntimeError(f"Errore get_result: {r_res.text}")


            row = (
                supabase.table("votazioni")
                .select("si,no,concluded")
                .eq("id", votazione_id)
                .single()
                .execute()
            ).data or {}

            #6)Caricati i risultati salvati nel db dall'endpoint /result
            result = {
                "Totale SI": int(row.get("si", 0)),
                "Totale NO": int(row.get("no", 0)),
                "Totale voti": int(row.get("si", 0)) + int(row.get("no", 0)),
            }

            # traccia per cleanup

            return SimulationResponse(
                simulation_id=simulation_id,
                categoria=categoria,
                votazione_id=votazione_id,
                generated_users=generated_users,
                result=result,
            )
        #rollback in caso di errore
        except Exception as e:
            logging.info("Entered failure DELETE section cause: %s", e)
            # rollback best-effort (utenti e votazione)
            sim = self.sim_store.get(simulation_id)
            if not sim:
                raise HTTPException(status_code=404, detail="Simulazione non trovata")

            try:
                uids = sim.get("user_ids", [])
                if uids:
                    delete_election(sim.get("votazione_id"))
                    for uid in uids:
                        try:
                            delete_auth_user(uid)
                        except Exception:
                            pass
            finally:
                self.sim_store.pop(simulation_id)
            raise HTTPException(status_code=500, detail=f"Simulazione fallita: {e}")


    async def end_simulation(self, payload: SimulationEndModel):
        """
        Chiude la simulazione eliminando gli UTENTI di test e la votazione effettuata
        L’aggregatore viene pulito quando /result marca la votazione come conclusa
        :param payload:
        :return void:
        """
        simulation_id = payload.simulation_id
        sim = self.sim_store.get(simulation_id)
        if not sim:
            raise HTTPException(status_code=404, detail="Simulazione non trovata")

        user_ids = sim["user_ids"]

        try:
            delete_election(sim.get("votazione_id"))
            if user_ids:
                for uid in user_ids:
                        delete_auth_user(uid)

            self.sim_store.pop(simulation_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Errore durante la chiusura della simulazione: {e}")

    async def new_election(self, payload: NewElectionModel):
        """
        Crea una nuova votazione
        :param payload:
        :return votazione_id:
        """
        try:
            return insert_election(payload.topic, payload.categoria)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Errore inserimento votazione: {e}")

    async def delete_election(self, payload: DeleteElectionModel):
        """
        Elimina una specifica votazione
        :param payload:
        :return voidd:
        """
        try:
            delete_election(payload.votazione_id)
        except Exception as e:
            logging.info(f"Errore eliminazione: {e}")
            raise HTTPException(status_code=500, detail=f"Impossibile eliminare la categoria: {e}")

    async def list_categorie(self):
        """
        Resituisce la lista aggiornata delle categorie
        :return [str]:
        """
        try:
           return get_categorie()
        except Exception as e:
            logging.info(f"Errore selezione categorie: {e}")
            raise HTTPException(status_code=500, detail=f"Errore selezione categorie: {e}")

