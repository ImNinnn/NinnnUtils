import os

from main import BASE_DIR


def update_env_setting(key: str, value: str) -> None:
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    found = False

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    lines.append(line)
                    continue
                if stripped.startswith(f"{key}="):
                    if any(ch.isspace() for ch in value) or any(ch in value for ch in "#=!"):
                        escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{key}="{escaped_value}"\n')
                    else:
                        lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        if any(ch.isspace() for ch in value) or any(ch in value for ch in "#=!"):
            escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped_value}"\n')
        else:
            lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))

    os.environ[key] = value
