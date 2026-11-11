"""EDL et FCPXML décrivent les mêmes points de coupe."""

from agents.edl import edl, fcpxml


def test_timecodes_et_duree():
    clips = [{"debut_s": 10.0, "fin_s": 12.0, "nom": "clip.mp4", "src": "source.mp4"}]
    texte = edl(clips, fps=25)
    assert "00:00:10:00 00:00:12:00 00:00:00:00 00:00:02:00" in texte
    assert "FROM CLIP NAME: clip.mp4" in texte
    xml = fcpxml(clips, fps=25)
    assert 'start="10.000s"' in xml
    assert 'duration="2.000s"' in xml
    assert "<!DOCTYPE fcpxml>" in xml
