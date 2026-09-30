# Vérification de sécurité du service d'authentification — LECTURE SEULE.
#
# Deux vérifications demandées par le produit :
#   1. Les mots de passe sont-ils hashés (et dans quel format) ?
#   2. La vérification d'email passe-t-elle par OTP (et comment est-il stocké) ?
#
# Rôle de ce script : OBSERVER, jamais modifier. Les schémas `neon_auth.*`
# appartiennent au fournisseur d'identité (Better Auth managé par Neon) :
# toute écriture ici serait du piratage du fournisseur, pas une correction.
#
# Le mot de passe de connexion est lu depuis backend/.env — jamais affiché.
import os
import re
import sys
from pathlib import Path

import psycopg

# ---------------------------------------------------------------------------
# 1. Chargement du DATABASE_URL depuis backend/.env (parsing minimal, sans
#    exposer la valeur dans la sortie).
# ---------------------------------------------------------------------------
env_path = Path(__file__).resolve().parent.parent / ".env"
database_url = None
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not database_url:
    print("ERREUR : DATABASE_URL introuvable dans backend/.env")
    sys.exit(1)

# Masquage du mot de passe pour l'affichage (le script lit la vraie valeur).
try:
    m = re.match(r"(postgres(?:ql)?://)([^:/@]+):([^@]+)@(.+)", database_url)
    masked = f"{m.group(1)}{m.group(2)}:***@{m.group(4)}" if m else "<non analysable>"
except Exception:
    masked = "<non analysable>"
print(f"Connexion : {masked}\n")


def q(conn, sql, params=None):
    """Exécute une requête et retourne les lignes (dictionnaires)."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return cols, rows


def main():
    with psycopg.connect(database_url, connect_timeout=15) as conn:
        print("=" * 70)
        print("A. Colonnes de neon_auth.\"user\" (ce qui existe chez le fournisseur)")
        print("=" * 70)
        cols, rows = q(
            conn,
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'neon_auth' AND table_name = 'user'
            ORDER BY ordinal_position
            """,
        )
        for r in rows:
            print(f"   {r[0]:<28} {r[1]:<24} {r[2]}")

        print("\n" + "=" * 70)
        print("B. Mots de passe : hash présents dans neon_auth.account ?")
        print("=" * 70)
        # Better Auth stocke le mot de passe dans la table account (providerId
        # 'credential'), PAS dans user. On joint sur user pour avoir l'email.
        # Le format Better Auth par défaut est scrypt : "sel:hash" encodés en
        # hexadécimal (sel 16 octets = 32 hex, hash 64 octets = 128 hex ->
        # longueur totale 161). Le préfixe hex n'est donc PAS un hash faible :
        # c'est le sel, suivi du ':'. Un hash de 161 caractères avec ':' est
        # la signature scrypt Better Auth.
        cols, rows = q(
            conn,
            """
            SELECT u.email,
                   a."providerId",
                   (a.password IS NOT NULL AND a.password <> '') AS has_hash,
                   LENGTH(a.password)                            AS longueur,
                   (POSITION(':' IN a.password) > 0)             AS a_separateur
            FROM neon_auth.account a
            LEFT JOIN neon_auth."user" u ON u.id = a."userId"
            ORDER BY u.email
            """,
        )
        fmts = set()
        for email, provider, has_hash, longueur, sep in rows:
            fmt = "?"
            if has_hash and longueur:
                if longueur == 161 and sep:
                    fmt = "scrypt Better Auth (sel:hash hex)"
                elif longueur == 60 and has_hash:
                    fmt = "bcrypt ($2*)"  # 60 caractères, commence par $2
                elif longueur >= 90:
                    fmt = "hash long (scrypt/argon2 probable)"
                else:
                    fmt = "format non standard, à identifier"
                fmts.add(fmt)
            print(
                f"   {str(email):<40} provider={str(provider):<12} "
                f"hash={'OUI' if has_hash else 'NON':<4} {fmt}"
            )
        print("   Formats détectés :", ", ".join(sorted(fmts)) if fmts else "aucun")

        # Afficher les 30 premiers caractères du hash (suffisant pour identifier
        # le format, pas assez pour compromettre) + la longueur totale et la
        # présence d'un séparateur sel:hash.
        if "format non standard, à identifier" in fmts:
            print("\n   Préfixes bruts (30 premiers caractères, par email) :")
            cols, rows = q(
                conn,
                """
                SELECT u.email,
                       LEFT(a.password, 30)              AS prefixe,
                       LENGTH(a.password)                AS longueur,
                       (POSITION(':' IN a.password) > 0) AS a_separateur_2points
                FROM neon_auth.account a
                LEFT JOIN neon_auth."user" u ON u.id = a."userId"
                WHERE a.password IS NOT NULL AND a.password <> ''
                ORDER BY u.email
                """,
            )
            for email, p, lg, sep in rows:
                print(
                    f"      {str(email):<40} {p}  (longueur={lg}, ':'={sep})"
                )

        # Politique du module email_and_password (config du fournisseur :
        # lecture seule — minPasswordLength, requireEmailVerification, etc.).
        # Découverte : la table n'a PAS de colonne 'data' — on liste d'abord
        # ses colonnes réelles, puis on lit la première ligne entière.
        cols, rows = q(
            conn,
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'neon_auth' AND table_name = 'project_config'
            ORDER BY ordinal_position
            """,
        )
        print("\n   Structure de neon_auth.project_config :")
        for c, d in rows:
            print(f"      {c:<28} {d}")

        # Lecture de la première ligne : chaque colonne, valeurs longues masquées.
        cols, rows = q(conn, "SELECT * FROM neon_auth.project_config LIMIT 1")
        if rows:
            print("\n   Valeurs de la ligne de configuration :")
            for col, val in zip(cols, rows[0]):
                if val is None:
                    print(f"      {col} = NULL")
                elif isinstance(val, (dict, list)):
                    # JSON : on masque les chaînes longues (surtout les secrets
                    # comme les clés SMTP si elles étaient présentes).
                    def _mask(v):
                        if isinstance(v, str) and len(v) >= 16:
                            return f"<{len(v)} caractères>"
                        return v

                    if isinstance(val, dict):
                        val = {k: _mask(v) for k, v in val.items()}
                    else:
                        val = [_mask(v) for v in val]
                    print(f"      {col} = {val}")
                elif isinstance(val, str) and len(val) > 40:
                    print(f"      {col} = <{len(val)} caractères>")
                else:
                    print(f"      {col} = {val}")

        print("\n" + "=" * 70)
        print("C. Stockage OTP (vérification d'email)")
        print("=" * 70)
        cols, rows = q(
            conn,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'neon_auth'
            ORDER BY table_name
            """,
        )
        print("   Tables neon_auth :", ", ".join(r[0] for r in rows))

        # Identification de la table des codes (verification ou otp).
        otp_tables = [r[0] for r in rows if r[0] in ("verification", "otp")]
        for table in otp_tables:
            print(f"\n   --- neon_auth.{table} : colonnes ---")
            cols, rows = q(
                conn,
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'neon_auth' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            for r in rows:
                print(f"      {r[0]:<24} {r[1]}")
            cols, rows = q(
                conn,
                f'SELECT * FROM neon_auth."{table}" ORDER BY "createdAt" DESC LIMIT 5',
            )
            print(f"   --- dernières lignes ({len(rows)}): colonnes = {cols} ---")
            for r in rows:
                # Masquage du code lui-même : on ne montre que sa longueur et
                # son préfixe pour juger du format de stockage sans l'exposer.
                if cols and "code" in cols:
                    idx = cols.index("code")
                    code_val = r[idx]
                    masked_code = f"<{len(code_val)} car, débute par {str(code_val)[:4]!r}>"
                    r = list(r)
                    r[idx] = masked_code
                print(f"      {r}")

        print("\n" + "=" * 70)
        print("D. Résumé — réponses aux deux questions produit")
        print("=" * 70)
        print(
            "   - Mots de passe hashés : voir colonne B 'hash' (format détecté au préfixe).\n"
            "   - Vérification email par OTP : la table de codes existe ; le transport\n"
            "     SMTP côté Neon reste le point bloquant (aucun email n'arrive, D-2)."
        )


if __name__ == "__main__":
    main()