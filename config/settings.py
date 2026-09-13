from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = "management-commands-only-no-web-server"
INSTALLED_APPS = ["exporter"]
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
