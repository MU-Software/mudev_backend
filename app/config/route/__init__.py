import pydantic_settings

import app.config.route.account as route_account_config


class RouteSetting(pydantic_settings.BaseSettings):
    account: route_account_config.AccountSetting
