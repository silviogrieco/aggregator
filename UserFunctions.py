import random
import string
import logging
from SupabaseConnection import supabase
from pydantic import BaseModel
import re, unicodedata

class VoteModel(BaseModel):
    id: int
    topic: str
    categoria: str
    concluded: bool = False


EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def get_user(user_id):
    try:
        resp_u = supabase.table("profiles").select("nome, cognome, categoria").eq("id", user_id).single().execute()
        user_data = resp_u.data
        resp_r = supabase.table("user_roles").select("role").eq("user_id", user_id).single().execute()
        result_role = resp_r.data
        if result_role["role"] != "admin":
            return ({"status": "ok"},
                    {
                    "id": str(user_id),
                    "nome": str(user_data["nome"]),
                    "cognome": str(user_data["cognome"]),
                    "categoria": str(user_data["categoria"])
                },)
        else:
            return "L'utente richiesto è un admin"
    except Exception as e:
        return {"status": f"{e}"}, None





def get_all_users():
    try:
        resp_users = supabase.table("profiles").select("id, nome, cognome, categoria").execute()
        resp_roles = supabase.table("user_roles").select("user_id, role").execute()

        result_users = resp_users.data
        result_roles = resp_roles.data

        roles_by_user = {
            r["user_id"]: (r["role"] or "").strip().lower()
            for r in result_roles if "user_id" in r and "role" in r
        }

        admin_ids = {uid for uid, role in roles_by_user.items() if role == "admin"}
        not_admin = []
        for user in result_users:
            uid = user.get("id")
            if admin_ids.__contains__(uid):
                continue
            else:
                not_admin.append({
                    "id": str(uid),
                    "nome": str(user["nome"]),
                    "cognome": str(user["cognome"]),
                    "categoria": str(user["categoria"])
                })


        return {"status": "ok"}, not_admin
    except Exception as e:
        return {"status" : f"{e}"}, None


def delete_user(user_id: str):
    try:
        supabase.auth.admin.delete_user(user_id)
        supabase.table("votes").delete().eq("user_id", user_id).execute()
        supabase.table("profiles").delete().eq("id", user_id).execute()
        return {"status": "ok"}
    except Exception as e:
        logging.info(f"ERRORE DELETE UTENTE {user_id} causa {e}")
        return {"status" : f"{e}"}


def change_categoria(user_id, categoria):
    try:
        supabase.table("profiles").update({"categoria": categoria}).eq("id", user_id).execute()
        return {"status": "ok"}
    except Exception as e:
        return {"status" : f"{e}"}

def rand_name():
    nomi = ["Marco","Sara","Elisa","Paolo","Chiara","Davide","Marta","Giorgio","Francesca","Alessio","Irene","Stefano"]
    cognomi = ["Rossi","Bianchi","Verdi","Neri","Gialli","Blu","Fontana","Greco","Marini","Ferrari","Conti","Scola"]
    return random.choice(nomi), random.choice(cognomi)

def rand_password(n=14):
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))



def make_email(nome: str, cognome: str, simulation_id: int, i: int) -> str:
    local = f"{nome}.{cognome}.{simulation_id}.{i+1}".lower()
    # normalizza accenti: "è" -> "e"
    local = unicodedata.normalize("NFKD", local)
    local = "".join(c for c in local if c.isalnum() or c in {'.','-','_','+'})
    # niente doppi punti o punto ai bordi
    local = re.sub(r"\.{2,}", ".", local).strip(".")
    # tronca local-part a 64 char (limite RFC)
    local = local[:64] or "user"
    email = f"{local}@example.com"
    return email

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))

def create_auth_user(email: str, password: str, simulation_id: int) -> str:
    resp = supabase.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"simulation_id": simulation_id}
    })
    user_obj = getattr(resp, "user", None)
    uid = getattr(user_obj, "id", None)
    if not uid:
        raise RuntimeError("Impossibile ottenere l'ID utente creato")
    return str(uid)

def delete_auth_user(user_id: str):
    supabase.auth.admin.delete_user(user_id)

def extract_ciphertext(enc) -> int:
    c = getattr(enc, "ciphertext", None)
    if callable(c):
        return int(c())
    if c is not None:
        return int(c)
    raise RuntimeError("Impossibile estrarre il ciphertext")

def list_elections():
    try:
        res = supabase.table("votazioni").select("id,topic,categoria,concluded").order("id").execute()
        rows = res.data or []
        return [VoteModel(**r) for r in rows]
    except Exception as e:
        raise RuntimeError(f"Impossibile selezionare le votazioni: {e}")

def insert_election(topic: str, categoria: str):
    try:
        res = supabase.table("votazioni").insert({"topic": topic, "categoria": categoria, "concluded": False} ).execute()
        row_list = getattr(res, "data", None) or []
        if not row_list:
            raise RuntimeError("Nessuna riga restituita dall'INSERT")

        row = row_list[0]
        return row
    except Exception as e:
        raise RuntimeError(f"Impossibile inserire la votazione: {e}")

def update_election(votazione_id: int, yes_total: int, no_total: int, concluded: bool):
    try:
       supabase.table("votazioni").update({"si": yes_total, "no": no_total, "concluded": True}).eq("id", votazione_id).execute()
    except Exception as e:
        raise RuntimeError(f"Impossibile inserire la votazione: {e}")

def get_election(votazione_id: int):
    try:
        resp = supabase.table("votazioni").select().eq("id", votazione_id).execute()
        return resp
    except Exception as e:
        raise RuntimeError(f"Impossibile trovare la votazione: {e}")

def delete_election(votazione_id: int):
    try:
        supabase.table("votes").delete().eq("votazione_id", votazione_id).execute()
        supabase.table("votazioni").delete().eq("id", votazione_id).execute()
    except Exception as e:
        raise RuntimeError(f"Impossibile cancellare la votazione: {e}")

def create_categoria(nome: str):
    try:
        supabase.table("categoria").insert({"nome": nome}).execute()
    except Exception as e:
        raise RuntimeError(f"Impossibile inserire la categoria: {e}")

def get_categorie():
    try:
        resp = supabase.table("categoria").select("nome").execute()
        rows = resp.data or []
        return [str(r.get("nome")) for r in rows]
    except Exception as e:
        raise RuntimeError(f"Impossibile selezionare le categorie: {e}")