from urllib.parse import urlparse

from app.config import config


def validate_single_lab_deployment() -> list[str]:
    errors: list[str] = []
    if config.APP_ENV != "production":
        errors.append("APP_ENV must be production")
    if not config.is_single_lab:
        errors.append("DEPLOYMENT_MODE must be single_lab")
    if config.effective_lab_structure_mode != "structured":
        errors.append("LAB_STRUCTURE_MODE must be structured")
    if config.API_ROOT_PATH:
        errors.append("API_ROOT_PATH must be empty because the bundled proxy strips /api")
    if config.LOG_REQUEST_BODIES:
        errors.append("LOG_REQUEST_BODIES must remain false in production")

    site_url = urlparse(config.SITE_URL)
    if site_url.scheme not in {"http", "https"} or not site_url.netloc:
        errors.append("SITE_URL must be an absolute HTTP or HTTPS URL")

    if config.STORAGE_BACKEND == "minio" and config.MINIO_PROXY_PATH != "/minio":
        errors.append("MINIO_PROXY_PATH must be /minio for the bundled reverse proxy")
    if config.effective_signup_mode != "invite_only":
        errors.append("SIGNUP_MODE must be invite_only for a single-Lab deployment")
    return errors


def main() -> None:
    errors = validate_single_lab_deployment()
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"Invalid single-Lab deployment configuration:\n{details}")
    print("single_lab deployment configuration is valid")


if __name__ == "__main__":
    main()
