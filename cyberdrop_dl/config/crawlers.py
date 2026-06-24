from typing import Literal

from pydantic import Field

from cyberdrop_dl.models import ConfigGroup, ConfigModel
from cyberdrop_dl.models.types import FalsyAsTuple, HttpURL, NonEmptyStr, RemoveDuplicates


class KemonoConfig(ConfigModel):
    ignore_ads: bool = False
    "Ignore advertisement posts"
    ignore_post_content: bool = True
    "Ignore URL in inside the content (text) of posts"


class TikTokConfig(ConfigModel):
    original: bool = False
    "Download videos in original quality (slower)"


class BandcampConfig(ConfigModel):
    formats: RemoveDuplicates[
        tuple[Literal["mp3-320", "mp3", "aac-hi", "wav", "flac", "vorbis", "aiff", "alas"], ...],
    ] = (
        "mp3-320",
        "mp3",
        "aac-hi",
        "wav",
        "flac",
        "vorbis",
        "aiff",
        "alas",
    )
    "Format to choose for downloads (if available), ordered by preference"


class ClypitConfig(ConfigModel):
    prefer_mp3: bool = False
    """Download audios as .mp3 files even if WAV (high quality) versions are available"""


class OnePaceConfig(ConfigModel):
    prefer_dub: bool = False
    """Download episodes with english audio tracks instead of japanase (if available)"""


class GenericCrawlers(ConfigModel):
    wordpress_media: FalsyAsTuple[HttpURL] = ()
    wordpress_html: FalsyAsTuple[HttpURL] = ()
    discourse: FalsyAsTuple[HttpURL] = ()
    chevereto: FalsyAsTuple[HttpURL] = ()


class Crawlers(ConfigGroup, name=None):
    disabled: RemoveDuplicates[FalsyAsTuple[NonEmptyStr]] = ()
    "Name of crawlers to disable for the current run"

    bandcamp: BandcampConfig = Field(default_factory=BandcampConfig)
    clypit: ClypitConfig = Field(default_factory=ClypitConfig)
    generic: GenericCrawlers = Field(default_factory=GenericCrawlers)
    kemono: KemonoConfig = Field(default_factory=KemonoConfig)
    coomer: KemonoConfig = Field(default_factory=KemonoConfig)
    one_pace: OnePaceConfig = Field(default_factory=OnePaceConfig)
    tiktok: TikTokConfig = Field(default_factory=TikTokConfig)
