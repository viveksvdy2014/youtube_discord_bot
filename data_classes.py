from dataclasses import dataclass


@dataclass
class YoutubeSearchResult:
    uuid: str
    added_by: str
    uploader_name: str
    title: str
    url: str | None
    watch_url: str

    def __hash__(self):
        return self.uuid, self.uploader_name, self.url
