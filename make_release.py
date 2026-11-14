"""Package app contents for the updater installed with v18.1."""
from pathlib import Path
import hashlib
import zipfile

root = Path(__file__).resolve().parent
app = root / "SiaAebi_Install" / "app"
if not (app / "SiaAebiBlogWriter.exe").is_file():
    raise FileNotFoundError("Build SiaAebiBlogWriter.exe first")

out = root / "GitHub_Release_Assets"
out.mkdir(exist_ok=True)
archive = out / "siaaebi-update.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for file in app.rglob("*"):
        if file.is_file():
            z.write(file, file.relative_to(app).as_posix())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(out / "siaaebi-update.zip.sha256").write_text(
    f"{digest}  siaaebi-update.zip\n", encoding="utf-8"
)
print("Validated release assets:", archive, digest)
