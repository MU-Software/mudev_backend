import uvicorn

import app.config.fastapi as fastapi_config

if __name__ == "__main__":
    config_obj = fastapi_config.get_fastapi_setting()
    uvicorn.run(
        "app:create_app",
        factory=True,
        **config_obj.to_uvicorn_config(),
    )
