import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.config import config
from app.interfaces import GeneratedContent, StorageInterface

logger = logging.getLogger(__name__)

# Category -> Drive subfolder name, matches the structure already created
# under the shared AutoSocial AI Drive folder.
CATEGORY_TO_FOLDER = {
    "image": "Generated_Memes",
    "caption": "Captions",
    "hashtags": "Hashtags",
    "log": "Logs",
}


class LocalFirstDriveStorage(StorageInterface):
    """Validates locally first — the app's ability to generate and preview
    content NEVER depends on Drive being reachable. Upload is a best-effort
    step after validation; if it fails, content stays valid locally and the
    caller can retry the upload later without regenerating anything."""

    def validate(self, content: GeneratedContent) -> bool:
        if not os.path.exists(content.image_path):
            logger.error("Validation failed: image missing at %s", content.image_path)
            return False
        if os.path.getsize(content.image_path) == 0:
            logger.error("Validation failed: image is 0 bytes")
            return False
        if not content.caption.strip():
            logger.error("Validation failed: caption is empty")
            return False
        if not content.hashtags:
            logger.error("Validation failed: no hashtags generated")
            return False
        return True

    def upload(self, content: GeneratedContent) -> GeneratedContent:
        """In mock mode, 'upload' just writes to a local mock_uploads.json log so
        the whole pipeline is testable offline. In live mode, this is where the
        Google Drive API (service account) call goes — see the TODO below.
        """
        if config.mock_mode:
            return self._mock_upload(content)
        return self._live_upload(content)

    def _mock_upload(self, content: GeneratedContent) -> GeneratedContent:
        log_path = config.local_logs_dir / "mock_uploads.json"
        entry = {
            "topic": content.topic.text,
            "category": content.topic.category,
            "image_path": content.image_path,
            "caption": content.caption,
            "hashtags": content.hashtags,
            "generated_at": content.generated_at,
            "would_upload_to_drive_folder": config.drive_folder_id or "(not set)",
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = []
        if log_path.exists():
            existing = json.loads(log_path.read_text(encoding="utf-8"))
        existing.append(entry)
        log_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        content.drive_file_ids = {"mock": True, "logged_to": str(log_path)}
        logger.info("[MOCK] Would upload %s to Drive folder %s", content.image_path, config.drive_folder_id)
        return content

    # ------------------------------------------------------------------
    # LIVE MODE: Google Drive API (service account) — per CTO requirement.
    # ------------------------------------------------------------------

    _DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

    def _live_upload(self, content: GeneratedContent) -> GeneratedContent:
        """Upload validated local content to Google Drive using a service
        account (google-api-python-client).

        Uploads:
          - content.image_path            -> Generated_Memes/
          - content.caption as a .txt     -> Captions/
          - content.hashtags as a .txt    -> Hashtags/

        Failures raise (so the scheduler can log + retry) but NEVER delete or
        invalidate the local files — local-first means local is never at the
        mercy of Drive being up.
        """
        service = self._build_drive_service()

        # 1) Ensure category subfolders exist under the root Drive folder.
        folder_ids = self._ensure_folders(service)

        # 2) Upload each artifact into its folder; any failure raises and
        #    stops the rest so nothing ends up half-uploaded.
        image_path = Path(content.image_path)
        uploads: dict = {
            "image": self._upload_file(service, image_path, folder_ids["image"]),
            "caption": self._upload_text(
                service,
                f"{image_path.stem}_caption.txt",
                content.caption + "\n\n" + " ".join(content.hashtags),
                folder_ids["caption"],
            ),
            "hashtags": self._upload_text(
                service,
                f"{image_path.stem}_hashtags.txt",
                "\n".join(content.hashtags),
                folder_ids["hashtags"],
            ),
        }

        # 3) Store IDs + public URL so the publisher can use the share link
        #    as the Graph API image_url parameter.
        content.drive_file_ids = uploads
        logger.info(
            "[LIVE] Uploaded %s to Drive: %s",
            image_path.name,
            {k: v.get("id") for k, v in uploads.items()},
        )
        return content

    def _build_drive_service(self):
        """Build an authorized Drive v3 service from the service account JSON."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "google-api-python-client not installed — run: "
                "pip install google-api-python-client google-auth"
            ) from exc

        sa_path = config.drive_service_account_path
        if not sa_path or not os.path.exists(sa_path):
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_PATH is not set or the file does "
                f"not exist: {sa_path!r}. Create a service account in the "
                "Google Cloud console, download its JSON key, and point the "
                "env var at it."
            )
        if not os.path.isfile(sa_path):
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_PATH does not point at a file: "
                f"{sa_path!r} is a directory. A broken bind mount can leave a "
                "dangling directory at this path — remove it and ensure the "
                "env var points at the actual JSON key file."
            )
        creds = service_account.Credentials.from_service_account_file(
            sa_path, scopes=self._DRIVE_SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _ensure_folders(self, service) -> dict:
        """Create (or find) the category subfolders under the root folder.
        Idempotent — re-runs are safe. Returns {category: folder_id}."""
        root_id = config.drive_folder_id
        if not root_id:
            raise RuntimeError(
                "GOOGLE_DRIVE_FOLDER_ID is not set — the service account has "
                "nowhere to upload. Set it in .env first."
            )

        ids = {}
        for category, folder_name in CATEGORY_TO_FOLDER.items():
            query = (
                f"name = '{folder_name}' and '{root_id}' in parents and "
                "trashed = false and mimeType = 'application/vnd.google-apps.folder'"
            )
            existing = (
                service.files()
                .list(q=query, fields="files(id)", supportsAllDrives=True)
                .execute()
            )
            files = existing.get("files", [])
            if files:
                ids[category] = files[0]["id"]
                continue

            created = (
                service.files()
                .create(
                    body={
                        "name": folder_name,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [root_id],
                    },
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
            ids[category] = created["id"]
            logger.info("[LIVE] Created Drive folder '%s': %s", folder_name, created["id"])

        return ids

    def _upload_file(self, service, local_path: Path, folder_id: str) -> dict:
        """Upload a binary file (image) and return {id, public_url}."""
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(local_path), resumable=True)
        uploaded = (
            service.files()
            .create(
                body={"name": local_path.name, "parents": [folder_id]},
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        # Anyone-with-link reader so the Graph API can fetch the image via URL.
        service.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
        return {
            "id": uploaded["id"],
            "public_url": f"https://drive.google.com/uc?id={uploaded['id']}",
        }

    def _upload_text(self, service, filename: str, text: str, folder_id: str) -> dict:
        """Upload a text snippet as a plain .txt file."""
        import io

        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(text.encode("utf-8")), mimetype="text/plain")
        uploaded = (
            service.files()
            .create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        return {"id": uploaded["id"]}
