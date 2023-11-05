import pydantic_settings


class AccountSetting(pydantic_settings.BaseSettings):
    allowed_signin_failures: int
    signin_possible_after_mail_verification: bool
