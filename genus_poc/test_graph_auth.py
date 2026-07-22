import msal
from src import config

app = msal.ConfidentialClientApplication(
    config.AZURE_CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}",
    client_credential=config.AZURE_CLIENT_SECRET,
)
result = app.acquire_token_for_client(scopes=config.GRAPH_SCOPE)
if "access_token" in result:
    print("SUCCESS. Token starts with:", result["access_token"][:30])
else:
    print("FAILED:", result.get("error"), "-", result.get("error_description"))
