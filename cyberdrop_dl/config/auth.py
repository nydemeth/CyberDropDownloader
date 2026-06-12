from cyclopts import Parameter
from pydantic import BaseModel, Field


class ApiKeyAuth(BaseModel):
    api_key: str = ""


class EmailAuth(BaseModel):
    email: str = ""
    password: str = ""


class ImgurAuth(BaseModel):
    client_id: str = ""


class JDownloaderAuth(BaseModel):
    username: str = ""
    password: str = ""
    device: str = ""


class KemonoAuth(BaseModel):
    session: str = ""


@Parameter(show=False)
class AuthSettings(BaseModel, defer_build=True):
    coomer: KemonoAuth = Field(default_factory=KemonoAuth)
    gofile: ApiKeyAuth = Field(default_factory=ApiKeyAuth)
    imgur: ImgurAuth = Field(default_factory=ImgurAuth)
    jdownloader: JDownloaderAuth = Field(default_factory=JDownloaderAuth)
    kemono: KemonoAuth = Field(default_factory=KemonoAuth)
    meganz: EmailAuth = Field(default_factory=EmailAuth)
    pixeldrain: ApiKeyAuth = Field(default_factory=ApiKeyAuth)
    realdebrid: ApiKeyAuth = Field(default_factory=ApiKeyAuth)
