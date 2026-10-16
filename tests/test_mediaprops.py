import pytest

from cyberdrop_dl.mediaprops import Codecs


@pytest.mark.parametrize(
    ("codecs", "expected"),
    [
        ("", Codecs.UNKNOWN),
        ("avc1.77.30, mp4a.40.2", Codecs("avc1.77.30", "mp4a.40.2")),
        ("mp4a.40.2", Codecs(None, "mp4a.40.2")),
        ("mp4a.40.5,avc1.42001e", Codecs("avc1.42001e", "mp4a.40.5")),
        ("avc3.640028", Codecs("avc3.640028")),
        (", h264,,invalid_codec,aac", Codecs("h264", "aac")),
        ("unknown_codec", Codecs.UNKNOWN),
        ("av01.0.05M.08", Codecs("av01.0.05M.08")),
        ("vp9.2", Codecs("vp9.2", hdr="HDR10")),
        ("vp09.02.50.10.01.09.18.09.00", Codecs("vp09.02.50.10.01.09.18.09.00", hdr="HDR10")),
        ("av01.0.12M.10.0.110.09.16.09.0", Codecs("av01.0.12M.10.0.110.09.16.09.0", hdr="HDR10")),
        ("dvhe", Codecs("dvhe", hdr="DV")),
        ("fLaC", Codecs(None, "flac")),
        ("theora, vorbis", Codecs("theora", "vorbis")),
        ("random_vcodec, random_acodec", Codecs("random_vcodec", "random_acodec")),
        ("avc1.4d401f,mp4a.40.2", Codecs("avc1.4d401f", "mp4a.40.2")),
        ("hvc1.1.6.L93.B0,mp4a.40.2", Codecs("hvc1.1.6.L93.B0", "mp4a.40.2")),
        ("hevc1.1.6.L93.B0,mp4a.40.2", Codecs("hevc1.1.6.L93.B0", "mp4a.40.2")),
        ("vp09.00.10.08,opus", Codecs("vp09.00.10.08", "opus")),
        ("vp10.00.10.08,opus", Codecs("vp10.00.10.08", "opus")),
        ("vp9.00.10.08,opus", Codecs("vp9.00.10.08", "opus")),
        ("av01.0.04M.08,opus", Codecs("av01.0.04M.08", "opus")),
        ("avc1.4d401f,ac-3", Codecs("avc1.4d401f", "ac-3")),
        ("avc01.4d401f,ec-3", Codecs("avc01.4d401f", "ec-3")),
        ("avc1.4d401f", Codecs("avc1.4d401f", None)),
    ],
)
def test_parse_codecs(codecs: str, expected: Codecs) -> None:
    assert Codecs.parse(codecs) == expected
