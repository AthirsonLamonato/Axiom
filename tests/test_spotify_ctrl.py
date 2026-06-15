"""Testes para modules/spotify_ctrl.py — sem Spotify real nem rede."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── _parse_query ──────────────────────────────────────────────────────

class TestParseQuery:
    def setup_method(self):
        from modules.spotify_ctrl import _parse_query
        self.parse = _parse_query

    def test_strips_leading_verb_toca(self):
        track, artist = self.parse("toca Eminem")
        assert "Eminem" in track or "Eminem" in artist

    def test_strips_leading_verb_bota(self):
        track, artist = self.parse("bota uma música do Eminem")
        assert "Eminem" in artist

    def test_strips_o_artista_prefix(self):
        track, artist = self.parse("o artista Radiohead")
        assert "Radiohead" in artist
        assert track == ""

    def test_track_and_artist_separated(self):
        track, artist = self.parse("Rap God do Eminem")
        assert "Rap God" in track
        assert "Eminem" in artist

    def test_playlist_query_no_artist(self):
        track, artist = self.parse("playlist de trabalho")
        assert "trabalho" in track or "trabalho" in artist

    def test_empty_query(self):
        track, artist = self.parse("")
        assert track == "" and artist == ""

    def test_returns_tuple_of_two_strings(self):
        result = self.parse("Coldplay")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(s, str) for s in result)


# ── play_search (modo básico — URI scheme) ──────────────────────────

class TestPlaySearchBasicMode:
    """Testa o ramo sem autenticação, mockando subprocess."""

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._open_spotify_uri")
    @patch("modules.spotify_ctrl._ensure_spotify_ready")
    def test_play_opens_search_uri(self, mock_ready, mock_open, mock_creds):
        from modules.spotify_ctrl import play_search
        result = play_search("Eminem")
        assert mock_open.called
        uri_arg = mock_open.call_args[0][0]
        assert "spotify:search:" in uri_arg
        assert "eminem" in uri_arg.lower()
        assert isinstance(result, str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._open_spotify_uri")
    @patch("modules.spotify_ctrl._ensure_spotify_ready")
    def test_play_search_returns_str(self, mock_ready, mock_open, mock_creds):
        from modules.spotify_ctrl import play_search
        result = play_search("Coldplay")
        assert isinstance(result, str) and len(result) > 0


# ── pause / resume / next / previous — modos sem API ─────────────────

class TestMediaControlNoApi:
    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_pause_no_api_calls_media_key(self, mock_key, mock_creds):
        from modules.spotify_ctrl import pause
        result = pause()
        assert mock_key.called
        assert isinstance(result, str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_resume_no_api_calls_media_key(self, mock_key, mock_creds):
        from modules.spotify_ctrl import resume
        result = resume()
        assert mock_key.called
        assert isinstance(result, str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_next_no_api_calls_media_key(self, mock_key, mock_creds):
        from modules.spotify_ctrl import next_track
        result = next_track()
        assert mock_key.called
        assert isinstance(result, str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_previous_no_api_calls_media_key(self, mock_key, mock_creds):
        from modules.spotify_ctrl import previous_track
        result = previous_track()
        assert mock_key.called
        assert isinstance(result, str)


# ── pause / resume / next / previous — com API mockada ───────────────

class TestMediaControlApiMode:
    def _make_response(self, status: int, json_data: dict = None):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = json_data or {}
        r.ok = status < 400
        return r

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=True)
    @patch("modules.spotify_ctrl._get_access_token", return_value="fake_token")
    @patch("modules.spotify_ctrl._api_request")
    def test_pause_success(self, mock_req, mock_token, mock_creds):
        mock_req.return_value = self._make_response(204)
        from modules.spotify_ctrl import pause
        result = pause()
        assert isinstance(result, str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=True)
    @patch("modules.spotify_ctrl._get_access_token", return_value="fake_token")
    @patch("modules.spotify_ctrl._api_request")
    def test_pause_error_returns_message(self, mock_req, mock_token, mock_creds):
        mock_req.return_value = self._make_response(404)
        from modules.spotify_ctrl import pause
        result = pause()
        assert isinstance(result, str)
        # Não deve fingir sucesso
        assert "pausado" not in result.lower() or "erro" in result.lower() or "404" in result

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=True)
    @patch("modules.spotify_ctrl._get_access_token", return_value="fake_token")
    @patch("modules.spotify_ctrl._api_request")
    def test_next_success(self, mock_req, mock_token, mock_creds):
        mock_req.return_value = self._make_response(204)
        from modules.spotify_ctrl import next_track
        result = next_track()
        assert isinstance(result, str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=True)
    @patch("modules.spotify_ctrl._get_access_token", return_value="fake_token")
    @patch("modules.spotify_ctrl._api_request")
    def test_previous_success(self, mock_req, mock_token, mock_creds):
        mock_req.return_value = self._make_response(204)
        from modules.spotify_ctrl import previous_track
        result = previous_track()
        assert isinstance(result, str)


# ── _ensure_active_device ─────────────────────────────────────────────

class TestEnsureActiveDevice:
    @patch("modules.spotify_ctrl._has_api_credentials", return_value=True)
    @patch("modules.spotify_ctrl._get_access_token", return_value="fake_token")
    @patch("modules.spotify_ctrl._api_request")
    def test_returns_true_when_device_is_active(self, mock_req, mock_token, mock_creds):
        mock_req.return_value = MagicMock(
            status_code=200,
            json=lambda: {"devices": [{"id": "abc", "is_active": True, "is_restricted": False, "name": "PC"}]}
        )
        from modules.spotify_ctrl import _ensure_active_device
        result = _ensure_active_device()
        assert result is True

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=True)
    @patch("modules.spotify_ctrl._get_access_token", return_value="fake_token")
    @patch("modules.spotify_ctrl._api_request")
    def test_returns_false_when_no_devices(self, mock_req, mock_token, mock_creds):
        mock_req.return_value = MagicMock(
            status_code=200,
            json=lambda: {"devices": []}
        )
        from modules.spotify_ctrl import _ensure_active_device
        result = _ensure_active_device()
        assert result is False


# ── Funções públicas retornam str ──────────────────────────────────────

class TestPublicFunctionsReturnStr:
    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._open_spotify_uri")
    @patch("modules.spotify_ctrl._ensure_spotify_ready")
    def test_play_search_returns_str(self, *_):
        from modules.spotify_ctrl import play_search
        assert isinstance(play_search("test"), str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_pause_returns_str(self, *_):
        from modules.spotify_ctrl import pause
        assert isinstance(pause(), str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_resume_returns_str(self, *_):
        from modules.spotify_ctrl import resume
        assert isinstance(resume(), str)

    @patch("modules.spotify_ctrl._has_api_credentials", return_value=False)
    @patch("modules.spotify_ctrl._media_key")
    def test_next_track_returns_str(self, *_):
        from modules.spotify_ctrl import next_track
        assert isinstance(next_track(), str)
