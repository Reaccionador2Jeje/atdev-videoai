import os
import tempfile
import unittest
import hashlib
import base64
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import oauth_provider as oauth


class OAuthProviderTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db = oauth.DB_PATH
        self.old_base = oauth.BASE_URL
        self.old_resource = oauth.RESOURCE
        oauth.DB_PATH = Path(self.tempdir.name) / "oauth-test.sqlite3"
        oauth.BASE_URL = "https://videoai.example.test"
        oauth.ISSUER = oauth.BASE_URL
        oauth.RESOURCE = oauth.BASE_URL + "/mcp"
        oauth.initialize()
        self.env = patch.dict(os.environ, {
            "ATDEV_OAUTH_USERNAME": "creator",
            "ATDEV_OAUTH_PASSWORD": "a-long-test-password"
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        oauth.DB_PATH = self.old_db
        oauth.BASE_URL = self.old_base
        oauth.ISSUER = self.old_base
        oauth.RESOURCE = self.old_resource
        self.tempdir.cleanup()

    def test_metadata_discovery(self):
        self.assertEqual(oauth.metadata()["issuer"], oauth.BASE_URL)
        self.assertEqual(oauth.protected_resource_metadata()["resource"], oauth.RESOURCE)
        self.assertIn("videoai.render", oauth.metadata()["scopes_supported"])

    def test_authorization_code_pkce_and_refresh_rotation(self):
        client = oauth.register_client({
            "client_name": "test ChatGPT client",
            "redirect_uris": ["https://client.example.test/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none"
        })
        verifier = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        request_id, data = oauth.begin_authorization({
            "client_id": client["client_id"],
            "redirect_uri": client["redirect_uris"][0],
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "videoai.read videoai.write",
            "resource": oauth.RESOURCE,
            "state": "state-test"
        })
        self.assertIn("videoai.read", oauth.authorization_page(request_id, data))
        callback = oauth.complete_authorization({
            "request_id": request_id, "username": "creator",
            "password": "a-long-test-password", "approve": "yes"
        })
        query = parse_qs(urlparse(callback).query)
        self.assertEqual(query["state"][0], "state-test")
        self.assertEqual(query["iss"][0], oauth.ISSUER)
        tokens = oauth.token_endpoint({
            "grant_type": "authorization_code",
            "client_id": client["client_id"],
            "redirect_uri": client["redirect_uris"][0],
            "code": query["code"][0],
            "code_verifier": verifier,
            "resource": oauth.RESOURCE
        })
        self.assertTrue(oauth.verify_access_token(tokens["access_token"], "videoai.read"))
        self.assertFalse(oauth.verify_access_token(tokens["access_token"], "videoai.render"))
        refreshed = oauth.token_endpoint({
            "grant_type": "refresh_token",
            "client_id": client["client_id"],
            "refresh_token": tokens["refresh_token"],
            "resource": oauth.RESOURCE
        })
        self.assertNotEqual(tokens["refresh_token"], refreshed["refresh_token"])
        self.assertTrue(oauth.verify_access_token(refreshed["access_token"], "videoai.read"))

    def test_authorization_errors_include_issuer_and_state(self):
        client = oauth.register_client({"redirect_uris": ["https://client.example.test/callback"]})
        destination = oauth.authorization_error_redirect({
            "client_id": client["client_id"],
            "redirect_uri": client["redirect_uris"][0],
            "state": "error-state"
        }, "invalid request")
        query = parse_qs(urlparse(destination).query)
        self.assertEqual(query["iss"][0], oauth.ISSUER)
        self.assertEqual(query["state"][0], "error-state")
        self.assertEqual(query["error"][0], "invalid_request")

    def test_rejects_non_https_redirect_uri(self):
        with self.assertRaises(ValueError):
            oauth.register_client({"redirect_uris": ["http://example.test/callback"]})

    def test_pkce_is_mandatory(self):
        client = oauth.register_client({"redirect_uris": ["https://client.example.test/callback"]})
        with self.assertRaises(ValueError):
            oauth.begin_authorization({
                "client_id": client["client_id"],
                "redirect_uri": client["redirect_uris"][0],
                "response_type": "code",
                "code_challenge": "not-a-pkce-challenge",
                "code_challenge_method": "plain",
                "scope": "videoai.read",
                "resource": oauth.RESOURCE
            })



    def _issue_test_tokens(self, scope="videoai.read"):
        client = oauth.register_client({"redirect_uris": ["https://client.example.test/callback"]})
        verifier = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        request_id, _ = oauth.begin_authorization({
            "client_id": client["client_id"], "redirect_uri": client["redirect_uris"][0],
            "response_type": "code", "code_challenge": challenge,
            "code_challenge_method": "S256", "scope": scope, "resource": oauth.RESOURCE
        })
        callback = oauth.complete_authorization({
            "request_id": request_id, "username": "creator",
            "password": "a-long-test-password", "approve": "yes"
        })
        code = parse_qs(urlparse(callback).query)["code"][0]
        tokens = oauth.token_endpoint({
            "grant_type": "authorization_code", "client_id": client["client_id"],
            "redirect_uri": client["redirect_uris"][0], "code": code,
            "code_verifier": verifier, "resource": oauth.RESOURCE
        })
        return client, tokens, code

    def test_authorization_code_cannot_be_exchanged_twice(self):
        client, tokens, code = self._issue_test_tokens()
        with self.assertRaisesRegex(ValueError, "invalid_grant"):
            oauth.token_endpoint({
                "grant_type": "authorization_code", "client_id": client["client_id"],
                "redirect_uri": "https://client.example.test/callback",
                "code": code, "code_verifier": "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN",
                "resource": oauth.RESOURCE
            })

    def test_refresh_token_cannot_be_reused(self):
        client, tokens, _code = self._issue_test_tokens()
        request = {
            "grant_type": "refresh_token", "client_id": client["client_id"],
            "refresh_token": tokens["refresh_token"], "resource": oauth.RESOURCE
        }
        rotated = oauth.token_endpoint(request)
        self.assertNotEqual(tokens["refresh_token"], rotated["refresh_token"])
        with self.assertRaisesRegex(ValueError, "invalid_grant"):
            oauth.token_endpoint(request)

    def test_refresh_token_cannot_escalate_scope(self):
        client, tokens, _code = self._issue_test_tokens("videoai.read")
        with self.assertRaisesRegex(ValueError, "invalid_scope"):
            oauth.token_endpoint({
                "grant_type": "refresh_token", "client_id": client["client_id"],
                "refresh_token": tokens["refresh_token"],
                "scope": "videoai.read videoai.render"
            })

if __name__ == "__main__":
    unittest.main()
