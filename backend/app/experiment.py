import hashlib, os

def assign_experiment(anonymous_user_id: str, salt: str | None = None) -> dict:
    secret = salt if salt is not None else os.getenv("EXPERIMENT_SALT", "local-demo-salt-change-me")
    digest = hashlib.sha256((secret + anonymous_user_id).encode()).hexdigest()
    bucket = int(digest[:16], 16) % 100
    group = "treatment_main" if bucket < 60 else "treatment_small" if bucket < 70 else "control"
    return {"anonymous_id_hash": hashlib.sha256(anonymous_user_id.encode()).hexdigest(), "bucket": bucket, "group": group}

