"""Script una tantum: completa il consenso OAuth di Google e salva token.json.

Eseguire manualmente una sola volta (o di nuovo se token.json viene eliminato):

    python setup_google_auth.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow

from calendar_service import SCOPES
from config import GOOGLE_CLIENT_SECRETS_PATH, GOOGLE_TOKEN_PATH


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CLIENT_SECRETS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(GOOGLE_TOKEN_PATH, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())
    print(f"Autenticazione completata. Token salvato in {GOOGLE_TOKEN_PATH}")


if __name__ == "__main__":
    main()
